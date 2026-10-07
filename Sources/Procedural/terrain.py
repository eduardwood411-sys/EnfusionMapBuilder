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
_SEED_MODULUS = 2**32


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


@dataclass(frozen=True, slots=True)
class TerrainLayerConfig:
    """Fixed parameters for one layer in the layered terrain baseline."""

    name: str
    frequency: float
    octaves: int
    lacunarity: float
    gain: float
    weight: float
    seed_offset: int


LAYERED_TERRAIN_LAYERS = (
    TerrainLayerConfig("macro", 0.003, 2, 2.0, 0.40, 1.0, 0),
    TerrainLayerConfig("secondary", 0.006, 2, 2.0, 0.40, 0.35, 1_000_003),
    TerrainLayerConfig("detail", 0.010, 2, 2.0, 0.40, 0.15, 2_000_033),
)


@dataclass(frozen=True, slots=True)
class LayeredTerrainConfig:
    """Inputs for the fixed three-layer procedural terrain baseline."""

    seed: int
    width: int = 512
    height: int = 512

    def __post_init__(self) -> None:
        # Reuse the established validation without changing the baseline API.
        TerrainConfig(seed=self.seed, width=self.width, height=self.height)


def derive_layer_seed(base_seed: int, layer_index: int) -> int:
    """Add a fixed layer offset and wrap it into signed 32-bit range."""

    TerrainConfig(seed=base_seed, width=1, height=1)
    if isinstance(layer_index, bool) or not isinstance(layer_index, int):
        raise TypeError("layer_index must be an integer")
    if not 0 <= layer_index < len(LAYERED_TERRAIN_LAYERS):
        raise ValueError("layer_index must identify one of the three terrain layers")

    offset = LAYERED_TERRAIN_LAYERS[layer_index].seed_offset
    unsigned_seed = (base_seed + offset) % _SEED_MODULUS
    if unsigned_seed > _MAX_SEED:
        return unsigned_seed - _SEED_MODULUS
    return unsigned_seed


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


def generate_layered_terrain(config: LayeredTerrainConfig) -> Float32Array:
    """Generate the fixed macro, secondary, and detail weighted terrain."""

    generated_layers = []
    for layer_index, layer in enumerate(LAYERED_TERRAIN_LAYERS):
        layer_config = TerrainConfig(
            seed=derive_layer_seed(config.seed, layer_index),
            width=config.width,
            height=config.height,
            frequency=layer.frequency,
            octaves=layer.octaves,
            lacunarity=layer.lacunarity,
            gain=layer.gain,
        )
        generated_layers.append(generate_terrain(layer_config))

    macro, secondary, detail = generated_layers
    macro_config, secondary_config, detail_config = LAYERED_TERRAIN_LAYERS
    total_weight = np.float32(
        macro_config.weight + secondary_config.weight + detail_config.weight
    )
    combined = (
        macro * np.float32(macro_config.weight)
        + secondary * np.float32(secondary_config.weight)
        + detail * np.float32(detail_config.weight)
    ) / total_weight
    return np.ascontiguousarray(combined, dtype=np.float32)
