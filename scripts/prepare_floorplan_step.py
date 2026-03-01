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
            "slice_thickness_m": 0.15,
            "wall_min_length_m": 0.5,
            "line_max_gap_m": 0.08,
            "line_min_density": 0.30,
            "dominant_axis_alignment": False,
            "line_angle_step_deg": 15.0,
            "line_angles_deg": None,
            "orthogonal_pair_mode": True,
            "orthogonal_base_angle_deg": None,
            "orthogonal_angle_jitter_deg": 12.0,
            "orthogonal_angle_step_deg": 4.0,
            "snap_grid_m": 0.02,
            "raw_max_points": 200000,
            "min_cell_hits": 3,
            "min_component_cells": 24,
        },
        "quality": {
            "max_deviation_m": 0.02,
            "notes": "Tolerance target from user: 2 cm",
        },
        "layers": {
            "walls": "1-0_ŘEZ",
            "doors": "2-7_DVERE",
            "windows": "2-8_OKNA",
            "grid": "6-1_OSY",
            "dimensions": "9-9_KOTY",
            "annotations": "7-0_POPIS",
        },
        "outputs": {
            "raw_plan_dxf": "output/floorplan_raw.dxf",
            "normalized_plan_dxf": "output/floorplan_normalized.dxf",
            "qa_report_json": "output/floorplan_qa.json",
            "wall_lines_dxf": "output/floorplan_walls.dxf",
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
                "1. Verify layer mapping in work/floorplan_config.json matches your CAD standard.",
                "2. Confirm slice/snap params and tune min_cell_hits + min_component_cells + line_max_gap_m + line_min_density + orthogonal_angle_jitter_deg/orthogonal_angle_step_deg if walls are fragmented/noisy.",
                "3. Run extraction script to produce raw/normalized DXF + wall lines DXF.",
                "4. Validate QA report max deviation <= 0.02 m and check wall_segments_count > 0.",
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
