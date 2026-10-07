"""Experimental graph-guided macro land/water generation.

This module is deliberately isolated from the stable terrain and Landform v2
pipeline.  It generates only a signed landness field and a binary land mask;
it does not generate elevation or game-specific data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import time
from typing import Iterable

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage
from scipy.interpolate import RBFInterpolator
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


Float32Array = NDArray[np.float32]
BoolArray = NDArray[np.bool_]

_UINT64_MASK = (1 << 64) - 1
_MIN_SEED = -(2**31)
_MAX_SEED = 2**31 - 1
_FOUR_CONNECTED = np.array(
    [[False, True, False], [True, True, True], [False, True, False]],
    dtype=np.bool_,
)


class MacroLandformPreset(str, Enum):
    """Proof presets supported by the isolated prototype."""

    ISLAND = "island"
    MAINLAND_COAST_EAST = "mainland_coast_east"
    PENINSULA_EAST = "peninsula_east"


class MacroRasterizer(str, Enum):
    """Continuous-field implementations compared by the prototype."""

    GAUSSIAN = "gaussian"
    RBF = "rbf"


class AnchorRole(str, Enum):
    PRIMARY_MASS = "primary_mass"
    SECONDARY_MASS = "secondary_mass"
    HEADLAND = "headland"
    PENINSULA_SUPPORT = "peninsula_support"
    MAINLAND_SUPPORT = "mainland_support"
    BOUNDARY_SUPPORT = "boundary_support"
    BAY = "bay"
    CHANNEL = "channel"
    OPEN_WATER_GUARD = "open_water_guard"


class MapEdge(str, Enum):
    NORTH = "north"
    EAST = "east"
    SOUTH = "south"
    WEST = "west"


class BoundaryRule(str, Enum):
    REQUIRED_LAND = "required_land"
    REQUIRED_WATER = "required_water"
    UNCONSTRAINED = "unconstrained"


@dataclass(frozen=True, slots=True)
class MacroAnchor:
    """One normalized signed control point in a macro plan."""

    identifier: str
    x: float
    y: float
    role: AnchorRole
    radius: float
    strength: float
    positive: bool
    size_class: int


@dataclass(frozen=True, slots=True)
class MacroConnection:
    """A required land corridor or water channel between two anchors."""

    identifier: str
    start_anchor: str
    end_anchor: str
    width: float
    strength: float
    positive: bool


@dataclass(frozen=True, slots=True)
class BoundaryCondition:
    edge: MapEdge
    rule: BoundaryRule


@dataclass(frozen=True, slots=True)
class MacroLandformPlan:
    """Resolution-independent, inspectable inputs to field rasterization."""

    base_seed: int
    preset: MacroLandformPreset
    anchors: tuple[MacroAnchor, ...]
    connections: tuple[MacroConnection, ...]
    boundaries: tuple[BoundaryCondition, ...]
    derived_subseeds: tuple[tuple[str, int], ...]
    generation_parameters: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class MacroLandformConfig:
    """Configuration for one prototype raster."""

    seed: int
    preset: MacroLandformPreset
    rasterizer: MacroRasterizer = MacroRasterizer.GAUSSIAN
    width: int = 512
    height: int = 512
    threshold: float = 0.0
    gaussian_truncate: float = 3.5
    rbf_epsilon: float = 4.5
    rbf_smoothing: float = 0.140
    neck_radius_fraction: float = 0.018

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        if not _MIN_SEED <= self.seed <= _MAX_SEED:
            raise ValueError("seed must fit in a signed 32-bit integer")
        if not isinstance(self.preset, MacroLandformPreset):
            raise TypeError("preset must be a MacroLandformPreset")
        if not isinstance(self.rasterizer, MacroRasterizer):
            raise TypeError("rasterizer must be a MacroRasterizer")
        for name, value in (("width", self.width), ("height", self.height)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 32:
                raise ValueError(f"{name} must be at least 32")
        for name, value in (
            ("threshold", self.threshold),
            ("gaussian_truncate", self.gaussian_truncate),
            ("rbf_epsilon", self.rbf_epsilon),
            ("rbf_smoothing", self.rbf_smoothing),
            ("neck_radius_fraction", self.neck_radius_fraction),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.gaussian_truncate <= 0:
            raise ValueError("gaussian_truncate must be positive")
        if self.rbf_epsilon <= 0:
            raise ValueError("rbf_epsilon must be positive")
        if self.rbf_smoothing < 0:
            raise ValueError("rbf_smoothing must be non-negative")
        if not 0 < self.neck_radius_fraction < 0.1:
            raise ValueError("neck_radius_fraction must be in (0, 0.1)")


@dataclass(frozen=True, slots=True)
class MacroLandformMetrics:
    land_coverage_percent: float
    land_component_count: int
    largest_component_percent: float
    boundary_rules_pass: bool
    intended_main_graph_connected: bool
    eroded_component_count: int
    minimum_neck_pass: bool
    coastline_perimeter_area_proxy: float
    eastward_projection_fraction: float
    peninsula_water_flanks_pass: bool
    inland_water_component_count: int
    cleanup_land_pixels_removed: int
    cleanup_land_percent_removed: float
    generation_runtime_seconds: float
    accepted: bool
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MacroLandformResult:
    plan: MacroLandformPlan
    landness: Float32Array
    land_mask: BoolArray
    metrics: MacroLandformMetrics


def _fnv1a_64(text: str) -> int:
    value = 0xCBF29CE484222325
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 0x100000001B3) & _UINT64_MASK
    return value


def derive_macro_subseed(base_seed: int, stream_name: str) -> int:
    """Derive a stable unsigned 64-bit sub-seed using FNV-1a and SplitMix64."""

    if isinstance(base_seed, bool) or not isinstance(base_seed, int):
        raise TypeError("base_seed must be an integer")
    if not _MIN_SEED <= base_seed <= _MAX_SEED:
        raise ValueError("base_seed must fit in a signed 32-bit integer")
    if not stream_name:
        raise ValueError("stream_name must not be empty")

    value = ((base_seed & _UINT64_MASK) ^ _fnv1a_64(stream_name)) & _UINT64_MASK
    value = (value + 0x9E3779B97F4A7C15) & _UINT64_MASK
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _UINT64_MASK
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _UINT64_MASK
    return (value ^ (value >> 31)) & _UINT64_MASK


def _local_rng(base_seed: int, stream_name: str) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(derive_macro_subseed(base_seed, stream_name)))


def _anchor(
    identifier: str,
    point: NDArray[np.floating],
    role: AnchorRole,
    radius: float,
    strength: float,
    positive: bool,
    size_class: int,
) -> MacroAnchor:
    return MacroAnchor(
        identifier=identifier,
        x=float(np.clip(point[0], 0.0, 1.0)),
        y=float(np.clip(point[1], 0.0, 1.0)),
        role=role,
        radius=float(radius),
        strength=float(strength),
        positive=positive,
        size_class=size_class,
    )


def _connection(
    identifier: str,
    start: MacroAnchor,
    end: MacroAnchor,
    width: float,
    strength: float,
    positive: bool,
) -> MacroConnection:
    return MacroConnection(
        identifier=identifier,
        start_anchor=start.identifier,
        end_anchor=end.identifier,
        width=float(width),
        strength=float(strength),
        positive=positive,
    )


def _island_plan(seed: int) -> tuple[
    list[MacroAnchor], list[MacroConnection], dict[str, float]
]:
    layout_rng = _local_rng(seed, "macro.island.layout.v01")
    detail_rng = _local_rng(seed, "macro.island.details.v01")
    negative_rng = _local_rng(seed, "macro.island.negative.v01")

    radii = (0.090, 0.125, 0.165)
    backbone_count = int(layout_rng.integers(5, 8))
    branch_count = int(layout_rng.integers(1, 4))
    angle = float(layout_rng.uniform(0.0, math.pi))
    direction = np.array([math.cos(angle), math.sin(angle)], dtype=np.float64)
    perpendicular = np.array([-direction[1], direction[0]], dtype=np.float64)
    span = float(layout_rng.uniform(0.46, 0.66))
    bend = float(layout_rng.uniform(-0.18, 0.18))
    wave = float(layout_rng.uniform(-0.075, 0.075))
    center = np.array(
        [layout_rng.uniform(0.44, 0.56), layout_rng.uniform(0.44, 0.56)],
        dtype=np.float64,
    )

    anchors: list[MacroAnchor] = []
    connections: list[MacroConnection] = []
    backbone: list[MacroAnchor] = []
    for index, t in enumerate(np.linspace(-1.0, 1.0, backbone_count)):
        curve = bend * (t * t - 0.35) + wave * math.sin(math.pi * t)
        jitter = perpendicular * float(detail_rng.uniform(-0.025, 0.025))
        point = center + direction * (0.5 * span * t) + perpendicular * curve + jitter
        point = np.clip(point, 0.14, 0.86)
        size_class = int(detail_rng.choice(3, p=(0.20, 0.55, 0.25)))
        if index in (0, backbone_count - 1):
            role = AnchorRole.HEADLAND
        elif index == backbone_count // 2:
            role = AnchorRole.PRIMARY_MASS
            size_class = max(size_class, 1)
        else:
            role = AnchorRole.SECONDARY_MASS
        item = _anchor(
            f"land_backbone_{index}",
            point,
            role,
            radii[size_class],
            detail_rng.uniform(0.90, 1.12),
            True,
            size_class,
        )
        anchors.append(item)
        backbone.append(item)
        if index:
            previous = backbone[index - 1]
            connections.append(
                _connection(
                    f"land_backbone_link_{index - 1}",
                    previous,
                    item,
                    min(previous.radius, item.radius) * 0.62,
                    0.82,
                    True,
                )
            )

    for index in range(branch_count):
        parent_index = int(detail_rng.integers(1, backbone_count - 1))
        parent = backbone[parent_index]
        side = -1.0 if detail_rng.random() < 0.5 else 1.0
        distance = float(detail_rng.uniform(0.13, 0.23))
        along = direction * float(detail_rng.uniform(-0.055, 0.055))
        point = np.array([parent.x, parent.y]) + side * perpendicular * distance + along
        point = np.clip(point, 0.14, 0.86)
        size_class = int(detail_rng.choice((0, 1), p=(0.35, 0.65)))
        branch = _anchor(
            f"land_branch_{index}",
            point,
            AnchorRole.HEADLAND,
            radii[size_class],
            detail_rng.uniform(0.82, 1.02),
            True,
            size_class,
        )
        anchors.append(branch)
        connections.append(
            _connection(
                f"land_branch_link_{index}",
                parent,
                branch,
                min(parent.radius, branch.radius) * 0.58,
                0.76,
                True,
            )
        )

    bay_count = int(negative_rng.integers(1, 3))
    for index in range(bay_count):
        segment = int(negative_rng.integers(0, backbone_count - 1))
        first = backbone[segment]
        second = backbone[segment + 1]
        midpoint = np.array([(first.x + second.x) * 0.5, (first.y + second.y) * 0.5])
        side = -1.0 if negative_rng.random() < 0.5 else 1.0
        point = midpoint + side * perpendicular * negative_rng.uniform(0.105, 0.155)
        point += direction * negative_rng.uniform(-0.035, 0.035)
        point = np.clip(point, 0.08, 0.92)
        size_class = int(negative_rng.choice((0, 1), p=(0.45, 0.55)))
        bay = _anchor(
            f"water_bay_{index}",
            point,
            AnchorRole.BAY,
            (0.075, 0.105)[size_class],
            negative_rng.uniform(0.62, 0.82),
            False,
            size_class,
        )
        outward = side * perpendicular
        boundary_steps: list[float] = []
        for coordinate, component in zip(point, outward, strict=True):
            if component > 1e-9:
                boundary_steps.append((0.98 - coordinate) / component)
            elif component < -1e-9:
                boundary_steps.append((0.02 - coordinate) / component)
        positive_steps = [step for step in boundary_steps if step > 0.0]
        step = min(positive_steps) if positive_steps else 0.25
        guard_point = np.clip(point + outward * step, 0.02, 0.98)
        guard = _anchor(
            f"water_guard_{index}",
            guard_point,
            AnchorRole.OPEN_WATER_GUARD,
            (0.090, 0.115)[size_class],
            negative_rng.uniform(0.90, 1.05),
            False,
            size_class,
        )
        anchors.extend((bay, guard))
        connections.append(
            _connection(
                f"water_bay_channel_{index}",
                bay,
                guard,
                negative_rng.uniform(0.060, 0.085),
                1.35,
                False,
            )
        )

    parameters = {
        "field_bias": -0.34,
        "boundary_guard_width": 0.105,
        "boundary_guard_strength": 1.25,
        "coverage_min": 0.18,
        "coverage_max": 0.65,
        "layout_angle": angle,
        "layout_span": span,
        "layout_bend": bend,
    }
    return anchors, connections, parameters


def _mainland_plan(seed: int) -> tuple[
    list[MacroAnchor], list[MacroConnection], dict[str, float]
]:
    layout_rng = _local_rng(seed, "macro.mainland.layout.v01")
    detail_rng = _local_rng(seed, "macro.mainland.details.v01")
    negative_rng = _local_rng(seed, "macro.mainland.negative.v01")
    radii = (0.125, 0.175, 0.230)

    anchors: list[MacroAnchor] = []
    connections: list[MacroConnection] = []
    supports: list[MacroAnchor] = []
    support_count = 4
    vertical_offset = float(layout_rng.uniform(-0.055, 0.055))
    for index, y in enumerate(np.linspace(0.10, 0.90, support_count)):
        point = np.array(
            [layout_rng.uniform(0.015, 0.075), np.clip(y + vertical_offset, 0.06, 0.94)]
        )
        item = _anchor(
            f"mainland_support_{index}",
            point,
            AnchorRole.MAINLAND_SUPPORT,
            radii[2],
            detail_rng.uniform(0.98, 1.16),
            True,
            2,
        )
        anchors.append(item)
        supports.append(item)
        if index:
            connections.append(
                _connection(
                    f"mainland_spine_{index - 1}",
                    supports[index - 1],
                    item,
                    0.155,
                    0.88,
                    True,
                )
            )

    headland_count = int(layout_rng.integers(3, 6))
    headlands: list[MacroAnchor] = []
    base_ys = np.linspace(0.14, 0.86, headland_count)
    for index, base_y in enumerate(base_ys):
        y = float(np.clip(base_y + layout_rng.uniform(-0.10, 0.10), 0.09, 0.91))
        x = float(layout_rng.uniform(0.40, 0.72))
        size_class = int(detail_rng.choice((0, 1), p=(0.30, 0.70)))
        item = _anchor(
            f"coastal_headland_{index}",
            np.array([x, y]),
            AnchorRole.HEADLAND,
            radii[size_class],
            detail_rng.uniform(0.88, 1.10),
            True,
            size_class,
        )
        anchors.append(item)
        headlands.append(item)
        parent = min(supports, key=lambda anchor: (abs(anchor.y - y), anchor.identifier))
        connections.append(
            _connection(
                f"headland_link_{index}",
                parent,
                item,
                min(0.125, item.radius * 0.72),
                0.83,
                True,
            )
        )

    channel_count = int(negative_rng.integers(1, 3))
    sorted_headlands = sorted(headlands, key=lambda anchor: (anchor.y, anchor.identifier))
    gaps = [
        (sorted_headlands[index].y + sorted_headlands[index + 1].y) * 0.5
        for index in range(len(sorted_headlands) - 1)
    ]
    negative_rng.shuffle(gaps)
    for index, y in enumerate(gaps[:channel_count]):
        inner = _anchor(
            f"bay_inner_{index}",
            np.array([negative_rng.uniform(0.43, 0.57), y]),
            AnchorRole.BAY,
            negative_rng.choice((0.105, 0.140)),
            negative_rng.uniform(0.72, 0.92),
            False,
            1,
        )
        outer = _anchor(
            f"bay_guard_{index}",
            np.array([0.965, np.clip(y + negative_rng.uniform(-0.035, 0.035), 0.04, 0.96)]),
            AnchorRole.OPEN_WATER_GUARD,
            0.140,
            1.05,
            False,
            1,
        )
        anchors.extend((inner, outer))
        connections.append(
            _connection(
                f"bay_channel_{index}",
                inner,
                outer,
                0.055,
                2.60,
                False,
            )
        )

    parameters = {
        "field_bias": -0.23,
        "boundary_guard_width": 0.075,
        "boundary_guard_strength": 1.30,
        "boundary_land_width": 0.050,
        "boundary_land_strength": 0.72,
        "coverage_min": 0.34,
        "coverage_max": 0.90,
        "vertical_offset": vertical_offset,
    }
    return anchors, connections, parameters


def _peninsula_plan(seed: int) -> tuple[
    list[MacroAnchor], list[MacroConnection], dict[str, float]
]:
    layout_rng = _local_rng(seed, "macro.peninsula.layout.v01")
    detail_rng = _local_rng(seed, "macro.peninsula.details.v01")
    negative_rng = _local_rng(seed, "macro.peninsula.negative.v01")
    radii = (0.095, 0.135, 0.205)

    anchors: list[MacroAnchor] = []
    connections: list[MacroConnection] = []
    supports: list[MacroAnchor] = []
    center_y = float(layout_rng.uniform(0.42, 0.58))
    for index, y in enumerate((0.16, 0.50, 0.84)):
        point = np.array([layout_rng.uniform(0.02, 0.065), y])
        item = _anchor(
            f"mainland_support_{index}",
            point,
            AnchorRole.MAINLAND_SUPPORT,
            radii[2],
            detail_rng.uniform(0.98, 1.14),
            True,
            2,
        )
        anchors.append(item)
        supports.append(item)
        if index:
            connections.append(
                _connection(
                    f"mainland_spine_{index - 1}",
                    supports[index - 1],
                    item,
                    0.145,
                    0.86,
                    True,
                )
            )

    junction = _anchor(
        "peninsula_junction",
        np.array([0.225, center_y]),
        AnchorRole.PENINSULA_SUPPORT,
        radii[2],
        1.08,
        True,
        2,
    )
    anchors.append(junction)
    parent = min(supports, key=lambda anchor: (abs(anchor.y - center_y), anchor.identifier))
    connections.append(
        _connection("peninsula_junction_link", parent, junction, 0.135, 0.88, True)
    )

    backbone_count = int(layout_rng.integers(4, 7))
    tip_x = float(layout_rng.uniform(0.73, 0.87))
    curve = float(layout_rng.uniform(-0.12, 0.12))
    wave = float(layout_rng.uniform(-0.055, 0.055))
    previous = junction
    peninsula_points: list[MacroAnchor] = []
    for index, t in enumerate(np.linspace(0.18, 1.0, backbone_count)):
        x = 0.225 + (tip_x - 0.225) * t
        y = center_y + curve * (t * t - 0.2 * t) + wave * math.sin(2.0 * math.pi * t)
        y += detail_rng.uniform(-0.018, 0.018)
        size_class = 1 if index < backbone_count - 1 else 0
        role = AnchorRole.HEADLAND if index == backbone_count - 1 else AnchorRole.PENINSULA_SUPPORT
        item = _anchor(
            f"peninsula_backbone_{index}",
            np.array([x, np.clip(y, 0.22, 0.78)]),
            role,
            radii[size_class],
            detail_rng.uniform(0.94, 1.10),
            True,
            size_class,
        )
        anchors.append(item)
        peninsula_points.append(item)
        connections.append(
            _connection(
                f"peninsula_link_{index}",
                previous,
                item,
                0.088 if index < backbone_count - 1 else 0.075,
                0.90,
                True,
            )
        )
        previous = item

    for side_name, side in (("north", -1.0), ("south", 1.0)):
        first_index = max(0, backbone_count // 3 - 1)
        second_index = min(backbone_count - 1, backbone_count - 2)
        first_land = peninsula_points[first_index]
        second_land = peninsula_points[second_index]
        offset = negative_rng.uniform(0.155, 0.205)
        inner = _anchor(
            f"{side_name}_channel_inner",
            np.array([max(0.37, first_land.x), np.clip(first_land.y + side * offset, 0.05, 0.95)]),
            AnchorRole.CHANNEL,
            0.100,
            negative_rng.uniform(0.66, 0.82),
            False,
            0,
        )
        outer = _anchor(
            f"{side_name}_channel_outer",
            np.array([min(0.90, second_land.x + 0.08), np.clip(second_land.y + side * offset, 0.05, 0.95)]),
            AnchorRole.OPEN_WATER_GUARD,
            0.145,
            negative_rng.uniform(0.95, 1.10),
            False,
            1,
        )
        anchors.extend((inner, outer))
        connections.append(
            _connection(
                f"{side_name}_water_lane",
                inner,
                outer,
                0.085,
                0.86,
                False,
            )
        )

    # Explicit outer-water guards suppress RBF extrapolation lobes beyond the
    # two flanking channels.  They are plan data, not hidden raster cleanup.
    anchors.extend(
        (
            _anchor(
                "north_outer_guard",
                np.array([0.62, 0.03]),
                AnchorRole.OPEN_WATER_GUARD,
                0.160,
                1.05,
                False,
                2,
            ),
            _anchor(
                "south_outer_guard",
                np.array([0.62, 0.97]),
                AnchorRole.OPEN_WATER_GUARD,
                0.160,
                1.05,
                False,
                2,
            ),
        )
    )

    parameters = {
        "field_bias": -0.27,
        "boundary_guard_width": 0.070,
        "boundary_guard_strength": 1.30,
        "boundary_land_width": 0.045,
        "boundary_land_strength": 0.70,
        "coverage_min": 0.22,
        "coverage_max": 0.68,
        "peninsula_tip_x": tip_x,
        "peninsula_curve": curve,
    }
    return anchors, connections, parameters


def generate_macro_landform_plan(config: MacroLandformConfig) -> MacroLandformPlan:
    """Generate the resolution-independent anchor and connection plan."""

    if config.preset is MacroLandformPreset.ISLAND:
        anchors, connections, parameters = _island_plan(config.seed)
        boundaries = tuple(
            BoundaryCondition(edge, BoundaryRule.REQUIRED_WATER) for edge in MapEdge
        )
        stream_prefix = "macro.island"
    elif config.preset is MacroLandformPreset.MAINLAND_COAST_EAST:
        anchors, connections, parameters = _mainland_plan(config.seed)
        boundaries = (
            BoundaryCondition(MapEdge.NORTH, BoundaryRule.UNCONSTRAINED),
            BoundaryCondition(MapEdge.EAST, BoundaryRule.REQUIRED_WATER),
            BoundaryCondition(MapEdge.SOUTH, BoundaryRule.UNCONSTRAINED),
            BoundaryCondition(MapEdge.WEST, BoundaryRule.REQUIRED_LAND),
        )
        stream_prefix = "macro.mainland"
    else:
        anchors, connections, parameters = _peninsula_plan(config.seed)
        boundaries = (
            BoundaryCondition(MapEdge.NORTH, BoundaryRule.UNCONSTRAINED),
            BoundaryCondition(MapEdge.EAST, BoundaryRule.REQUIRED_WATER),
            BoundaryCondition(MapEdge.SOUTH, BoundaryRule.UNCONSTRAINED),
            BoundaryCondition(MapEdge.WEST, BoundaryRule.REQUIRED_LAND),
        )
        stream_prefix = "macro.peninsula"

    subseeds = tuple(
        (name, derive_macro_subseed(config.seed, f"{stream_prefix}.{name}.v01"))
        for name in ("layout", "details", "negative")
    )
    return MacroLandformPlan(
        base_seed=config.seed,
        preset=config.preset,
        anchors=tuple(anchors),
        connections=tuple(connections),
        boundaries=boundaries,
        derived_subseeds=subseeds,
        generation_parameters=tuple(sorted(parameters.items())),
    )


def _parameters(plan: MacroLandformPlan) -> dict[str, float]:
    return dict(plan.generation_parameters)


def _anchor_lookup(plan: MacroLandformPlan) -> dict[str, MacroAnchor]:
    return {anchor.identifier: anchor for anchor in plan.anchors}


def _raster_point(anchor: MacroAnchor, width: int, height: int) -> tuple[int, int]:
    return (
        int(round(anchor.y * (height - 1))),
        int(round(anchor.x * (width - 1))),
    )


def _line_mask(
    connections: Iterable[MacroConnection],
    anchors: dict[str, MacroAnchor],
    width: int,
    height: int,
) -> BoolArray:
    mask = np.zeros((height, width), dtype=np.bool_)
    for connection in connections:
        start = anchors[connection.start_anchor]
        end = anchors[connection.end_anchor]
        pixel_distance = math.hypot(
            (end.x - start.x) * (width - 1),
            (end.y - start.y) * (height - 1),
        )
        sample_count = max(2, int(math.ceil(pixel_distance)) + 1)
        xs = np.rint(np.linspace(start.x, end.x, sample_count) * (width - 1)).astype(int)
        ys = np.rint(np.linspace(start.y, end.y, sample_count) * (height - 1)).astype(int)
        mask[ys, xs] = True
    return ndimage.binary_dilation(mask, structure=_FOUR_CONNECTED, iterations=1)


def _gaussian_anchor_field(
    plan: MacroLandformPlan, width: int, height: int, truncate: float
) -> Float32Array:
    field = np.zeros((height, width), dtype=np.float32)
    grouped: dict[tuple[bool, float], list[MacroAnchor]] = {}
    for anchor in plan.anchors:
        grouped.setdefault((anchor.positive, anchor.radius), []).append(anchor)

    for (positive, radius), anchors in sorted(grouped.items(), key=lambda item: item[0]):
        impulses = np.zeros((height, width), dtype=np.float32)
        for anchor in anchors:
            y, x = _raster_point(anchor, width, height)
            impulses[y, x] += np.float32(anchor.strength)
        sigma_y = max(0.75, radius * (height - 1))
        sigma_x = max(0.75, radius * (width - 1))
        blurred = ndimage.gaussian_filter(
            impulses,
            sigma=(sigma_y, sigma_x),
            mode="constant",
            cval=0.0,
            truncate=truncate,
            output=np.float32,
        )
        amplitude_scale = np.float32(2.0 * math.pi * sigma_x * sigma_y)
        if positive:
            field += blurred * amplitude_scale
        else:
            field -= blurred * amplitude_scale
    return field


def _corridor_field(
    plan: MacroLandformPlan,
    width: int,
    height: int,
    polarity: bool | None = None,
) -> Float32Array:
    field = np.zeros((height, width), dtype=np.float32)
    anchors = _anchor_lookup(plan)
    grouped: dict[tuple[bool, float, float], list[MacroConnection]] = {}
    for connection in plan.connections:
        if polarity is not None and connection.positive is not polarity:
            continue
        key = (connection.positive, connection.width, connection.strength)
        grouped.setdefault(key, []).append(connection)

    sampling = (1.0 / (height - 1), 1.0 / (width - 1))
    for (positive, corridor_width, strength), connections in sorted(
        grouped.items(), key=lambda item: item[0]
    ):
        line = _line_mask(connections, anchors, width, height)
        distance = ndimage.distance_transform_edt(~line, sampling=sampling)
        contribution = np.exp(
            -0.5 * np.square(distance / corridor_width)
        ).astype(np.float32)
        contribution *= np.float32(strength)
        if positive:
            field += contribution
        else:
            field -= contribution
    return field


def _boundary_field(
    plan: MacroLandformPlan, width: int, height: int
) -> Float32Array:
    parameters = _parameters(plan)
    water_width = parameters["boundary_guard_width"]
    water_strength = parameters["boundary_guard_strength"]
    land_width = parameters.get("boundary_land_width", water_width)
    land_strength = parameters.get("boundary_land_strength", 0.0)
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[np.newaxis, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, np.newaxis]
    field = np.zeros((height, width), dtype=np.float32)

    edge_distance = {
        MapEdge.NORTH: y,
        MapEdge.SOUTH: np.float32(1.0) - y,
        MapEdge.WEST: x,
        MapEdge.EAST: np.float32(1.0) - x,
    }
    for boundary in plan.boundaries:
        if boundary.rule is BoundaryRule.UNCONSTRAINED:
            continue
        distance = edge_distance[boundary.edge]
        if boundary.rule is BoundaryRule.REQUIRED_WATER:
            progress = np.clip(
                (np.float32(water_width) - distance) / np.float32(water_width),
                0.0,
                1.0,
            )
            field -= np.float32(water_strength) * progress * progress
        else:
            # Localize required-land support around explicit mainland anchors.
            # A full positive edge strip would quietly reintroduce a coast ramp.
            supports = [
                anchor
                for anchor in plan.anchors
                if anchor.positive
                and anchor.role
                in (AnchorRole.MAINLAND_SUPPORT, AnchorRole.BOUNDARY_SUPPORT)
            ]
            cross_coordinate = (
                y if boundary.edge in (MapEdge.WEST, MapEdge.EAST) else x
            )
            for support in supports:
                cross_center = (
                    support.y
                    if boundary.edge in (MapEdge.WEST, MapEdge.EAST)
                    else support.x
                )
                cross_radius = max(support.radius, 0.12)
                edge_progress = np.clip(
                    (np.float32(land_width) - distance) / np.float32(land_width),
                    0.0,
                    1.0,
                )
                cross_progress = np.exp(
                    -0.5
                    * np.square((cross_coordinate - cross_center) / cross_radius)
                ).astype(np.float32)
                field += (
                    np.float32(land_strength)
                    * edge_progress
                    * edge_progress
                    * cross_progress
                )
    return field


def _rbf_observations(plan: MacroLandformPlan) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    points: list[tuple[float, float]] = []
    values: list[float] = []
    lookup = _anchor_lookup(plan)

    for anchor in plan.anchors:
        sign = 1.0 if anchor.positive else -1.0
        positive_scale = 1.35 if anchor.positive else 1.0
        points.append((anchor.x, anchor.y))
        values.append(sign * anchor.strength * positive_scale)
        ring_value = sign * anchor.strength * (0.56 if anchor.positive else 0.46)
        for angle in (0.0, 0.5 * math.pi, math.pi, 1.5 * math.pi):
            point = (
                float(np.clip(anchor.x + anchor.radius * math.cos(angle), 0.0, 1.0)),
                float(np.clip(anchor.y + anchor.radius * math.sin(angle), 0.0, 1.0)),
            )
            points.append(point)
            values.append(ring_value)

    for connection in plan.connections:
        start = lookup[connection.start_anchor]
        end = lookup[connection.end_anchor]
        sign = 1.0 if connection.positive else -1.0
        positive_scale = 1.22 if connection.positive else 1.0
        effective_strength = (
            connection.strength
            if connection.positive
            else min(connection.strength, 1.0)
        )
        dx = end.x - start.x
        dy = end.y - start.y
        length = math.hypot(dx, dy)
        normal = (-dy / length, dx / length) if length else (0.0, 0.0)
        for t in (0.25, 0.50, 0.75):
            x = start.x + dx * t
            y = start.y + dy * t
            points.append((x, y))
            values.append(sign * effective_strength * positive_scale)
            for side in (-1.0, 1.0):
                points.append(
                    (
                        float(np.clip(x + normal[0] * connection.width, 0.0, 1.0)),
                        float(np.clip(y + normal[1] * connection.width, 0.0, 1.0)),
                    )
                )
                values.append(
                    sign
                    * effective_strength
                    * (0.52 if connection.positive else 0.42)
                )

    for boundary in plan.boundaries:
        if boundary.rule is BoundaryRule.UNCONSTRAINED:
            continue
        value = 1.05 if boundary.rule is BoundaryRule.REQUIRED_LAND else -1.05
        for t in np.linspace(0.0, 1.0, 9):
            if boundary.edge is MapEdge.NORTH:
                point = (float(t), 0.0)
            elif boundary.edge is MapEdge.SOUTH:
                point = (float(t), 1.0)
            elif boundary.edge is MapEdge.WEST:
                point = (0.0, float(t))
            else:
                point = (1.0, float(t))
            points.append(point)
            values.append(value)

    # Rounding makes deterministic de-duplication robust where rings meet edges.
    combined: dict[tuple[float, float], list[float]] = {}
    for point, value in zip(points, values, strict=True):
        key = (round(point[0], 12), round(point[1], 12))
        combined.setdefault(key, []).append(value)
    ordered = sorted(combined.items())
    unique_points = np.array([item[0] for item in ordered], dtype=np.float64)
    unique_values = np.array(
        [sum(item[1]) / len(item[1]) for item in ordered], dtype=np.float64
    )
    return unique_points, unique_values


def _rbf_field(plan: MacroLandformPlan, config: MacroLandformConfig) -> Float32Array:
    points, values = _rbf_observations(plan)
    interpolator = RBFInterpolator(
        points,
        values,
        kernel="gaussian",
        epsilon=config.rbf_epsilon,
        smoothing=config.rbf_smoothing,
        degree=-1,
    )
    x = np.linspace(0.0, 1.0, config.width, dtype=np.float64)
    y = np.linspace(0.0, 1.0, config.height, dtype=np.float64)
    field = np.empty((config.height, config.width), dtype=np.float32)
    chunk_rows = max(1, min(64, 2_000_000 // config.width))
    for start in range(0, config.height, chunk_rows):
        end = min(config.height, start + chunk_rows)
        grid_x, grid_y = np.meshgrid(x, y[start:end])
        samples = np.column_stack((grid_x.ravel(), grid_y.ravel()))
        field[start:end] = interpolator(samples).reshape(end - start, config.width)
    return field


def _hard_enforce_boundaries(
    landness: Float32Array, plan: MacroLandformPlan
) -> None:
    water_value = np.float32(-1.0)
    land_value = np.float32(0.35)
    for boundary in plan.boundaries:
        if boundary.rule is BoundaryRule.UNCONSTRAINED:
            continue
        value = water_value if boundary.rule is BoundaryRule.REQUIRED_WATER else land_value
        if boundary.edge is MapEdge.NORTH:
            if boundary.rule is BoundaryRule.REQUIRED_WATER:
                landness[0, :] = np.minimum(landness[0, :], value)
            else:
                landness[0, :] = np.maximum(landness[0, :], value)
        elif boundary.edge is MapEdge.SOUTH:
            if boundary.rule is BoundaryRule.REQUIRED_WATER:
                landness[-1, :] = np.minimum(landness[-1, :], value)
            else:
                landness[-1, :] = np.maximum(landness[-1, :], value)
        elif boundary.edge is MapEdge.WEST:
            if boundary.rule is BoundaryRule.REQUIRED_WATER:
                landness[:, 0] = np.minimum(landness[:, 0], value)
            else:
                supports = [
                    anchor
                    for anchor in plan.anchors
                    if anchor.positive
                    and anchor.role
                    in (AnchorRole.MAINLAND_SUPPORT, AnchorRole.BOUNDARY_SUPPORT)
                ]
                for support in supports:
                    center = int(round(support.y * (landness.shape[0] - 1)))
                    radius = max(
                        1,
                        int(round(0.45 * support.radius * landness.shape[0])),
                    )
                    start = max(0, center - radius)
                    end = min(landness.shape[0], center + radius + 1)
                    landness[start:end, 0] = np.maximum(
                        landness[start:end, 0], value
                    )
        else:
            if boundary.rule is BoundaryRule.REQUIRED_WATER:
                landness[:, -1] = np.minimum(landness[:, -1], value)
            else:
                landness[:, -1] = np.maximum(landness[:, -1], value)


def rasterize_macro_landform(
    plan: MacroLandformPlan, config: MacroLandformConfig
) -> Float32Array:
    """Rasterize a plan into a continuous float32 signed landness field."""

    if plan.base_seed != config.seed or plan.preset is not config.preset:
        raise ValueError("plan seed and preset must match config")
    parameters = _parameters(plan)
    if config.rasterizer is MacroRasterizer.GAUSSIAN:
        field = _gaussian_anchor_field(
            plan, config.width, config.height, config.gaussian_truncate
        )
        field += _corridor_field(plan, config.width, config.height)
    else:
        field = _rbf_field(plan, config)
        # RBF fits the signed anchor observations, while the mature EDT-based
        # corridor field makes required graph continuity an explicit constraint
        # rather than an accidental property of interpolation.
        field += np.float32(0.50) * _corridor_field(
            plan, config.width, config.height, polarity=True
        )
        if plan.preset is MacroLandformPreset.ISLAND:
            field += np.float32(0.10) * _corridor_field(
                plan, config.width, config.height, polarity=False
            )
    field += _boundary_field(plan, config.width, config.height)
    bias_scale = 0.55 if config.rasterizer is MacroRasterizer.RBF else 1.0
    field += np.float32(parameters["field_bias"] * bias_scale)
    field = np.ascontiguousarray(field, dtype=np.float32)
    _hard_enforce_boundaries(field, plan)
    if not np.isfinite(field).all():
        raise RuntimeError("rasterizer produced non-finite landness values")
    return field


def _edge(mask: BoolArray, edge: MapEdge) -> BoolArray:
    if edge is MapEdge.NORTH:
        return mask[0, :]
    if edge is MapEdge.SOUTH:
        return mask[-1, :]
    if edge is MapEdge.WEST:
        return mask[:, 0]
    return mask[:, -1]


def _boundary_rules_pass(mask: BoolArray, plan: MacroLandformPlan) -> bool:
    for boundary in plan.boundaries:
        edge_values = _edge(mask, boundary.edge)
        if boundary.rule is BoundaryRule.REQUIRED_WATER and np.any(edge_values):
            return False
        if boundary.rule is BoundaryRule.REQUIRED_LAND and not np.any(edge_values):
            return False
    return True


def _main_graph_connected(
    mask: BoolArray, labels: NDArray[np.int32], plan: MacroLandformPlan
) -> bool:
    positive = [anchor for anchor in plan.anchors if anchor.positive]
    if not positive:
        return False
    index = {anchor.identifier: position for position, anchor in enumerate(positive)}
    rows: list[int] = []
    columns: list[int] = []
    for connection in plan.connections:
        if not connection.positive:
            continue
        rows.extend((index[connection.start_anchor], index[connection.end_anchor]))
        columns.extend((index[connection.end_anchor], index[connection.start_anchor]))
    graph = coo_matrix(
        (np.ones(len(rows), dtype=np.int8), (rows, columns)),
        shape=(len(positive), len(positive)),
    ).tocsr()
    graph_components, _ = connected_components(graph, directed=False)
    if graph_components != 1:
        return False

    raster_labels: list[int] = []
    height, width = mask.shape
    for anchor in positive:
        y, x = _raster_point(anchor, width, height)
        label = int(labels[y, x])
        if label == 0:
            return False
        raster_labels.append(label)
    return len(set(raster_labels)) == 1


def _peninsula_water_flanks(mask: BoolArray, plan: MacroLandformPlan) -> bool:
    height, width = mask.shape
    backbone = sorted(
        (
            anchor
            for anchor in plan.anchors
            if anchor.positive
            and (
                anchor.identifier == "peninsula_junction"
                or anchor.identifier.startswith("peninsula_backbone_")
            )
        ),
        key=lambda anchor: (anchor.x, anchor.identifier),
    )
    if len(backbone) < 2:
        return False
    start = int(round(max(0.40, backbone[1].x) * (width - 1)))
    end = int(round(min(0.82, backbone[-1].x) * (width - 1)))
    path_x = np.array([anchor.x for anchor in backbone], dtype=np.float64)
    path_y = np.array([anchor.y for anchor in backbone], dtype=np.float64)
    qualifying = 0
    evaluated = 0
    margin = max(2, int(round(0.04 * height)))
    for x in range(start, end + 1):
        normalized_x = x / (width - 1)
        center = int(round(np.interp(normalized_x, path_x, path_y) * (height - 1)))
        if not mask[center, x]:
            search_radius = max(2, int(round(0.12 * height)))
            search_start = max(0, center - search_radius)
            search_end = min(height, center + search_radius + 1)
            candidates = np.flatnonzero(mask[search_start:search_end, x])
            if candidates.size == 0:
                continue
            candidate_rows = candidates + search_start
            center = int(candidate_rows[np.argmin(np.abs(candidate_rows - center))])
        top = center
        bottom = center
        while top > 0 and mask[top - 1, x]:
            top -= 1
        while bottom + 1 < height and mask[bottom + 1, x]:
            bottom += 1
        if bottom < top:
            continue
        evaluated += 1
        if top >= margin and bottom < height - margin:
            qualifying += 1
    return evaluated > 0 and qualifying / evaluated >= 0.55


def measure_macro_landform(
    landness: Float32Array,
    plan: MacroLandformPlan,
    config: MacroLandformConfig,
    runtime_seconds: float,
) -> MacroLandformMetrics:
    """Calculate lightweight prototype topology and gameplay diagnostics."""

    mask = np.ascontiguousarray(landness > np.float32(config.threshold))
    labels, component_count = ndimage.label(mask, structure=_FOUR_CONNECTED)
    land_pixels = int(mask.sum())
    if component_count:
        sizes = np.bincount(labels.ravel())[1:]
        largest_percent = float(sizes.max() * 100.0 / land_pixels)
    else:
        largest_percent = 0.0

    neck_pixels = max(1, int(round(config.neck_radius_fraction * min(mask.shape))))
    land_distance = ndimage.distance_transform_edt(mask)
    eroded = land_distance > neck_pixels
    _, eroded_components = ndimage.label(eroded, structure=_FOUR_CONNECTED)
    minimum_neck_pass = bool(eroded.any() and eroded_components <= 1)

    transitions = int(np.count_nonzero(mask[:, 1:] != mask[:, :-1]))
    transitions += int(np.count_nonzero(mask[1:, :] != mask[:-1, :]))
    perimeter_proxy = transitions / max(1, land_pixels)
    if land_pixels:
        occupied_columns = np.flatnonzero(mask.any(axis=0))
        eastward_projection = float(occupied_columns[-1] / (mask.shape[1] - 1))
    else:
        eastward_projection = 0.0

    boundary_pass = _boundary_rules_pass(mask, plan)
    graph_pass = _main_graph_connected(mask, labels.astype(np.int32, copy=False), plan)
    water_labels, water_component_count = ndimage.label(
        ~mask, structure=_FOUR_CONNECTED
    )
    edge_water_labels = set(int(value) for value in water_labels[0, :])
    edge_water_labels.update(int(value) for value in water_labels[-1, :])
    edge_water_labels.update(int(value) for value in water_labels[:, 0])
    edge_water_labels.update(int(value) for value in water_labels[:, -1])
    inland_water_components = sum(
        label not in edge_water_labels
        for label in range(1, int(water_component_count) + 1)
    )
    flank_pass = (
        _peninsula_water_flanks(mask, plan)
        if plan.preset is MacroLandformPreset.PENINSULA_EAST
        else True
    )
    parameters = _parameters(plan)
    coverage = land_pixels / mask.size
    failures: list[str] = []
    if component_count != 1:
        failures.append("land_component_count")
    if not boundary_pass:
        failures.append("boundary_rules")
    if not graph_pass:
        failures.append("main_graph_connectivity")
    if not minimum_neck_pass:
        failures.append("minimum_neck")
    if inland_water_components:
        failures.append("inland_water_voids")
    if not parameters["coverage_min"] <= coverage <= parameters["coverage_max"]:
        failures.append("land_coverage")
    if plan.preset is MacroLandformPreset.PENINSULA_EAST:
        if eastward_projection < 0.68:
            failures.append("eastward_projection")
        if not flank_pass:
            failures.append("peninsula_water_flanks")

    return MacroLandformMetrics(
        land_coverage_percent=coverage * 100.0,
        land_component_count=int(component_count),
        largest_component_percent=largest_percent,
        boundary_rules_pass=boundary_pass,
        intended_main_graph_connected=graph_pass,
        eroded_component_count=int(eroded_components),
        minimum_neck_pass=minimum_neck_pass,
        coastline_perimeter_area_proxy=float(perimeter_proxy),
        eastward_projection_fraction=eastward_projection,
        peninsula_water_flanks_pass=flank_pass,
        inland_water_component_count=inland_water_components,
        cleanup_land_pixels_removed=0,
        cleanup_land_percent_removed=0.0,
        generation_runtime_seconds=float(runtime_seconds),
        accepted=not failures,
        failure_reasons=tuple(failures),
    )


def generate_macro_landform(config: MacroLandformConfig) -> MacroLandformResult:
    """Generate a plan, signed landness field, mask, and prototype metrics."""

    started = time.perf_counter()
    plan = generate_macro_landform_plan(config)
    landness = rasterize_macro_landform(plan, config)
    runtime = time.perf_counter() - started
    mask = np.ascontiguousarray(landness > np.float32(config.threshold))
    metrics = measure_macro_landform(landness, plan, config, runtime)
    return MacroLandformResult(plan, landness, mask, metrics)
