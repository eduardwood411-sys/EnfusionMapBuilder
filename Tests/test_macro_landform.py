"""Focused tests for the isolated MacroLandform Prototype v0.1."""

from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np

from Frontends.CLI.macro_landform_preview import (
    mask_to_preview_pixels,
    save_macro_mask_png,
)
from Sources.Procedural.macro_landform import (
    AnchorRole,
    BoundaryRule,
    MacroLandformConfig,
    MacroLandformPreset,
    MacroRasterizer,
    MapEdge,
    derive_macro_subseed,
    generate_macro_landform,
    generate_macro_landform_plan,
)


class MacroLandformTests(unittest.TestCase):
    WIDTH = 128
    HEIGHT = 128

    @classmethod
    def setUpClass(cls) -> None:
        cls.results = {}
        for rasterizer in MacroRasterizer:
            for preset in MacroLandformPreset:
                for seed in (1001, 2002):
                    key = (rasterizer, preset, seed)
                    cls.results[key] = generate_macro_landform(
                        MacroLandformConfig(
                            seed=seed,
                            preset=preset,
                            rasterizer=rasterizer,
                            width=cls.WIDTH,
                            height=cls.HEIGHT,
                        )
                    )

    def _result(
        self,
        rasterizer: MacroRasterizer,
        preset: MacroLandformPreset,
        seed: int = 1001,
    ):
        return self.results[(rasterizer, preset, seed)]

    def test_subseeds_are_deterministic_named_and_distinct(self) -> None:
        first = derive_macro_subseed(12345, "macro.prototype.alpha")
        self.assertEqual(first, derive_macro_subseed(12345, "macro.prototype.alpha"))
        self.assertNotEqual(first, derive_macro_subseed(12345, "macro.prototype.beta"))
        self.assertNotEqual(first, derive_macro_subseed(12346, "macro.prototype.alpha"))

    def test_identical_inputs_are_byte_identical_for_both_rasterizers(self) -> None:
        for rasterizer in MacroRasterizer:
            for preset in MacroLandformPreset:
                with self.subTest(rasterizer=rasterizer, preset=preset):
                    config = MacroLandformConfig(
                        seed=1001,
                        preset=preset,
                        rasterizer=rasterizer,
                        width=self.WIDTH,
                        height=self.HEIGHT,
                    )
                    first = self._result(rasterizer, preset)
                    second = generate_macro_landform(config)
                    self.assertEqual(first.plan, second.plan)
                    self.assertTrue(np.array_equal(first.landness, second.landness))
                    self.assertEqual(first.landness.tobytes(), second.landness.tobytes())
                    self.assertTrue(np.array_equal(first.land_mask, second.land_mask))

    def test_different_seeds_produce_different_plans_and_masks(self) -> None:
        for rasterizer in MacroRasterizer:
            for preset in MacroLandformPreset:
                with self.subTest(rasterizer=rasterizer, preset=preset):
                    first = self._result(rasterizer, preset, 1001)
                    second = self._result(rasterizer, preset, 2002)
                    self.assertNotEqual(first.plan, second.plan)
                    self.assertFalse(np.array_equal(first.land_mask, second.land_mask))

    def test_arrays_have_expected_shape_dtype_and_finite_values(self) -> None:
        for result in self.results.values():
            self.assertEqual(result.landness.shape, (self.HEIGHT, self.WIDTH))
            self.assertEqual(result.landness.dtype, np.dtype(np.float32))
            self.assertTrue(result.landness.flags.c_contiguous)
            self.assertTrue(np.isfinite(result.landness).all())
            self.assertEqual(result.land_mask.dtype, np.dtype(np.bool_))

    def test_plans_are_normalized_explicit_and_graph_guided(self) -> None:
        for preset in MacroLandformPreset:
            plan = generate_macro_landform_plan(
                MacroLandformConfig(seed=12345, preset=preset)
            )
            positive = [anchor for anchor in plan.anchors if anchor.positive]
            negative = [anchor for anchor in plan.anchors if not anchor.positive]
            self.assertGreaterEqual(len(positive), 5)
            self.assertLessEqual(len(positive), 12)
            self.assertGreaterEqual(len(negative), 1)
            self.assertTrue(any(connection.positive for connection in plan.connections))
            self.assertTrue(plan.derived_subseeds)
            self.assertTrue(plan.generation_parameters)
            for anchor in plan.anchors:
                self.assertGreaterEqual(anchor.x, 0.0)
                self.assertLessEqual(anchor.x, 1.0)
                self.assertGreaterEqual(anchor.y, 0.0)
                self.assertLessEqual(anchor.y, 1.0)
                self.assertGreater(anchor.radius, 0.0)
                self.assertGreater(anchor.strength, 0.0)

    def test_island_edges_are_water_and_dominant_land_is_connected(self) -> None:
        for rasterizer in MacroRasterizer:
            result = self._result(rasterizer, MacroLandformPreset.ISLAND)
            mask = result.land_mask
            boundary = np.concatenate(
                (mask[0, :], mask[-1, :], mask[1:-1, 0], mask[1:-1, -1])
            )
            self.assertFalse(np.any(boundary))
            self.assertEqual(result.metrics.land_component_count, 1)
            self.assertEqual(result.metrics.largest_component_percent, 100.0)
            self.assertTrue(result.metrics.intended_main_graph_connected)

    def test_mainland_coast_has_west_mainland_and_water_east_edge(self) -> None:
        for rasterizer in MacroRasterizer:
            result = self._result(
                rasterizer, MacroLandformPreset.MAINLAND_COAST_EAST
            )
            self.assertTrue(np.any(result.land_mask[:, 0]))
            self.assertFalse(np.any(result.land_mask[:, -1]))
            self.assertEqual(result.metrics.land_component_count, 1)
            self.assertTrue(result.metrics.intended_main_graph_connected)

    def test_peninsula_has_projection_water_flanks_and_safe_neck(self) -> None:
        for rasterizer in MacroRasterizer:
            result = self._result(rasterizer, MacroLandformPreset.PENINSULA_EAST)
            self.assertTrue(np.any(result.land_mask[:, 0]))
            self.assertFalse(np.any(result.land_mask[:, -1]))
            self.assertGreaterEqual(result.metrics.eastward_projection_fraction, 0.68)
            self.assertTrue(result.metrics.peninsula_water_flanks_pass)
            self.assertTrue(result.metrics.minimum_neck_pass)
            self.assertEqual(result.metrics.land_component_count, 1)

    def test_boundary_rules_are_semantic_plan_data_and_pass(self) -> None:
        island = self._result(MacroRasterizer.GAUSSIAN, MacroLandformPreset.ISLAND)
        self.assertEqual(
            {condition.rule for condition in island.plan.boundaries},
            {BoundaryRule.REQUIRED_WATER},
        )
        coast = self._result(
            MacroRasterizer.GAUSSIAN, MacroLandformPreset.MAINLAND_COAST_EAST
        )
        rules = {condition.edge: condition.rule for condition in coast.plan.boundaries}
        self.assertIs(rules[MapEdge.WEST], BoundaryRule.REQUIRED_LAND)
        self.assertIs(rules[MapEdge.EAST], BoundaryRule.REQUIRED_WATER)
        for result in self.results.values():
            self.assertTrue(result.metrics.boundary_rules_pass)

    def test_negative_controls_and_connections_are_explicit(self) -> None:
        mainland = self._result(
            MacroRasterizer.GAUSSIAN, MacroLandformPreset.MAINLAND_COAST_EAST
        ).plan
        peninsula = self._result(
            MacroRasterizer.GAUSSIAN, MacroLandformPreset.PENINSULA_EAST
        ).plan
        self.assertTrue(
            any(anchor.role is AnchorRole.BAY for anchor in mainland.anchors)
        )
        self.assertTrue(any(not item.positive for item in mainland.connections))
        self.assertTrue(
            any(anchor.role is AnchorRole.CHANNEL for anchor in peninsula.anchors)
        )
        self.assertTrue(any(not item.positive for item in peninsula.connections))

    def test_no_cleanup_hides_topology_failures(self) -> None:
        for result in self.results.values():
            self.assertEqual(result.metrics.cleanup_land_pixels_removed, 0)
            self.assertEqual(result.metrics.cleanup_land_percent_removed, 0.0)
            self.assertEqual(result.metrics.inland_water_component_count, 0)
            self.assertTrue(result.metrics.accepted, result.metrics.failure_reasons)

    def test_gaussian_and_rbf_are_distinct_working_rasterizers(self) -> None:
        for preset in MacroLandformPreset:
            gaussian = self._result(MacroRasterizer.GAUSSIAN, preset)
            rbf = self._result(MacroRasterizer.RBF, preset)
            self.assertEqual(gaussian.plan, rbf.plan)
            self.assertFalse(np.array_equal(gaussian.landness, rbf.landness))
            self.assertFalse(np.array_equal(gaussian.land_mask, rbf.land_mask))

    def test_binary_preview_is_neutral_and_deterministic(self) -> None:
        result = self._result(MacroRasterizer.GAUSSIAN, MacroLandformPreset.ISLAND)
        pixels = mask_to_preview_pixels(result.land_mask)
        self.assertEqual(set(np.unique(pixels)), {0, 255})
        output = Path(
            "Projects/Synthetic_Test_01/Output/_test_macro_landform_preview.png"
        )
        self.addCleanup(output.unlink, missing_ok=True)
        save_macro_mask_png(result.land_mask, output)
        first = output.read_bytes()
        save_macro_mask_png(result.land_mask.copy(), output)
        self.assertEqual(first, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
