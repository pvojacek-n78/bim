param(
  [string]$PartsGlob = "input/pointcloud/*.zip.*",
  [string]$CombinedZip = "work/full_floor.zip",
  [string]$ExtractDir = "work/full_floor_extracted"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path "scripts/full_floor_runner.py")) {
  throw "Chybi scripts/full_floor_runner.py. Spust nejdriv: git pull"
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
  $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
  throw "Python nebyl nalezen v PATH. Nainstaluj Python a spust znovu."
}

Write-Host "[1/3] Running full-floor preparation..."
& $pythonCmd.Source scripts/full_floor_runner.py --parts-glob "$PartsGlob" --combined-zip "$CombinedZip" --extract-dir "$ExtractDir" --extract

Write-Host "[2/3] Checking outputs..."
if (-not (Test-Path "work/run_report.json")) {
  throw "Chybi work/run_report.json - beh nedokoncen korektne."
}

Write-Host "[3/3] Done. Open: work/run_report.json"
