#!/usr/bin/env python3
"""Auto-tune floorplan extraction parameters locally.

Runs multiple extract_floorplan.py trials, scores results from QA + walls DXF,
and writes best config suggestion.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import subprocess
import sys
from pathlib import Path


def parse_dxf_line_lengths(path: Path) -> list[float]:
    if not path.exists():
        return []
    vals = path.read_text(encoding="ascii", errors="ignore").splitlines()
    lengths: list[float] = []
    i = 0
    while i < len(vals):
        if vals[i] == "0" and i + 1 < len(vals) and vals[i + 1] == "LINE":
            i += 2
            x1 = y1 = x2 = y2 = None
            while i + 1 < len(vals) and not (vals[i] == "0" and vals[i + 1] in {"LINE", "ENDSEC", "EOF"}):
                code = vals[i]
                value = vals[i + 1]
                if code == "10":
                    x1 = float(value)
                elif code == "20":
                    y1 = float(value)
                elif code == "11":
                    x2 = float(value)
                elif code == "21":
                    y2 = float(value)
                i += 2
            if None not in (x1, y1, x2, y2):
                lengths.append(math.hypot(x2 - x1, y2 - y1))
            continue
        i += 1
    return lengths


def score_trial(qa: dict, line_lengths: list[float]) -> float:
    seg = float(qa.get("wall_segments_count", 0))
    norm = float(qa.get("normalized_points_count", 1))
    seg_density = seg / max(norm, 1.0)

    mean_len = (sum(line_lengths) / len(line_lengths)) if line_lengths else 0.0
    long_count = sum(1 for x in line_lengths if x >= 0.5)

    score = 0.0
    score += min(mean_len, 5.0) * 6.0
    score += min(long_count, 2000) * 0.02
    score += (1.0 / max(seg_density, 1e-9)) * 0.1
    return score


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-tune floorplan extraction parameters")
    ap.add_argument("--config", default="work/floorplan_config.json", help="Base config path")
    ap.add_argument("--extract-script", default="scripts/extract_floorplan.py", help="Extractor script")
    ap.add_argument("--report", default="work/autotune_report.json", help="Autotune report output")
    args = ap.parse_args()

    base_path = Path(args.config)
    if not base_path.exists():
        raise SystemExit(f"Missing config: {base_path}")

    base = json.loads(base_path.read_text(encoding="utf-8"))

    gap_values = [0.03, 0.05, 0.08, 0.12]
    density_values = [0.20, 0.30, 0.40]
    min_len_values = [0.20, 0.30, 0.40]
    ortho_step_values = [3.0, 4.0, 6.0]
    ortho_jitter_values = [8.0, 12.0, 16.0]

    tuning_dir = Path("work/autotune")
    tuning_dir.mkdir(parents=True, exist_ok=True)

    trials: list[dict] = []
    best: dict | None = None

    for gap in gap_values:
        for dens in density_values:
            for min_len in min_len_values:
                for ortho_step in ortho_step_values:
                    for ortho_jitter in ortho_jitter_values:
                        cfg = copy.deepcopy(base)
                        cfg.setdefault("extraction", {})["line_max_gap_m"] = gap
                        cfg["extraction"]["line_min_density"] = dens
                        cfg["extraction"]["wall_min_length_m"] = min_len

                        cfg["extraction"]["dominant_axis_alignment"] = False
                        cfg["extraction"]["line_angle_step_deg"] = 15.0
                        cfg["extraction"]["line_angles_deg"] = None
                        cfg["extraction"]["orthogonal_pair_mode"] = True
                        cfg["extraction"]["orthogonal_base_angle_deg"] = None
                        cfg["extraction"]["orthogonal_angle_step_deg"] = ortho_step
                        cfg["extraction"]["orthogonal_angle_jitter_deg"] = ortho_jitter

                        trial_id = f"g{gap}_d{dens}_m{min_len}_s{ortho_step}_j{ortho_jitter}".replace(".", "_")
                        out_dir = tuning_dir / trial_id
                        out_dir.mkdir(parents=True, exist_ok=True)

                        cfg.setdefault("outputs", {})["raw_plan_dxf"] = str(out_dir / "floorplan_raw.dxf")
                        cfg["outputs"]["normalized_plan_dxf"] = str(out_dir / "floorplan_normalized.dxf")
                        cfg["outputs"]["wall_lines_dxf"] = str(out_dir / "floorplan_walls.dxf")
                        cfg["outputs"]["qa_report_json"] = str(out_dir / "floorplan_qa.json")

                        cfg_path = out_dir / "config.json"
                        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

                        proc = subprocess.run(
                            [sys.executable, args.extract_script, "--config", str(cfg_path)],
                            capture_output=True,
                            text=True,
                        )
                        if proc.returncode != 0:
                            trials.append(
                                {
                                    "trial": trial_id,
                                    "params": {
                                        "line_max_gap_m": gap,
                                        "line_min_density": dens,
                                        "wall_min_length_m": min_len,
                                        "orthogonal_angle_step_deg": ortho_step,
                                        "orthogonal_angle_jitter_deg": ortho_jitter,
                                    },
                                    "status": "failed",
                                    "stderr": proc.stderr[-1200:],
                                    "stdout": proc.stdout[-1200:],
                                }
                            )
                            continue

                        qa_path = Path(cfg["outputs"]["qa_report_json"])
                        qa = json.loads(qa_path.read_text(encoding="utf-8"))
                        lengths = parse_dxf_line_lengths(Path(cfg["outputs"]["wall_lines_dxf"]))
                        score = score_trial(qa, lengths)

                        row = {
                            "trial": trial_id,
                            "params": {
                                "line_max_gap_m": gap,
                                "line_min_density": dens,
                                "wall_min_length_m": min_len,
                                "orthogonal_angle_step_deg": ortho_step,
                                "orthogonal_angle_jitter_deg": ortho_jitter,
                            },
                            "status": "ok",
                            "score": score,
                            "wall_segments_count": qa.get("wall_segments_count", 0),
                            "normalized_points_count": qa.get("normalized_points_count", 0),
                            "mean_line_length_m": (sum(lengths) / len(lengths)) if lengths else 0.0,
                            "long_lines_count_0_5m": sum(1 for x in lengths if x >= 0.5),
                            "outputs": qa.get("outputs", {}),
                        }
                        trials.append(row)

                        if best is None or row["score"] > best["score"]:
                            best = row

    report = {
        "base_config": str(base_path),
        "tested": len(trials),
        "successful": sum(1 for t in trials if t.get("status") == "ok"),
        "best": best,
        "trials": sorted(trials, key=lambda x: x.get("score", -1.0), reverse=True),
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if best is not None:
        tuned = json.loads(base_path.read_text(encoding="utf-8"))
        tuned.setdefault("extraction", {})["line_max_gap_m"] = best["params"]["line_max_gap_m"]
        tuned["extraction"]["line_min_density"] = best["params"]["line_min_density"]
        tuned["extraction"]["wall_min_length_m"] = best["params"]["wall_min_length_m"]

        tuned["extraction"]["dominant_axis_alignment"] = False
        tuned["extraction"]["line_angle_step_deg"] = 15.0
        tuned["extraction"]["line_angles_deg"] = None
        tuned["extraction"]["orthogonal_pair_mode"] = True
        tuned["extraction"]["orthogonal_base_angle_deg"] = None
        tuned["extraction"]["orthogonal_angle_step_deg"] = best["params"]["orthogonal_angle_step_deg"]
        tuned["extraction"]["orthogonal_angle_jitter_deg"] = best["params"]["orthogonal_angle_jitter_deg"]

        tuned_path = report_path.parent / "floorplan_config.tuned.json"
        tuned_path.write_text(json.dumps(tuned, indent=2), encoding="utf-8")
        print(f"Best params: {best['params']}")
        print(f"Wrote tuned config: {tuned_path}")

    print(f"Wrote autotune report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())