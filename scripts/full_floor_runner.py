#!/usr/bin/env python3
import argparse
import json
import shutil
import zipfile
from pathlib import Path

POINT_EXTS = {'.e57', '.las', '.laz', '.rcp', '.rcs'}


def is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open('r', encoding='utf-8', errors='ignore') as f:
            first = f.readline().strip()
        return first == 'version https://git-lfs.github.com/spec/v1'
    except Exception:
        return False


def combine_split_zip(parts_glob: str, output_zip: Path) -> list[str]:
    parts = sorted(Path().glob(parts_glob))
    if not parts:
        raise FileNotFoundError(f'No files found for pattern: {parts_glob}')
    if any(is_lfs_pointer(p) for p in parts):
        raise RuntimeError('Input split ZIP parts are Git LFS pointers, not real binary data.')

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with output_zip.open('wb') as out:
        for p in parts:
            with p.open('rb') as src:
                shutil.copyfileobj(src, out)
    return [str(p) for p in parts]


def extract_zip(input_zip: Path, extract_dir: Path) -> None:
    if is_lfs_pointer(input_zip):
        raise RuntimeError('Combined ZIP is still an LFS pointer, cannot extract.')
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_zip, 'r') as zf:
        zf.extractall(extract_dir)


def find_pointcloud_files(root: Path) -> list[str]:
    files = []
    for p in root.rglob('*'):
        if p.is_file() and p.suffix.lower() in POINT_EXTS:
            files.append(str(p))
    return sorted(files)


def main() -> int:
    ap = argparse.ArgumentParser(description='Prepare full-floor input package from split ZIP and inspect payload.')
    ap.add_argument('--parts-glob', default='input/pointcloud/*.zip.*', help='Glob for split ZIP chunks')
    ap.add_argument('--combined-zip', default='work/full_floor.zip', help='Path to combined ZIP output')
    ap.add_argument('--extract-dir', default='work/full_floor_extracted', help='Extraction directory')
    ap.add_argument('--report', default='work/run_report.json', help='JSON report path')
    ap.add_argument('--extract', action='store_true', help='Extract combined ZIP')
    args = ap.parse_args()

    combined_zip = Path(args.combined_zip)
    extract_dir = Path(args.extract_dir)
    report_path = Path(args.report)

    report = {
        'parts_glob': args.parts_glob,
        'combined_zip': str(combined_zip),
        'extract_dir': str(extract_dir),
        'parts': [],
        'warnings': [],
        'pointcloud_files': [],
    }

    try:
        report['parts'] = combine_split_zip(args.parts_glob, combined_zip)
    except Exception as e:
        report['warnings'].append(str(e))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
        return 2

    if args.extract:
        try:
            extract_zip(combined_zip, extract_dir)
        except Exception as e:
            report['warnings'].append(str(e))

    if extract_dir.exists():
        report['pointcloud_files'] = find_pointcloud_files(extract_dir)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
