"""Deterministic procedural terrain generation using FastNoiseLite."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from numpy.typing import NDArray
from pyfastnoiselite.pyfastnoiselite import FastNoiseLite, FractalType, NoiseType


Float32Array = NDArray[np.float32]

_MIN_SEED = -(2**31)
_MAX_SEED = 2**31 - 1


@dataclass(frozen=True, slots=True)
class TerrainConfig:
    """All inputs that define a generated terrain raster."""

    seed: int
    width: int = 512
    height: int = 512
    frequency: float = 0.01
    octaves: int = 5
    lacunarity: float = 2.0
    gain: float = 0.5

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        if not _MIN_SEED <= self.seed <= _MAX_SEED:
            raise ValueError("seed must fit in a signed 32-bit integer")

        for name, value in (("width", self.width), ("height", self.height)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")

        if isinstance(self.octaves, bool) or not isinstance(self.octaves, int):
            raise TypeError("octaves must be an integer")
        if self.octaves <= 0:
            raise ValueError("octaves must be greater than zero")

        for name, value in (
            ("frequency", self.frequency),
            ("lacunarity", self.lacunarity),
            ("gain", self.gain),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")

        if self.frequency <= 0:
            raise ValueError("frequency must be greater than zero")
        if self.lacunarity <= 0:
            raise ValueError("lacunarity must be greater than zero")
        if self.gain < 0:
            raise ValueError("gain must be greater than or equal to zero")


def generate_terrain(config: TerrainConfig) -> Float32Array:
    """Generate a row-major float32 height raster for ``config``.

    FastNoiseLite is the sole noise implementation. Coordinates start at
    (0, 0), increase by one sample, and are passed in x/y order.
    """

    noise = FastNoiseLite(seed=config.seed)
    noise.noise_type = NoiseType.NoiseType_OpenSimplex2
    noise.fractal_type = FractalType.FractalType_FBm
    noise.frequency = config.frequency
    noise.fractal_octaves = config.octaves
    noise.fractal_lacunarity = config.lacunarity
    noise.fractal_gain = config.gain
    noise.fractal_weighted_strength = 0.0

    y_coordinates, x_coordinates = np.indices(
        (config.height, config.width), dtype=np.float32
    )
    coordinates = np.stack(
        (x_coordinates.reshape(-1), y_coordinates.reshape(-1)), axis=0
    )
    values = noise.gen_from_coords(coordinates)

    return np.ascontiguousarray(values, dtype=np.float32).reshape(
        config.height, config.width
    )
