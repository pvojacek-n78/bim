#!/usr/bin/env python3
"""Extract a first-pass 2D floorplan slice from point cloud config.

Outputs:
- raw DXF POINT cloud slice (optionally capped by sampling)
- normalized DXF POINT cloud (snapped + deduplicated)
- wall-lines DXF (multi-angle vectorization from normalized points)
- QA JSON report
"""

from __future__ import annotations

import argparse
import json
import math
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class Config:
    primary_pointcloud: Path
    raw_plan_dxf: Path
    normalized_plan_dxf: Path
    wall_lines_dxf: Path
    qa_report_json: Path
    walls_layer: str
    slice_height_m: float
    slice_thickness_m: float
    snap_grid_m: float
    wall_min_length_m: float
    line_max_gap_m: float
    line_min_density: float
    dominant_axis_alignment: bool
    line_angle_step_deg: float
    line_angles_deg: list[float] | None
    orthogonal_pair_mode: bool
    orthogonal_base_angle_deg: float | None
    orthogonal_angle_jitter_deg: float
    orthogonal_angle_step_deg: float
    raw_max_points: int
    max_deviation_m: float


def _require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"Missing {label}: {path}")


def load_config(path: Path) -> Config:
    _require_file(path, "config")
    data = json.loads(path.read_text(encoding="utf-8"))

    outputs = data["outputs"]
    extraction = data["extraction"]

    return Config(
        primary_pointcloud=Path(data["input"]["primary_pointcloud"]),
        raw_plan_dxf=Path(outputs["raw_plan_dxf"]),
        normalized_plan_dxf=Path(outputs["normalized_plan_dxf"]),
        wall_lines_dxf=Path(outputs.get("wall_lines_dxf", "output/floorplan_walls.dxf")),
        qa_report_json=Path(outputs["qa_report_json"]),
        walls_layer=str(data["layers"]["walls"]),
        slice_height_m=float(extraction["slice_height_m"]),
        slice_thickness_m=float(extraction["slice_thickness_m"]),
        snap_grid_m=float(extraction["snap_grid_m"]),
        wall_min_length_m=float(extraction.get("wall_min_length_m", 0.3)),
        line_max_gap_m=float(extraction.get("line_max_gap_m", 0.05)),
        line_min_density=float(extraction.get("line_min_density", 0.30)),
        dominant_axis_alignment=bool(extraction.get("dominant_axis_alignment", False)),
        line_angle_step_deg=float(extraction.get("line_angle_step_deg", 15.0)),
        line_angles_deg=(
            [float(x) for x in extraction.get("line_angles_deg", [])]
            if extraction.get("line_angles_deg") is not None
            else None
        ),
        orthogonal_pair_mode=bool(extraction.get("orthogonal_pair_mode", True)),
        orthogonal_base_angle_deg=(
            float(extraction["orthogonal_base_angle_deg"])
            if extraction.get("orthogonal_base_angle_deg") is not None
            else None
        ),
        orthogonal_angle_jitter_deg=float(extraction.get("orthogonal_angle_jitter_deg", 12.0)),
        orthogonal_angle_step_deg=float(extraction.get("orthogonal_angle_step_deg", 4.0)),
        raw_max_points=int(extraction.get("raw_max_points", 500000)),
        max_deviation_m=float(data["quality"]["max_deviation_m"]),
    )


def _is_finite_triplet(x: float, y: float, z: float) -> bool:
    return math.isfinite(x) and math.isfinite(y) and math.isfinite(z)


