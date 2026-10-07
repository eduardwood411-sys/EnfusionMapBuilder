"""Isolated preview and batch experiment CLI for MacroLandform v0.1."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFont

from Sources.Procedural.macro_landform import (
    MacroLandformConfig,
    MacroLandformPreset,
    MacroLandformResult,
    MacroRasterizer,
    generate_macro_landform,
)


DEFAULT_OUTPUT_DIRECTORY = Path(
    "Projects/Synthetic_Test_01/Output/MacroLandformV01"
)
COMPARISON_SEEDS = (1001, 2002, 3003, 4004, 5005, 12345)
RASTERIZER_DIRECTORIES = {
    MacroRasterizer.GAUSSIAN: "Gaussian",
    MacroRasterizer.RBF: "RBF",
}


def mask_to_preview_pixels(mask: NDArray[np.bool_]) -> NDArray[np.uint8]:
    """Render a boolean mask neutrally: white land and black water."""

    values = np.asarray(mask)
    if values.ndim != 2 or values.size == 0:
        raise ValueError("mask must be a non-empty two-dimensional array")
    if values.dtype != np.dtype(np.bool_):
        raise TypeError("mask must use bool dtype")
    return np.ascontiguousarray(values.astype(np.uint8) * np.uint8(255))


def save_macro_mask_png(mask: NDArray[np.bool_], output_path: Path) -> None:
    """Save one deterministic binary land/water diagnostic PNG."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask_to_preview_pixels(mask), mode="L").save(
        output_path,
        format="PNG",
        optimize=False,
        compress_level=9,
    )


def _metric_record(result: MacroLandformResult) -> dict[str, Any]:
    record = asdict(result.metrics)
    record["seed"] = result.plan.base_seed
    record["preset"] = result.plan.preset.value
    return record


