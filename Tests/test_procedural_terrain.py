"""Tests for deterministic procedural terrain generation."""

from __future__ import annotations

import hashlib
import unittest

import numpy as np

from Sources.Procedural.terrain import TerrainConfig, generate_terrain


class ProceduralTerrainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = TerrainConfig(seed=12345, width=32, height=24)

    def test_same_configuration_produces_exactly_same_terrain(self) -> None:
        first = generate_terrain(self.config)

        np.random.seed(9876)
        np.random.random(100)
        second = generate_terrain(self.config)

        self.assertTrue(np.array_equal(first, second))

    def test_reference_terrain_digest(self) -> None:
        terrain = generate_terrain(self.config)
        digest = hashlib.sha256(terrain.tobytes(order="C")).hexdigest()

        self.assertEqual(
            digest,
            "a9aa40abc35c5199095a6ac574ebb7ba1fb5b5ccc47b884f5e589b91ae7eddf5",
        )

    def test_different_seed_changes_terrain(self) -> None:
        first = generate_terrain(self.config)
        second = generate_terrain(
            TerrainConfig(seed=12346, width=self.config.width, height=self.config.height)
        )

        self.assertFalse(np.array_equal(first, second))

    def test_shape_dtype_and_values(self) -> None:
        terrain = generate_terrain(self.config)

        self.assertEqual(terrain.shape, (24, 32))
        self.assertEqual(terrain.dtype, np.dtype(np.float32))
        self.assertTrue(terrain.flags.c_contiguous)
        self.assertTrue(np.isfinite(terrain).all())
        self.assertGreaterEqual(float(terrain.min()), -1.0)
        self.assertLessEqual(float(terrain.max()), 1.0)

    def test_invalid_configuration_is_rejected(self) -> None:
        invalid_arguments = (
            {"seed": 2**31},
            {"seed": 1, "width": 0},
            {"seed": 1, "height": -1},
            {"seed": 1, "frequency": 0.0},
            {"seed": 1, "octaves": 0},
            {"seed": 1, "lacunarity": float("nan")},
            {"seed": 1, "gain": -0.1},
        )

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises((TypeError, ValueError)):
                    TerrainConfig(**arguments)


if __name__ == "__main__":
    unittest.main()
