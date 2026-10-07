"""Generic deterministic landform shaping for procedural terrain."""

from __future__ import annotations

from collections import deque
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
_UINT64_MASK = (1 << 64) - 1


class LandformMode(str, Enum):
    ISLAND = "island"
    COAST = "coast"


class CoastEdge(str, Enum):
    EAST = "east"
    WEST = "west"
    NORTH = "north"
    SOUTH = "south"


@dataclass(frozen=True, slots=True)
class LandformMacroParameters:
    """Seed-derived controls used by the v1 island and coast falloff fields."""

    land_bias: float
    island_radius_x: float
    island_radius_y: float
    island_falloff_start: float
    island_center_offset_x: float
    island_center_offset_y: float
    coast_falloff_start: float
    coast_transition_width: float
    coast_directional_asymmetry: float


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


def _seed_float(base_seed: int, stream: int) -> float:
    """Map a signed seed and stream number to a stable float in [0, 1]."""

    value = (
        (base_seed & _UINT64_MASK)
        + 0x9E3779B97F4A7C15 * (stream + 1)
    ) & _UINT64_MASK
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _UINT64_MASK
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _UINT64_MASK
    value ^= value >> 31
    return ((value >> 40) & 0xFFFFFF) / float(0xFFFFFF)


def _seed_range(base_seed: int, stream: int, low: float, high: float) -> float:
    return low + (high - low) * _seed_float(base_seed, stream)


def derive_landform_macro_parameters(
    config: LandformConfig,
) -> LandformMacroParameters:
    """Derive conservative macro variation without using random global state.

    The ranges are offsets from the v1 configuration, so its public shaping
    controls remain useful. With the default configuration, island radii are
    0.86--0.94 and 0.84--0.94, island falloff starts are 0.68--0.80,
    land bias is 0.30--0.39, and center offsets are -0.05--0.05. Coast
    falloff starts are 0.50--0.68, transition widths are 0.22--0.30, and
    directional asymmetry is -0.06--0.06.
    """

    seed = config.seed
    land_bias = config.land_bias + _seed_range(seed, 0, 0.0, 0.09)
    # Retain the boundary guarantee even for a non-default but valid config.
    land_bias = min(land_bias, config.falloff_depth - 1.000001)

    center_x = _seed_range(seed, 4, -0.05, 0.05)
    center_y = _seed_range(seed, 5, -0.05, 0.05)
    radius_x = config.island_radius_x + _seed_range(seed, 1, -0.12, -0.04)
    radius_y = config.island_radius_y + _seed_range(seed, 2, -0.08, 0.02)
    radius_x = max(0.05, min(radius_x, 1.0 - abs(center_x)))
    radius_y = max(0.05, min(radius_y, 1.0 - abs(center_y)))
    island_start = config.island_falloff_start + _seed_range(
        seed, 3, 0.0, 0.12
    )
    island_start = max(0.0, min(island_start, config.island_falloff_end - 0.05))

    coast_start = config.coast_falloff_start + _seed_range(
        seed, 6, -0.15, 0.03
    )
    v1_transition_width = config.coast_falloff_end - config.coast_falloff_start
    coast_width = v1_transition_width + _seed_range(seed, 7, -0.13, -0.05)
    coast_start = max(0.0, min(coast_start, 0.95))
    coast_width = max(0.05, min(coast_width, 1.0 - coast_start))

    return LandformMacroParameters(
        land_bias=land_bias,
        island_radius_x=radius_x,
        island_radius_y=radius_y,
        island_falloff_start=island_start,
        island_center_offset_x=center_x,
        island_center_offset_y=center_y,
        coast_falloff_start=coast_start,
        coast_transition_width=coast_width,
        coast_directional_asymmetry=_seed_range(seed, 8, -0.06, 0.06),
    )


def _smoothstep(values: Float32Array, start: float, end: float) -> Float32Array:
    start_value = np.float32(start)
    extent = np.float32(end - start)
    progress = np.clip((values - start_value) / extent, 0.0, 1.0)
    return progress * progress * (np.float32(3.0) - np.float32(2.0) * progress)


