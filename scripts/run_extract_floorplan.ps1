param(
  [string]$Config = "work/floorplan_config.json"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path "scripts/extract_floorplan.py")) {
  throw "Chybi scripts/extract_floorplan.py. Spust nejdriv: git pull"
}
if (-not (Test-Path $Config)) {
  throw "Chybi config: $Config"
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
  $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
  throw "Python nebyl nalezen v PATH. Nainstaluj Python a spust znovu."
}

Write-Host "[1/2] Extracting floorplan from point cloud..."
& $pythonCmd.Source scripts/extract_floorplan.py --config "$Config"

Write-Host "[2/2] Done. Check output/floorplan_raw.dxf, output/floorplan_normalized.dxf, output/floorplan_walls.dxf, output/floorplan_qa.json"
