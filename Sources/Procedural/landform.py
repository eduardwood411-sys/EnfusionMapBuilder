"""Generic deterministic landform shaping for procedural terrain."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

import numpy as np

from Sources.Procedural.terrain import (
    Float32Array,
    LayeredTerrainConfig,
    generate_layered_terrain,
)


SEA_LEVEL = np.float32(0.0)


class LandformMode(str, Enum):
    ISLAND = "island"
    COAST = "coast"


class CoastEdge(str, Enum):
    EAST = "east"
    WEST = "west"
    NORTH = "north"
    SOUTH = "south"


@dataclass(frozen=True, slots=True)
class LandformConfig:
    """Configuration for shaping layered terrain into a generic landform."""

    seed: int
    mode: LandformMode
    width: int = 512
    height: int = 512
    coast_edge: CoastEdge = CoastEdge.EAST
    land_bias: float = 0.30
    falloff_depth: float = 1.40
    island_radius_x: float = 0.98
    island_radius_y: float = 0.92
    island_falloff_start: float = 0.68
    island_falloff_end: float = 1.0
    coast_falloff_start: float = 0.65
    coast_falloff_end: float = 1.0

    def __post_init__(self) -> None:
        LayeredTerrainConfig(seed=self.seed, width=self.width, height=self.height)
        if not isinstance(self.mode, LandformMode):
            raise TypeError("mode must be a LandformMode")
        if not isinstance(self.coast_edge, CoastEdge):
            raise TypeError("coast_edge must be a CoastEdge")

        numeric_parameters = (
            ("land_bias", self.land_bias),
            ("falloff_depth", self.falloff_depth),
            ("island_radius_x", self.island_radius_x),
            ("island_radius_y", self.island_radius_y),
            ("island_falloff_start", self.island_falloff_start),
            ("island_falloff_end", self.island_falloff_end),
            ("coast_falloff_start", self.coast_falloff_start),
            ("coast_falloff_end", self.coast_falloff_end),
        )
        for name, value in numeric_parameters:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")

        if self.island_radius_x <= 0 or self.island_radius_y <= 0:
            raise ValueError("island radii must be greater than zero")
        if not 0 <= self.island_falloff_start < self.island_falloff_end:
            raise ValueError("island falloff start must be before its end")
        nearest_boundary_distance = min(
            1.0 / self.island_radius_x, 1.0 / self.island_radius_y
        )
        if self.island_falloff_end > nearest_boundary_distance:
            raise ValueError("island falloff must be complete at every map boundary")
        if not 0 <= self.coast_falloff_start < self.coast_falloff_end <= 1:
            raise ValueError("coast falloff must be ordered within [0, 1]")
        if self.falloff_depth <= 1.0 + self.land_bias:
            raise ValueError(
                "falloff_depth must force the maximum base height below sea level"
            )


def _smoothstep(values: Float32Array, start: float, end: float) -> Float32Array:
    start_value = np.float32(start)
    extent = np.float32(end - start)
    progress = np.clip((values - start_value) / extent, 0.0, 1.0)
    return progress * progress * (np.float32(3.0) - np.float32(2.0) * progress)


def _island_falloff(config: LandformConfig) -> Float32Array:
    x = np.linspace(-1.0, 1.0, config.width, dtype=np.float32)
    y = np.linspace(-1.0, 1.0, config.height, dtype=np.float32)
    normalized_x = x / np.float32(config.island_radius_x)
    normalized_y = y / np.float32(config.island_radius_y)
    distance = np.sqrt(
        normalized_x[np.newaxis, :] ** 2 + normalized_y[:, np.newaxis] ** 2
    )
    return _smoothstep(
        distance, config.island_falloff_start, config.island_falloff_end
    )


def _coast_falloff(config: LandformConfig) -> Float32Array:
    x = np.linspace(0.0, 1.0, config.width, dtype=np.float32)
    y = np.linspace(0.0, 1.0, config.height, dtype=np.float32)

    if config.coast_edge is CoastEdge.EAST:
        sea_progress = x[np.newaxis, :]
    elif config.coast_edge is CoastEdge.WEST:
        sea_progress = (np.float32(1.0) - x)[np.newaxis, :]
    elif config.coast_edge is CoastEdge.NORTH:
        sea_progress = (np.float32(1.0) - y)[:, np.newaxis]
    else:
        sea_progress = y[:, np.newaxis]

    return _smoothstep(
        sea_progress, config.coast_falloff_start, config.coast_falloff_end
    )


def shape_landform(base_terrain: Float32Array, config: LandformConfig) -> Float32Array:
    """Apply the configured deterministic shaping field to layered terrain."""

    values = np.asarray(base_terrain)
    if values.shape != (config.height, config.width):
        raise ValueError("base terrain shape does not match LandformConfig")
    if values.dtype != np.dtype(np.float32):
        raise TypeError("base terrain must use float32")
    if not np.isfinite(values).all():
        raise ValueError("base terrain must contain only finite values")

    if config.mode is LandformMode.ISLAND:
        falloff = _island_falloff(config)
    else:
        falloff = _coast_falloff(config)

    shaped = (
        values
        + np.float32(config.land_bias)
        - falloff * np.float32(config.falloff_depth)
    )
    return np.ascontiguousarray(shaped, dtype=np.float32)


def generate_landform(config: LandformConfig) -> Float32Array:
    """Generate layered terrain and shape it into the requested landform."""

    base_terrain = generate_layered_terrain(
        LayeredTerrainConfig(
            seed=config.seed,
            width=config.width,
            height=config.height,
        )
    )
    return shape_landform(base_terrain, config)


def derive_land_water_masks(
    terrain: Float32Array,
) -> tuple[np.ndarray, np.ndarray]:
    """Return deterministic land (> 0) and water (<= 0) boolean masks."""

    values = np.asarray(terrain)
    if values.ndim != 2 or values.size == 0:
        raise ValueError("terrain must be a non-empty two-dimensional array")
    if not np.isfinite(values).all():
        raise ValueError("terrain must contain only finite values")

    land_mask = values > SEA_LEVEL
    water_mask = values <= SEA_LEVEL
    return land_mask, water_mask
