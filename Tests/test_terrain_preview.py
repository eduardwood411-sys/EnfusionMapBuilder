"""Tests for grayscale terrain preview generation."""

from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np
from PIL import Image

from Frontends.CLI.terrain_preview import (
    save_preview_png,
    terrain_to_preview_pixels,
)
from Sources.Procedural.terrain import (
    LayeredTerrainConfig,
    TerrainConfig,
    generate_layered_terrain,
    generate_terrain,
)


class TerrainPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.terrain = generate_terrain(TerrainConfig(seed=12345, width=16, height=12))
        self.output_directory = Path("Projects/Synthetic_Test_01/Output")

    def _temporary_output(self, name: str) -> Path:
        output_path = self.output_directory / name
        self.addCleanup(output_path.unlink, missing_ok=True)
        return output_path

    def test_preview_has_expected_mode_size_and_pixels(self) -> None:
        expected_pixels = terrain_to_preview_pixels(self.terrain)

        output_path = self._temporary_output("_test_preview.png")
        save_preview_png(self.terrain, output_path)

        with Image.open(output_path) as image:
            self.assertEqual(image.mode, "L")
            self.assertEqual(image.size, (16, 12))
            self.assertTrue(np.array_equal(np.asarray(image), expected_pixels))

    def test_same_terrain_produces_identical_png_bytes(self) -> None:
        first_path = self._temporary_output("_test_preview_first.png")
        second_path = self._temporary_output("_test_preview_second.png")

        save_preview_png(self.terrain, first_path)
        save_preview_png(self.terrain.copy(), second_path)

        self.assertEqual(first_path.read_bytes(), second_path.read_bytes())

    def test_layered_preview_png_is_deterministic(self) -> None:
        config = LayeredTerrainConfig(seed=12345, width=16, height=12)
        first_terrain = generate_layered_terrain(config)
        second_terrain = generate_layered_terrain(config)
        first_path = self._temporary_output("_test_layered_preview_first.png")
        second_path = self._temporary_output("_test_layered_preview_second.png")

        save_preview_png(first_terrain, first_path)
        save_preview_png(second_terrain, second_path)

        self.assertEqual(first_path.read_bytes(), second_path.read_bytes())

    def test_preview_uses_fixed_value_mapping(self) -> None:
        terrain = np.array([[-1.0, 0.0, 1.0]], dtype=np.float32)

        pixels = terrain_to_preview_pixels(terrain)

        np.testing.assert_array_equal(
            pixels, np.array([[0, 128, 255]], dtype=np.uint8)
        )

    def test_invalid_terrain_is_rejected(self) -> None:
        invalid_terrains = (
            np.array([], dtype=np.float32),
            np.zeros((2, 2, 2), dtype=np.float32),
            np.array([[np.nan]], dtype=np.float32),
        )

        for terrain in invalid_terrains:
            with self.subTest(shape=terrain.shape):
                with self.assertRaises(ValueError):
                    terrain_to_preview_pixels(terrain)


if __name__ == "__main__":
    unittest.main()