def load_points(path: Path) -> list[tuple[float, float, float]]:
    ext = path.suffix.lower()

    if ext == ".e57":
        try:
            import pye57  # type: ignore
        except Exception as exc:
            raise SystemExit(
                "E57 input detected but pye57 is not installed. Install with: pip install pye57"
            ) from exc

        e57 = pye57.E57(str(path))
        if e57.scan_count == 0:
            raise SystemExit("E57 has no scans.")
        data = e57.read_scan_raw(0)

        pts: list[tuple[float, float, float]] = []
        for x, y, z in zip(data["cartesianX"], data["cartesianY"], data["cartesianZ"]):
            xf, yf, zf = float(x), float(y), float(z)
            if _is_finite_triplet(xf, yf, zf):
                pts.append((xf, yf, zf))
        return pts

    if ext in {".las", ".laz"}:
        try:
            import laspy  # type: ignore
        except Exception as exc:
            raise SystemExit(
                "LAS/LAZ input detected but laspy is not installed. Install with: pip install laspy"
            ) from exc

        las = laspy.read(path)
        pts = []
        for x, y, z in zip(las.x, las.y, las.z):
            xf, yf, zf = float(x), float(y), float(z)
            if _is_finite_triplet(xf, yf, zf):
                pts.append((xf, yf, zf))
        return pts

    if ext in {".xyz", ".txt"}:
        pts = []
        for idx, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 3:
                raise SystemExit(f"Invalid XYZ row at line {idx}: expected at least 3 columns")
            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
            if _is_finite_triplet(x, y, z):
                pts.append((x, y, z))
        if not pts:
            raise SystemExit("XYZ/TXT parsed but no valid finite points were found")
        return pts

    if ext in {".rcp", ".rcs"}:
        raise SystemExit(
            "RCP/RCS is not directly supported in this script. Export to E57/LAS first (Recap/CloudCompare)."
        )

    raise SystemExit(f"Unsupported input format: {ext}")


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("Cannot compute quantile of empty list")
    if q <= 0:
        return sorted_values[0]
    if q >= 1:
        return sorted_values[-1]

    pos = (len(sorted_values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_values[lo]
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def slice_points(
    points: list[tuple[float, float, float]],
    slice_height_m: float,
    slice_thickness_m: float,
) -> tuple[list[tuple[float, float]], float]:
    z_values = sorted(p[2] for p in points)
    floor_z = _quantile(z_values, 0.02)
    target_z = floor_z + slice_height_m
    half = slice_thickness_m / 2.0

    xy = [(x, y) for x, y, z in points if abs(z - target_z) <= half]
    return xy, target_z


def sample_points(points_xy: list[tuple[float, float]], max_points: int) -> tuple[list[tuple[float, float]], bool]:
    if max_points <= 0 or len(points_xy) <= max_points:
        return points_xy, False
    step = len(points_xy) / max_points
    sampled = [points_xy[int(i * step)] for i in range(max_points)]
    return sampled, True


def snap_xy(points_xy: list[tuple[float, float]], grid: float) -> list[tuple[float, float]]:
    if grid <= 0:
        return points_xy
    return [(round(x / grid) * grid, round(y / grid) * grid) for x, y in points_xy]


def unique_points(points_xy: list[tuple[float, float]]) -> list[tuple[float, float]]:
    seen: set[tuple[float, float]] = set()
    out: list[tuple[float, float]] = []
    for pt in points_xy:
        if pt not in seen:
            seen.add(pt)
            out.append(pt)
    return out


def to_grid_points(points_xy: list[tuple[float, float]], grid: float) -> set[tuple[int, int]]:
    if grid <= 0:
        raise SystemExit("snap_grid_m must be > 0 for wall vectorization.")
    return {(int(round(x / grid)), int(round(y / grid))) for x, y in points_xy}

def _runs_with_gap(values: list[int], max_gap_cells: int) -> list[tuple[int, int, int]]:
    """Return list of (start, end, support_count) allowing small gaps."""
    if not values:
        return []
    vals = sorted(set(values))
    runs: list[tuple[int, int, int]] = []

    start = prev = vals[0]
    support = 1
    for v in vals[1:]:
        if v - prev <= max_gap_cells + 1:
            prev = v
            support += 1
            continue
        runs.append((start, prev, support))
        start = prev = v
        support = 1
    runs.append((start, prev, support))
    return runs


def _normalize_halfturn_angle(angle_deg: float) -> float:
    normalized = angle_deg % 180.0
    if normalized < 0:
        normalized += 180.0
    return normalized


def _estimate_dominant_axis_angle(grid_points: set[tuple[int, int]]) -> float:
    if not grid_points:
        return 0.0

    offsets = [
        (dx, dy)
        for dx in range(-2, 3)
        for dy in range(-2, 3)
        if not (dx == 0 and dy == 0)
    ]
    sample = list(grid_points)[:50000]

    bins = [0] * 180
    for gx, gy in sample:
        for dx, dy in offsets:
            if (gx + dx, gy + dy) not in grid_points:
                continue
            angle = _normalize_halfturn_angle(math.degrees(math.atan2(dy, dx)))
            bins[int(round(angle)) % 180] += 1

    peak_idx = max(range(180), key=lambda i: bins[i])
    return float(peak_idx)


def _angles_around(base_deg: float, jitter_deg: float, step_deg: float) -> set[float]:
    step = max(0.1, step_deg)
    jitter = max(0.0, jitter_deg)
    count = int(math.floor(jitter / step))
    return {
        _normalize_halfturn_angle(base_deg + i * step)
        for i in range(-count, count + 1)
    }


def resolve_candidate_angles(
    dominant_axis_alignment: bool,
    line_angle_step_deg: float,
    line_angles_deg: list[float] | None,
    orthogonal_pair_mode: bool,
    orthogonal_base_angle_deg: float | None,
    orthogonal_angle_jitter_deg: float,
    orthogonal_angle_step_deg: float,
    grid_points: set[tuple[int, int]],
) -> list[float]:
    if line_angles_deg is not None and len(line_angles_deg) > 0:
        return sorted({_normalize_halfturn_angle(a) for a in line_angles_deg})

    if orthogonal_pair_mode:
        base = orthogonal_base_angle_deg
        if base is None:
            base = _estimate_dominant_axis_angle(grid_points)
        a = _angles_around(base, orthogonal_angle_jitter_deg, orthogonal_angle_step_deg)
        b = _angles_around(base + 90.0, orthogonal_angle_jitter_deg, orthogonal_angle_step_deg)
        return sorted(a | b)

    if dominant_axis_alignment:
        return [0.0, 90.0]

    step = max(1.0, line_angle_step_deg)
    steps = max(1, int(round(180.0 / step)))
    return sorted({_normalize_halfturn_angle(i * step) for i in range(steps)})


def extract_wall_segments(
    grid_points: set[tuple[int, int]],
    grid: float,
    wall_min_length_m: float,
    line_max_gap_m: float,
    line_min_density: float,
    candidate_angles_deg: list[float],
) -> list[tuple[float, float, float, float]]:
    min_cells = max(2, int(math.ceil(wall_min_length_m / grid)))
    max_gap_cells = max(0, int(round(line_max_gap_m / grid)))
    min_density = max(0.0, min(1.0, line_min_density))

    segments: list[tuple[float, float, float, float]] = []
    dedupe: set[tuple[int, int, int, int]] = set()

    for angle in candidate_angles_deg:
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        lines: dict[int, list[int]] = {}
        for gx, gy in grid_points:
            u = gx * cos_a + gy * sin_a
            v = -gx * sin_a + gy * cos_a
            ui = int(round(u))
            vi = int(round(v))
            lines.setdefault(vi, []).append(ui)

        for vi, us in lines.items():
            for start, end, support in _runs_with_gap(us, max_gap_cells):
                span = end - start + 1
                density = support / span if span > 0 else 0.0
                if span < min_cells or density < min_density:
                    continue

                x1g = start * cos_a - vi * sin_a
                y1g = start * sin_a + vi * cos_a
                x2g = end * cos_a - vi * sin_a
                y2g = end * sin_a + vi * cos_a

                p1 = (int(round(x1g)), int(round(y1g)))
                p2 = (int(round(x2g)), int(round(y2g)))
                key = (*p1, *p2) if p1 <= p2 else (*p2, *p1)
                if key in dedupe:
                    continue
                dedupe.add(key)
                segments.append((p1[0] * grid, p1[1] * grid, p2[0] * grid, p2[1] * grid))

    return segments


def sanitize_dxf_layer_name(name: str) -> str:
    """Return ASCII-safe layer name for broad DXF compatibility."""
    # Remove diacritics
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")

    # Keep only safe chars commonly accepted by CAD tools
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in ascii_only)
    safe = safe.strip("_")
    if not safe:
        safe = "LAYER"
    return safe[:120]


def dxf_header(layers: Iterable[str]) -> str:
    layers_list = list(layers)
    lines = [
        "0", "SECTION", "2", "HEADER", "0", "ENDSEC",
        "0", "SECTION", "2", "TABLES",
        "0", "TABLE", "2", "LAYER", "70", str(len(layers_list)),
    ]
    for name in layers_list:
        lines.extend(["0", "LAYER", "2", name, "70", "0", "62", "7", "6", "CONTINUOUS"])
    lines.extend(["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"])
    return "\n".join(lines) + "\n"


def dxf_points(points_xy: list[tuple[float, float]], layer: str) -> str:
    lines: list[str] = []
    for x, y in points_xy:
        lines.extend([
            "0", "POINT",
            "8", layer,
            "10", f"{x:.6f}",
            "20", f"{y:.6f}",
            "30", "0.0",
        ])
    return "\n".join(lines) + ("\n" if lines else "")


def dxf_lines(segments: list[tuple[float, float, float, float]], layer: str) -> str:
    lines: list[str] = []
    for x1, y1, x2, y2 in segments:
        lines.extend([
            "0", "LINE",
            "8", layer,
            "10", f"{x1:.6f}",
            "20", f"{y1:.6f}",
            "30", "0.0",
            "11", f"{x2:.6f}",
            "21", f"{y2:.6f}",
            "31", "0.0",
        ])
    return "\n".join(lines) + ("\n" if lines else "")


def write_dxf_points(path: Path, points_xy: list[tuple[float, float]], layer: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    layer_safe = sanitize_dxf_layer_name(layer)
    text = dxf_header([layer_safe]) + dxf_points(points_xy, layer_safe) + "0\nENDSEC\n0\nEOF\n"
    safe_write_text(path, text)
    return layer_safe


def write_dxf_lines(path: Path, segments: list[tuple[float, float, float, float]], layer: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    layer_safe = sanitize_dxf_layer_name(layer)
    text = dxf_header([layer_safe]) + dxf_lines(segments, layer_safe) + "0\nENDSEC\n0\nEOF\n"
    safe_write_text(path, text)
    return layer_safe


def safe_write_text(path: Path, text: str, retries: int = 6, delay_s: float = 0.4) -> None:
    """Write text with retries to survive transient Windows file locks (OneDrive/CAD preview)."""
    last_exc: Exception | None = None
    for _ in range(max(1, retries)):
        try:
            path.write_text(text, encoding="ascii", errors="ignore")

            return
        except PermissionError as exc:
            last_exc = exc
            time.sleep(max(0.0, delay_s))
    raise SystemExit(
        f"Cannot write output file after retries (file may be open in CAD/Explorer/OneDrive): {path}"
    ) from last_exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract first-pass 2D floorplan points to DXF")
    parser.add_argument("--config", default="work/floorplan_config.json", help="Config path")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    _require_file(cfg.primary_pointcloud, "primary pointcloud")

    points = load_points(cfg.primary_pointcloud)
    if not points:
        raise SystemExit("No valid points loaded from input point cloud.")

    raw_xy_full, target_z = slice_points(points, cfg.slice_height_m, cfg.slice_thickness_m)
    if not raw_xy_full:
        raise SystemExit("No points found in requested slice. Adjust slice_height_m or slice_thickness_m.")

    raw_xy, was_sampled = sample_points(raw_xy_full, cfg.raw_max_points)
    snapped_xy = unique_points(snap_xy(raw_xy_full, cfg.snap_grid_m))

    grid_points = to_grid_points(snapped_xy, cfg.snap_grid_m)
    candidate_angles = resolve_candidate_angles(
        cfg.dominant_axis_alignment,
        cfg.line_angle_step_deg,
        cfg.line_angles_deg,
        cfg.orthogonal_pair_mode,
        cfg.orthogonal_base_angle_deg,
        cfg.orthogonal_angle_jitter_deg,
        cfg.orthogonal_angle_step_deg,
        grid_points,
    )
    wall_segments = extract_wall_segments(
        grid_points,
        cfg.snap_grid_m,
        cfg.wall_min_length_m,
        cfg.line_max_gap_m,
        cfg.line_min_density,
        candidate_angles,
    )

    raw_layer_used = write_dxf_points(cfg.raw_plan_dxf, raw_xy, cfg.walls_layer)
    norm_layer_used = write_dxf_points(cfg.normalized_plan_dxf, snapped_xy, cfg.walls_layer)
    walls_layer_used = write_dxf_lines(cfg.wall_lines_dxf, wall_segments, cfg.walls_layer)

    warnings = []
    if was_sampled:
        warnings.append(
            f"Raw DXF was sampled from {len(raw_xy_full)} to {len(raw_xy)} points (raw_max_points={cfg.raw_max_points})."
        )
    if cfg.walls_layer != walls_layer_used:
        warnings.append(
            f"Layer name sanitized for DXF compatibility: '{cfg.walls_layer}' -> '{walls_layer_used}'"
        )
    warnings.append(
        "Wall-lines output uses gap-bridged vectorization with rotated orthogonal candidates; review/tune wall_min_length_m, line_max_gap_m, line_min_density, orthogonal_angle_jitter_deg, orthogonal_angle_step_deg, snap_grid_m."
    )

    report = {
        "input": str(cfg.primary_pointcloud),
        "raw_points_total": int(len(points)),
        "slice_target_z": target_z,
        "slice_points_count": int(len(raw_xy_full)),
        "raw_points_exported": int(len(raw_xy)),
        "normalized_points_count": int(len(snapped_xy)),
        "wall_segments_count": int(len(wall_segments)),
        "slice_height_m": cfg.slice_height_m,
        "slice_thickness_m": cfg.slice_thickness_m,
        "snap_grid_m": cfg.snap_grid_m,
        "wall_min_length_m": cfg.wall_min_length_m,
        "line_max_gap_m": cfg.line_max_gap_m,
        "line_min_density": cfg.line_min_density,
        "dominant_axis_alignment": cfg.dominant_axis_alignment,
        "line_angle_step_deg": cfg.line_angle_step_deg,
        "line_angles_deg": cfg.line_angles_deg,
        "orthogonal_pair_mode": cfg.orthogonal_pair_mode,
        "orthogonal_base_angle_deg": cfg.orthogonal_base_angle_deg,
        "orthogonal_angle_jitter_deg": cfg.orthogonal_angle_jitter_deg,
        "orthogonal_angle_step_deg": cfg.orthogonal_angle_step_deg,
        "candidate_angles_deg_used": candidate_angles,
        "raw_max_points": cfg.raw_max_points,
        "max_deviation_m_target": cfg.max_deviation_m,
        "outputs": {
            "raw_plan_dxf": str(cfg.raw_plan_dxf),
            "normalized_plan_dxf": str(cfg.normalized_plan_dxf),
            "wall_lines_dxf": str(cfg.wall_lines_dxf),
        },
        "layers_used_in_dxf": {
            "raw": raw_layer_used,
            "normalized": norm_layer_used,
            "walls": walls_layer_used,
        },
        "warnings": warnings,
    }

    cfg.qa_report_json.parent.mkdir(parents=True, exist_ok=True)
    cfg.qa_report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())