def _contact_sheet(
    masks: dict[tuple[int, MacroLandformPreset], NDArray[np.bool_]],
    output_path: Path,
) -> None:
    """Create the fixed six-row, three-column diagnostic contact sheet."""

    first = next(iter(masks.values()))
    source_height, source_width = first.shape
    cell_width = min(384, source_width)
    cell_height = max(1, round(source_height * cell_width / source_width))
    label_height = 18
    header_height = 22
    row_label_width = 52
    canvas = Image.new(
        "L",
        (
            row_label_width + cell_width * len(MacroLandformPreset),
            header_height + (cell_height + label_height) * len(COMPARISON_SEEDS),
        ),
        color=0,
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    headings = ("Island", "Mainland Coast East", "Peninsula East")
    for column, heading in enumerate(headings):
        draw.text(
            (row_label_width + column * cell_width + 4, 5),
            heading,
            fill=255,
            font=font,
        )

    resampling = getattr(Image, "Resampling", Image).NEAREST
    for row, seed in enumerate(COMPARISON_SEEDS):
        row_top = header_height + row * (cell_height + label_height)
        draw.text((4, row_top + 4), str(seed), fill=255, font=font)
        for column, preset in enumerate(MacroLandformPreset):
            image = Image.fromarray(mask_to_preview_pixels(masks[(seed, preset)]), mode="L")
            if image.size != (cell_width, cell_height):
                image = image.resize((cell_width, cell_height), resample=resampling)
            x = row_label_width + column * cell_width
            canvas.paste(image, (x, row_top + label_height))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG", optimize=False, compress_level=9)


def run_comparison_suite(
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    width: int = 512,
    height: int = 512,
) -> dict[str, list[dict[str, Any]]]:
    """Generate the required 36 masks, two contact sheets, and metrics."""

    all_metrics: dict[str, list[dict[str, Any]]] = {}
    for rasterizer in MacroRasterizer:
        rasterizer_directory = output_directory / RASTERIZER_DIRECTORIES[rasterizer]
        masks: dict[tuple[int, MacroLandformPreset], NDArray[np.bool_]] = {}
        records: list[dict[str, Any]] = []
        for seed in COMPARISON_SEEDS:
            for preset in MacroLandformPreset:
                config = MacroLandformConfig(
                    seed=seed,
                    preset=preset,
                    rasterizer=rasterizer,
                    width=width,
                    height=height,
                )
                result = generate_macro_landform(config)
                masks[(seed, preset)] = result.land_mask
                records.append(_metric_record(result))
                save_macro_mask_png(
                    result.land_mask,
                    rasterizer_directory / f"seed_{seed}_{preset.value}.png",
                )
        contact_sheet_name = (
            f"macro_landform_v01_{rasterizer.value}_contact_sheet.png"
        )
        _contact_sheet(masks, output_directory / contact_sheet_name)
        all_metrics[rasterizer.value] = records
    return all_metrics


def run_batch_experiment(
    seed_count: int = 100,
    first_seed: int = 0,
    width: int = 512,
    height: int = 512,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Collect metrics only for a deterministic bounded seed batch."""

    if seed_count <= 0:
        raise ValueError("seed_count must be positive")
    summaries: dict[str, dict[str, dict[str, Any]]] = {}
    for rasterizer in MacroRasterizer:
        rasterizer_summaries: dict[str, dict[str, Any]] = {}
        for preset in MacroLandformPreset:
            metrics = []
            failures: Counter[str] = Counter()
            for seed in range(first_seed, first_seed + seed_count):
                result = generate_macro_landform(
                    MacroLandformConfig(
                        seed=seed,
                        preset=preset,
                        rasterizer=rasterizer,
                        width=width,
                        height=height,
                    )
                )
                metrics.append(result.metrics)
                failures.update(result.metrics.failure_reasons)

            accepted = sum(metric.accepted for metric in metrics)
            coverage = [metric.land_coverage_percent for metric in metrics]
            removed = [metric.cleanup_land_percent_removed for metric in metrics]
            rasterizer_summaries[preset.value] = {
                "seed_range": [first_seed, first_seed + seed_count - 1],
                "generated": seed_count,
                "accepted": accepted,
                "rejected": seed_count - accepted,
                "deterministic_retry_count": 0,
                "land_coverage_percent": {
                    "min": min(coverage),
                    "mean": fmean(coverage),
                    "max": max(coverage),
                },
                "component_failures": sum(
                    metric.land_component_count != 1 for metric in metrics
                ),
                "boundary_failures": sum(
                    not metric.boundary_rules_pass for metric in metrics
                ),
                "narrow_neck_failures": sum(
                    not metric.minimum_neck_pass for metric in metrics
                ),
                "main_graph_failures": sum(
                    not metric.intended_main_graph_connected for metric in metrics
                ),
                "inland_water_failures": sum(
                    metric.inland_water_component_count > 0 for metric in metrics
                ),
                "cleanup_frequency": sum(value > 0.0 for value in removed),
                "cleanup_removed_percent": {
                    "mean": fmean(removed),
                    "max": max(removed),
                },
                "mean_runtime_seconds": fmean(
                    metric.generation_runtime_seconds for metric in metrics
                ),
                "failure_patterns": dict(sorted(failures.items())),
                "rejected_cases": [
                    {
                        "seed": first_seed + index,
                        "reasons": list(metric.failure_reasons),
                    }
                    for index, metric in enumerate(metrics)
                    if not metric.accepted
                ],
            }
        summaries[rasterizer.value] = rasterizer_summaries
    return summaries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate isolated graph-guided macro land/water masks."
    )
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--preset", choices=[preset.value for preset in MacroLandformPreset]
    )
    parser.add_argument(
        "--rasterizer",
        choices=[rasterizer.value for rasterizer in MacroRasterizer],
        default=MacroRasterizer.GAUSSIAN.value,
    )
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--comparison-suite", action="store_true")
    parser.add_argument("--batch-count", type=int, default=0)
    parser.add_argument("--batch-first-seed", type=int, default=0)
    parser.add_argument(
        "--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY
    )
    parser.add_argument("--metrics-json", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload: dict[str, Any] = {}

    if args.comparison_suite:
        payload["comparison"] = run_comparison_suite(
            args.output_directory, args.width, args.height
        )
    if args.batch_count:
        payload["batch"] = run_batch_experiment(
            seed_count=args.batch_count,
            first_seed=args.batch_first_seed,
            width=args.width,
            height=args.height,
        )

    if not args.comparison_suite and not args.batch_count:
        if args.seed is None or args.preset is None:
            parser.error("single preview mode requires --seed and --preset")
        rasterizer = MacroRasterizer(args.rasterizer)
        preset = MacroLandformPreset(args.preset)
        result = generate_macro_landform(
            MacroLandformConfig(
                seed=args.seed,
                preset=preset,
                rasterizer=rasterizer,
                width=args.width,
                height=args.height,
            )
        )
        output = args.output or (
            args.output_directory
            / RASTERIZER_DIRECTORIES[rasterizer]
            / f"seed_{args.seed}_{preset.value}.png"
        )
        save_macro_mask_png(result.land_mask, output)
        payload["preview"] = _metric_record(result)
        payload["output"] = str(output)

    if args.metrics_json:
        args.metrics_json.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_json.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
