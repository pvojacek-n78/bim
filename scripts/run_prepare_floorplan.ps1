param(
  [string]$Report = "work/run_report.json",
  [string]$Config = "work/floorplan_config.json",
  [string]$Checklist = "work/NEXT_STEP_CHECKLIST.md"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path "scripts/prepare_floorplan_step.py")) {
  throw "Chybi scripts/prepare_floorplan_step.py. Spust nejdriv: git pull"
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
  $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
  throw "Python nebyl nalezen v PATH. Nainstaluj Python a spust znovu."
}

Write-Host "[1/2] Preparing floorplan config..."
& $pythonCmd.Source scripts/prepare_floorplan_step.py --report "$Report" --config "$Config" --checklist "$Checklist"

Write-Host "[2/2] Done. Open: $Config and $Checklist"
