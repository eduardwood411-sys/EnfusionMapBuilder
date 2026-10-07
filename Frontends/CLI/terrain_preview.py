"""Command-line generation of deterministic terrain preview PNGs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from Sources.Procedural.terrain import TerrainConfig, generate_terrain


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
        "--output",
        type=Path,
        help="PNG path; defaults to the Synthetic_Test_01 Output directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
    output_path = args.output or (
        DEFAULT_OUTPUT_DIRECTORY / f"terrain_seed_{config.seed}.png"
    )
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
