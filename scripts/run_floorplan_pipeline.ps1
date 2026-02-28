param(
  [string]$PartsGlob = "input/pointcloud/*.zip.*",
  [string]$CombinedZip = "work/full_floor.zip",
  [string]$ExtractDir = "work/full_floor_extracted",
  [string]$Report = "work/run_report.json",
  [string]$Config = "work/floorplan_config.json",
  [switch]$RunAutotune = $true,
  [switch]$ApplyTunedConfig = $true
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path "scripts/run_full_floor.ps1")) { throw "Chybi scripts/run_full_floor.ps1. Spust nejdriv: git pull" }
if (-not (Test-Path "scripts/run_prepare_floorplan.ps1")) { throw "Chybi scripts/run_prepare_floorplan.ps1. Spust nejdriv: git pull" }
if (-not (Test-Path "scripts/run_extract_floorplan.ps1")) { throw "Chybi scripts/run_extract_floorplan.ps1. Spust nejdriv: git pull" }
if ($RunAutotune -and -not (Test-Path "scripts/run_autotune_floorplan.ps1")) { throw "Chybi scripts/run_autotune_floorplan.ps1. Spust nejdriv: git pull" }

Write-Host "[1/5] Full-floor prepare"
& .\scripts\run_full_floor.ps1 -PartsGlob "$PartsGlob" -CombinedZip "$CombinedZip" -ExtractDir "$ExtractDir"

Write-Host "[2/5] Build floorplan config"
& .\scripts\run_prepare_floorplan.ps1 -Report "$Report" -Config "$Config"

Write-Host "[3/5] First extraction"
& .\scripts\run_extract_floorplan.ps1 -Config "$Config"

if ($RunAutotune) {
  Write-Host "[4/5] Autotune"
  & .\scripts\run_autotune_floorplan.ps1 -Config "$Config"

  if ($ApplyTunedConfig) {
    if (-not (Test-Path "work/floorplan_config.tuned.json")) {
      throw "Chybi work/floorplan_config.tuned.json po autotune"
    }
    Copy-Item "work/floorplan_config.tuned.json" "$Config" -Force
    Write-Host "Applied tuned config -> $Config"

    Write-Host "[5/5] Final extraction with tuned config"
    & .\scripts\run_extract_floorplan.ps1 -Config "$Config"
  } else {
    Write-Host "[5/5] Skipped applying tuned config (--ApplyTunedConfig not used)"
  }
} else {
  Write-Host "[4/5] Autotune skipped"
  Write-Host "[5/5] Pipeline done"
}

Write-Host "Done. Check output/floorplan_qa.json and work/autotune_report.json"