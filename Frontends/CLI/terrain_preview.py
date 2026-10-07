"""Command-line generation of deterministic terrain preview PNGs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from Sources.Procedural.landform import (
    CoastEdge,
    LandformConfig,
    LandformMode,
    derive_land_water_masks,
    generate_landform,
)
from Sources.Procedural.terrain import (
    LayeredTerrainConfig,
    TerrainConfig,
    generate_layered_terrain,
    generate_terrain,
)


DEFAULT_OUTPUT_DIRECTORY = Path("Projects/Synthetic_Test_01/Output")


def terrain_to_preview_pixels(terrain: NDArray[np.floating]) -> NDArray[np.uint8]:
    """Convert terrain values in [-1, 1] to deterministic grayscale pixels."""

    values = np.asarray(terrain)
    if values.ndim != 2 or values.size == 0:
        raise ValueError("terrain must be a non-empty two-dimensional array")
    if not np.isfinite(values).all():
        raise ValueError("terrain must contain only finite values")

    clipped = np.clip(values, -1.0, 1.0).astype(np.float32, copy=False)
    scaled = (clipped + np.float32(1.0)) * np.float32(127.5)
    return np.rint(scaled).astype(np.uint8)


def save_preview_png(terrain: NDArray[np.floating], output_path: Path) -> None:
    """Write an 8-bit grayscale preview; the PNG is not terrain source data."""

    pixels = terrain_to_preview_pixels(terrain)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(pixels)
    image.save(output_path, format="PNG", optimize=False, compress_level=9)


def landform_to_preview_pixels(terrain: NDArray[np.floating]) -> NDArray[np.uint8]:
    """Map water to black and positive land elevation to grayscale."""

    land_mask, _ = derive_land_water_masks(terrain)
    values = np.asarray(terrain, dtype=np.float32)
    land_values = np.clip(values, 0.0, 1.0)
    pixels = np.zeros(values.shape, dtype=np.uint8)
    pixels[land_mask] = (
        np.rint(land_values[land_mask] * np.float32(254.0)).astype(np.uint8) + 1
    )
    return pixels


def save_landform_preview_png(
    terrain: NDArray[np.floating], output_path: Path
) -> None:
    """Write a landform preview with water rendered as black."""

    pixels = landform_to_preview_pixels(terrain)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(pixels)
    image.save(output_path, format="PNG", optimize=False, compress_level=9)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic procedural terrain preview PNG."
    )
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--frequency", type=float, default=0.01)
    parser.add_argument("--octaves", type=int, default=5)
    parser.add_argument("--lacunarity", type=float, default=2.0)
    parser.add_argument("--gain", type=float, default=0.5)
    parser.add_argument(
        "--layered",
        action="store_true",
        help="Use the fixed macro, secondary, and detail terrain layers.",
    )
    parser.add_argument(
        "--landform",
        choices=[mode.value for mode in LandformMode],
        help="Shape layered terrain as an island or coastal mainland section.",
    )
    parser.add_argument(
        "--coast-edge",
        choices=[edge.value for edge in CoastEdge],
        default=CoastEdge.EAST.value,
        help="Sea-facing map edge for coast landforms (default: east).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="PNG path; defaults to the Synthetic_Test_01 Output directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.landform and args.layered:
        parser.error("--landform already uses layered terrain; omit --layered")

    is_landform = args.landform is not None
    if is_landform:
        mode = LandformMode(args.landform)
        coast_edge = CoastEdge(args.coast_edge)
        config = LandformConfig(
            seed=args.seed,
            mode=mode,
            width=args.width,
            height=args.height,
            coast_edge=coast_edge,
        )
        terrain = generate_landform(config)
        if mode is LandformMode.ISLAND:
            default_filename = f"terrain_seed_{config.seed}_landform_island.png"
        else:
            default_filename = (
                f"terrain_seed_{config.seed}_landform_coast_{coast_edge.value}.png"
            )
    elif args.layered:
        config = LayeredTerrainConfig(
            seed=args.seed,
            width=args.width,
            height=args.height,
        )
        terrain = generate_layered_terrain(config)
        default_filename = f"terrain_seed_{config.seed}_layered.png"
    else:
        config = TerrainConfig(
            seed=args.seed,
            width=args.width,
            height=args.height,
            frequency=args.frequency,
            octaves=args.octaves,
            lacunarity=args.lacunarity,
            gain=args.gain,
        )
        terrain = generate_terrain(config)
        default_filename = f"terrain_seed_{config.seed}.png"

    output_path = args.output or (DEFAULT_OUTPUT_DIRECTORY / default_filename)
    if is_landform:
        save_landform_preview_png(terrain, output_path)
    else:
        save_preview_png(terrain, output_path)

    print(f"Generated preview: {output_path}")
    print(
        "Terrain statistics: "
        f"min={float(terrain.min()):.9f}, "
        f"max={float(terrain.max()):.9f}, "
        f"mean={float(terrain.mean(dtype=np.float64)):.9f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
