"""Tests for deterministic procedural terrain generation."""

from __future__ import annotations

import hashlib
import unittest

import numpy as np

from Sources.Procedural.terrain import (
    LayeredTerrainConfig,
    TerrainConfig,
    derive_layer_seed,
    generate_layered_terrain,
    generate_terrain,
)


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


class LayeredTerrainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = LayeredTerrainConfig(seed=12345, width=32, height=24)

    def test_same_base_seed_produces_exactly_same_terrain(self) -> None:
        first = generate_layered_terrain(self.config)
        second = generate_layered_terrain(self.config)

        self.assertTrue(np.array_equal(first, second))

    def test_different_base_seed_changes_terrain(self) -> None:
        first = generate_layered_terrain(self.config)
        second = generate_layered_terrain(
            LayeredTerrainConfig(seed=12346, width=32, height=24)
        )

        self.assertFalse(np.array_equal(first, second))

    def test_shape_dtype_and_finite_values(self) -> None:
        terrain = generate_layered_terrain(self.config)

        self.assertEqual(terrain.shape, (24, 32))
        self.assertEqual(terrain.dtype, np.dtype(np.float32))
        self.assertTrue(terrain.flags.c_contiguous)
        self.assertTrue(np.isfinite(terrain).all())

    def test_layer_seed_derivation_is_deterministic_and_wrapped(self) -> None:
        self.assertEqual(
            [derive_layer_seed(12345, index) for index in range(3)],
            [12345, 1_012_348, 2_012_378],
        )
        self.assertEqual(
            [derive_layer_seed(2**31 - 1, index) for index in range(3)],
            [2_147_483_647, -2_146_483_646, -2_145_483_616],
        )

    def test_layered_reference_terrain_digest(self) -> None:
        terrain = generate_layered_terrain(self.config)
        digest = hashlib.sha256(terrain.tobytes(order="C")).hexdigest()

        self.assertEqual(
            digest,
            "6d3b39f2a57c854620a7bf7a58a79d4dd06ec5669b1756e3cf1aee47426b58b3",
        )


if __name__ == "__main__":
    unittest.main()
