param(
  [string]$Config = "work/floorplan_config.json"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path "scripts/autotune_floorplan.py")) {
  throw "Chybi scripts/autotune_floorplan.py. Spust nejdriv: git pull"
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

Write-Host "[1/2] Running autotune sweep..."
& $pythonCmd.Source scripts/autotune_floorplan.py --config "$Config"

Write-Host "[2/2] Done. Check work/autotune_report.json and work/floorplan_config.tuned.json"
