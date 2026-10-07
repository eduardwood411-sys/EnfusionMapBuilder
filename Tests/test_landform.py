"""Tests for generic deterministic procedural landform shaping."""

from __future__ import annotations

from collections import deque

import hashlib
from pathlib import Path
import unittest

import numpy as np

from Frontends.CLI.terrain_preview import (
    landform_to_preview_pixels,
    save_landform_preview_png,
)
from Sources.Procedural.landform import (
    CoastEdge,
    LandformConfig,
    LandformMode,
    derive_landform_macro_parameters,
    derive_land_water_masks,
    generate_landform,
)
from Sources.Procedural.terrain import LayeredTerrainConfig, generate_layered_terrain


class LandformTests(unittest.TestCase):
    REPRESENTATIVE_SEEDS = (1001, 2002, 3003, 4004, 5005, 12345)

    def setUp(self) -> None:
        self.island_config = LandformConfig(
            seed=12345,
            mode=LandformMode.ISLAND,
            width=32,
            height=24,
        )
        self.coast_config = LandformConfig(
            seed=12345,
            mode=LandformMode.COAST,
            width=32,
            height=24,
            coast_edge=CoastEdge.EAST,
        )
        self.output_directory = Path("Projects/Synthetic_Test_01/Output")

    def _temporary_output(self, name: str) -> Path:
        output_path = self.output_directory / name
        self.addCleanup(output_path.unlink, missing_ok=True)
        return output_path

    @staticmethod
    def _land_component_count(land_mask: np.ndarray) -> int:
        remaining = land_mask.copy()
        components = 0
        height, width = remaining.shape
        for start_y, start_x in np.argwhere(remaining):
            if not remaining[start_y, start_x]:
                continue
            components += 1
            remaining[start_y, start_x] = False
            queue = deque([(int(start_y), int(start_x))])
            while queue:
                y, x = queue.popleft()
                for neighbor_y, neighbor_x in (
                    (y - 1, x),
                    (y + 1, x),
                    (y, x - 1),
                    (y, x + 1),
                ):
                    if (
                        0 <= neighbor_y < height
                        and 0 <= neighbor_x < width
                        and remaining[neighbor_y, neighbor_x]
                    ):
                        remaining[neighbor_y, neighbor_x] = False
                        queue.append((neighbor_y, neighbor_x))
        return components

    def test_macro_parameters_are_deterministic_and_vary_by_seed(self) -> None:
        for mode in LandformMode:
            with self.subTest(mode=mode):
                parameter_sets = []
                for seed in self.REPRESENTATIVE_SEEDS:
                    config = LandformConfig(seed=seed, mode=mode)
                    first = derive_landform_macro_parameters(config)
                    second = derive_landform_macro_parameters(config)
                    self.assertEqual(first, second)
                    parameter_sets.append(first)
                self.assertEqual(len(set(parameter_sets)), len(parameter_sets))

    def test_representative_islands_are_connected_with_water_boundaries(self) -> None:
        for seed in self.REPRESENTATIVE_SEEDS:
            with self.subTest(seed=seed):
                terrain = generate_landform(
                    LandformConfig(
                        seed=seed, mode=LandformMode.ISLAND, width=512, height=512
                    )
                )
                land, _ = derive_land_water_masks(terrain)
                boundary = np.concatenate(
                    (land[0, :], land[-1, :], land[1:-1, 0], land[1:-1, -1])
                )
                self.assertFalse(np.any(boundary))
                self.assertEqual(self._land_component_count(land), 1)
                self.assertGreaterEqual(float(land.mean()), 0.25)
                self.assertLessEqual(float(land.mean()), 0.60)
                self.assertEqual(terrain.dtype, np.dtype(np.float32))
                self.assertTrue(np.isfinite(terrain).all())

    def test_representative_coasts_have_one_mainland_and_submerged_edge(self) -> None:
        for seed in self.REPRESENTATIVE_SEEDS:
            with self.subTest(seed=seed):
                terrain = generate_landform(
                    LandformConfig(
                        seed=seed,
                        mode=LandformMode.COAST,
                        width=512,
                        height=512,
                        coast_edge=CoastEdge.EAST,
                    )
                )
                land, _ = derive_land_water_masks(terrain)
                self.assertFalse(np.any(land[:, -1]))
                self.assertTrue(np.any(land[:, 0]))
                self.assertEqual(self._land_component_count(land), 1)
                self.assertGreaterEqual(float(land.mean()), 0.45)
                self.assertLessEqual(float(land.mean()), 0.85)
                self.assertEqual(terrain.dtype, np.dtype(np.float32))
                self.assertTrue(np.isfinite(terrain).all())

    def test_island_is_exactly_deterministic(self) -> None:
        first = generate_landform(self.island_config)
        second = generate_landform(self.island_config)
        self.assertTrue(np.array_equal(first, second))

    def test_coast_is_exactly_deterministic(self) -> None:
        first = generate_landform(self.coast_config)
        second = generate_landform(self.coast_config)
        self.assertTrue(np.array_equal(first, second))

    def test_different_seeds_produce_different_landforms(self) -> None:
        for config in (self.island_config, self.coast_config):
            with self.subTest(mode=config.mode):
                other = LandformConfig(
                    seed=12346,
                    mode=config.mode,
                    width=config.width,
                    height=config.height,
                    coast_edge=config.coast_edge,
                )
                self.assertFalse(
                    np.array_equal(generate_landform(config), generate_landform(other))
                )

    def test_results_are_float32_and_finite(self) -> None:
        for config in (self.island_config, self.coast_config):
            with self.subTest(mode=config.mode):
                terrain = generate_landform(config)
                self.assertEqual(terrain.dtype, np.dtype(np.float32))
                self.assertTrue(np.isfinite(terrain).all())

    def test_island_boundaries_are_sea_and_interior_contains_land(self) -> None:
        terrain = generate_landform(self.island_config)
        boundary = np.concatenate(
            (terrain[0, :], terrain[-1, :], terrain[1:-1, 0], terrain[1:-1, -1])
        )
        interior = terrain[1:-1, 1:-1]

        self.assertTrue(np.all(boundary < 0.0))
        self.assertTrue(np.any(interior > 0.0))

    def test_coast_selected_edge_is_sea_and_opposite_is_not_forced(self) -> None:
        terrain = generate_landform(self.coast_config)
        base = generate_layered_terrain(
            LayeredTerrainConfig(seed=12345, width=32, height=24)
        )

        self.assertTrue(np.all(terrain[:, -1] < 0.0))
        macro = derive_landform_macro_parameters(self.coast_config)
        np.testing.assert_array_equal(
            terrain[:, 0], base[:, 0] + np.float32(macro.land_bias)
        )
        self.assertTrue(np.any(terrain[:, 0] > 0.0))

    def test_coast_land_reaches_non_sea_facing_boundaries(self) -> None:
        terrain = generate_landform(self.coast_config)

        self.assertTrue(np.any(terrain[:, 0] > 0.0))
        self.assertTrue(np.any(terrain[0, :-1] > 0.0))
        self.assertTrue(np.any(terrain[-1, :-1] > 0.0))

    def test_land_and_water_masks_are_deterministic(self) -> None:
        terrain = generate_landform(self.island_config)
        first_land, first_water = derive_land_water_masks(terrain)
        second_land, second_water = derive_land_water_masks(terrain.copy())

        self.assertTrue(np.array_equal(first_land, second_land))
        self.assertTrue(np.array_equal(first_water, second_water))
        self.assertTrue(np.array_equal(first_land, terrain > 0.0))
        self.assertTrue(np.array_equal(first_water, terrain <= 0.0))
        self.assertTrue(np.all(first_land != first_water))

    def test_all_coast_edge_directions(self) -> None:
        for edge in CoastEdge:
            with self.subTest(edge=edge):
                config = LandformConfig(
                    seed=12345,
                    mode=LandformMode.COAST,
                    width=32,
                    height=24,
                    coast_edge=edge,
                )
                terrain = generate_landform(config)
                if edge is CoastEdge.EAST:
                    sea_edge, opposite = terrain[:, -1], terrain[:, 0]
                elif edge is CoastEdge.WEST:
                    sea_edge, opposite = terrain[:, 0], terrain[:, -1]
                elif edge is CoastEdge.NORTH:
                    sea_edge, opposite = terrain[0, :], terrain[-1, :]
                else:
                    sea_edge, opposite = terrain[-1, :], terrain[0, :]

                self.assertTrue(np.all(sea_edge < 0.0))
                self.assertTrue(np.any(opposite > 0.0))

    def test_island_reference_digest(self) -> None:
        terrain = generate_landform(self.island_config)
        digest = hashlib.sha256(terrain.tobytes(order="C")).hexdigest()
        self.assertEqual(
            digest,
            "a385ea72f06376647fcbba8ec63253c57fe9afb46b1ae613017b62a4494d4fb1",
        )

    def test_coast_reference_digest(self) -> None:
        terrain = generate_landform(self.coast_config)
        digest = hashlib.sha256(terrain.tobytes(order="C")).hexdigest()
        self.assertEqual(
            digest,
            "2b26a91539bf7012d9763e4727a5f3a288e5627ec0e6eb1b78e981abc618d906",
        )

    def test_landform_preview_png_is_deterministic(self) -> None:
        terrain = generate_landform(self.island_config)
        first_path = self._temporary_output("_test_landform_preview_first.png")
        second_path = self._temporary_output("_test_landform_preview_second.png")

        save_landform_preview_png(terrain, first_path)
        save_landform_preview_png(terrain.copy(), second_path)

        self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
        pixels = landform_to_preview_pixels(terrain)
        self.assertTrue(np.all(pixels[terrain <= 0.0] == 0))
        self.assertTrue(np.all(pixels[terrain > 0.0] > 0))


if __name__ == "__main__":
    unittest.main()