def _island_falloff(
    config: LandformConfig, macro: LandformMacroParameters
) -> Float32Array:
    x = np.linspace(-1.0, 1.0, config.width, dtype=np.float32)
    y = np.linspace(-1.0, 1.0, config.height, dtype=np.float32)
    normalized_x = (
        x - np.float32(macro.island_center_offset_x)
    ) / np.float32(macro.island_radius_x)
    normalized_y = (
        y - np.float32(macro.island_center_offset_y)
    ) / np.float32(macro.island_radius_y)
    distance = np.sqrt(
        normalized_x[np.newaxis, :] ** 2 + normalized_y[:, np.newaxis] ** 2
    )
    return _smoothstep(
        distance, macro.island_falloff_start, config.island_falloff_end
    )


def _coast_falloff(
    config: LandformConfig, macro: LandformMacroParameters
) -> Float32Array:
    x = np.linspace(0.0, 1.0, config.width, dtype=np.float32)
    y = np.linspace(0.0, 1.0, config.height, dtype=np.float32)

    if config.coast_edge is CoastEdge.EAST:
        sea_progress = x[np.newaxis, :]
        cross_progress = (np.float32(2.0) * y - np.float32(1.0))[:, np.newaxis]
    elif config.coast_edge is CoastEdge.WEST:
        sea_progress = (np.float32(1.0) - x)[np.newaxis, :]
        cross_progress = (np.float32(2.0) * y - np.float32(1.0))[:, np.newaxis]
    elif config.coast_edge is CoastEdge.NORTH:
        sea_progress = (np.float32(1.0) - y)[:, np.newaxis]
        cross_progress = (np.float32(2.0) * x - np.float32(1.0))[np.newaxis, :]
    else:
        sea_progress = y[:, np.newaxis]
        cross_progress = (np.float32(2.0) * x - np.float32(1.0))[np.newaxis, :]

    # Fade the slant to zero at the sea edge so that edge remains uniformly
    # submerged, while seeds still change how the sea enters the map.
    sea_progress = sea_progress + (
        np.float32(macro.coast_directional_asymmetry)
        * cross_progress
        * (np.float32(1.0) - sea_progress)
    )
    coast_end = macro.coast_falloff_start + macro.coast_transition_width

    return _smoothstep(
        sea_progress, macro.coast_falloff_start, coast_end
    )


def _retain_dominant_landmass(values: Float32Array) -> Float32Array:
    """Submerge detached land while preserving the largest 4-connected mass."""

    land = values > SEA_LEVEL
    unvisited = land.copy()
    height, width = land.shape
    largest_component: list[tuple[int, int]] = []

    for start_y, start_x in np.argwhere(unvisited):
        start_y = int(start_y)
        start_x = int(start_x)
        if not unvisited[start_y, start_x]:
            continue
        unvisited[start_y, start_x] = False
        component = [(start_y, start_x)]
        queue = deque(component)
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
                    and unvisited[neighbor_y, neighbor_x]
                ):
                    unvisited[neighbor_y, neighbor_x] = False
                    component.append((neighbor_y, neighbor_x))
                    queue.append((neighbor_y, neighbor_x))
        if len(component) > len(largest_component):
            largest_component = component

    if not largest_component or len(largest_component) == int(land.sum()):
        return values

    retained = np.zeros(land.shape, dtype=np.bool_)
    component_y, component_x = zip(*largest_component)
    retained[component_y, component_x] = True
    result = values.copy()
    result[land & ~retained] = np.float32(-1e-6)
    return result


def shape_landform(base_terrain: Float32Array, config: LandformConfig) -> Float32Array:
    """Apply the configured deterministic shaping field to layered terrain."""

    values = np.asarray(base_terrain)
    if values.shape != (config.height, config.width):
        raise ValueError("base terrain shape does not match LandformConfig")
    if values.dtype != np.dtype(np.float32):
        raise TypeError("base terrain must use float32")
    if not np.isfinite(values).all():
        raise ValueError("base terrain must contain only finite values")

    macro = derive_landform_macro_parameters(config)
    if config.mode is LandformMode.ISLAND:
        falloff = _island_falloff(config, macro)
    else:
        falloff = _coast_falloff(config, macro)

    shaped = (
        values
        + np.float32(macro.land_bias)
        - falloff * np.float32(config.falloff_depth)
    )
    shaped = np.ascontiguousarray(shaped, dtype=np.float32)
    return np.ascontiguousarray(_retain_dominant_landmass(shaped), dtype=np.float32)


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
