#!/usr/bin/env python3
"""Prepare next-step floorplan configuration from run_report output.

This script does not generate DWG yet. It creates a deterministic config package
for the next extraction step (slice, snap, layers, QA tolerance).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PREFERRED_EXT_ORDER = [".e57", ".las", ".laz", ".rcp", ".rcs"]


def choose_primary_pointcloud(files: list[str]) -> str:
    if not files:
        raise ValueError("No pointcloud files were found in run_report.json")

    normalized = [Path(p) for p in files]
    for ext in PREFERRED_EXT_ORDER:
        candidates = [p for p in normalized if p.suffix.lower() == ext]
        if candidates:
            return str(sorted(candidates)[0])
    return str(sorted(normalized)[0])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare floorplan extraction config from work/run_report.json"
    )
    parser.add_argument(
        "--report",
        default="work/run_report.json",
        help="Input report from full_floor_runner",
    )
    parser.add_argument(
        "--config",
        default="work/floorplan_config.json",
        help="Output config path",
    )
    parser.add_argument(
        "--checklist",
        default="work/NEXT_STEP_CHECKLIST.md",
        help="Output checklist path",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        raise SystemExit(
            f"Missing report: {report_path}. Run scripts/run_full_floor.ps1 first."
        )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    warnings = report.get("warnings", [])
    if warnings:
        raise SystemExit(
            "run_report.json contains warnings. Fix them first: " + "; ".join(warnings)
        )

    pointcloud_files = report.get("pointcloud_files", [])
    primary = choose_primary_pointcloud(pointcloud_files)

    config_path = Path(args.config)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config = {
        "input": {
            "primary_pointcloud": primary,
            "all_pointcloud_files": pointcloud_files,
            "template_dwg": "input/templates/VZOR.dwg",
        },
        "extraction": {
            "target": "2d_floorplan",
            "slice_height_m": 1.1,
            "slice_thickness_m": 0.1,
            "wall_min_length_m": 0.3,
            "dominant_axis_alignment": True,
            "snap_grid_m": 0.01,
        },
        "quality": {
            "max_deviation_m": 0.02,
            "notes": "Tolerance target from user: 2 cm",
        },
        "layers": {
            "walls": "TODO_FROM_TEMPLATE",
            "openings": "TODO_FROM_TEMPLATE",
            "grid": "TODO_FROM_TEMPLATE",
            "dimensions": "TODO_FROM_TEMPLATE",
            "annotations": "TODO_FROM_TEMPLATE",
        },
        "outputs": {
            "raw_plan_dxf": "output/floorplan_raw.dxf",
            "normalized_plan_dxf": "output/floorplan_normalized.dxf",
            "qa_report_json": "output/floorplan_qa.json",
        },
    }

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    checklist_path = Path(args.checklist)
    checklist_path.parent.mkdir(parents=True, exist_ok=True)
    checklist_path.write_text(
        "\n".join(
            [
                "# Next step checklist (2D floorplan)",
                "",
                "1. Open work/floorplan_config.json and map CAD layers from VZOR.dwg.",
                "2. Confirm slice height (default 1.1 m) and wall thickness assumptions.",
                "3. Run extraction implementation (next script) to produce raw + normalized DXF.",
                "4. Validate QA report max deviation <= 0.02 m.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Created: {config_path}")
    print(f"Created: {checklist_path}")
    print(f"Primary pointcloud: {primary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
