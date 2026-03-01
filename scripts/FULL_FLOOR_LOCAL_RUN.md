# Full-floor local run (Windows) — pro začátečníka (anti-zaseknutí verze)

> Důležité: Do PowerShellu vkládej **jen příkazy**, ne celý text návodu.
> 
> Řádky jako „## Krok 1“ nebo „Očekávání“ jsou jen popis, ten se **nespouští**.

## 0) Nejrychlejší varianta (vše jedním příkazem)
Pokud nechceš spouštět každý krok ručně, použij nový pipeline wrapper:

```powershell
.\scripts\run_floorplan_pipeline.ps1
```

Tohle udělá automaticky:
- přípravu full-floor ZIP + report,
- vygenerování `work/floorplan_config.json`,
- první extrakci,
- autotune,
- aplikaci tuned configu,
- finální extrakci.

Volitelné přepínače:

```powershell
.\scripts\run_floorplan_pipeline.ps1 -RunAutotune:$false
.\scripts\run_floorplan_pipeline.ps1 -RunAutotune:$true -ApplyTunedConfig:$false
```

---

## 1) Otevři PowerShell a jdi do repo složky
Spusť přesně tento příkaz (uprav cestu jen pokud máš repo jinde):

```powershell
cd "C:\Users\vojacek\OneDrive\Atelier\_CODEX\PC_to_dwg\bim"
```

## 2) Stáhni nejnovější změny (aby existovaly skripty)
Tím opravíš chybu `scripts/full_floor_runner.py: No such file or directory`.

```powershell
git pull
```

## 3) Rychlá kontrola, že jsi ve správném repu
```powershell
git remote -v
git status
```

Očekávej remote na `https://github.com/pvojacek-n78/bim.git`.

## 4) Zkontroluj, že skripty opravdu existují
```powershell
Get-ChildItem scripts
```

Musíš vidět minimálně:
- `full_floor_runner.py`
- `run_full_floor.ps1`

## 5) Zkontroluj vstupní data
```powershell
Get-ChildItem input\pointcloud
Get-ChildItem input\templates
```

## 6) Ověř Git LFS (volitelné, ale doporučené)
```powershell
git lfs ls-files
git lfs pull
```

## 7) Spusť přípravu celého podlaží (nejjednodušší varianta)
Spusť **jediný** příkaz:

```powershell
.\scripts\run_full_floor.ps1
```

## 8) Zkontroluj výstupy
```powershell
Get-ChildItem work
Get-Content work\run_report.json
```

Měly by vzniknout:
- `work/full_floor.zip`
- `work/full_floor_extracted/`
- `work/run_report.json`

---

## Pokud chceš spouštět Python přímo
Použij **jednořádkový** příkaz (bez zalamování):

```powershell
python scripts/full_floor_runner.py --parts-glob "input/pointcloud/*.zip.*" --combined-zip "work/full_floor.zip" --extract-dir "work/full_floor_extracted" --report "work/run_report.json" --extract
```

---

## Nejčastější chyba z tvého logu (a proč vznikla)
- Vložil ses do PowerShellu i Markdown text (`##`, `-`, `````), takže ho PowerShell bral jako příkazy.
- Správně vkládej jen obsah uvnitř kódových bloků.


## 9) Další krok: připrav konfiguraci pro 2D půdorys
Jakmile máš úspěšně hotový `work/run_report.json` bez varování, spusť:

```powershell
.\scripts\run_prepare_floorplan.ps1
```

Vznikne:
- `work/floorplan_config.json` (konfigurace extrakce)
- `work/NEXT_STEP_CHECKLIST.md` (co přesně udělat před exportem DWG/DXF)

## 10) Co mi pak poslat
Pošli sem obsah těchto souborů:

```powershell
Get-Content work\floorplan_config.json
Get-Content work\NEXT_STEP_CHECKLIST.md
```

Podle toho nastavím přesná pravidla os/modulů a případně doladím mapování vrstev z `VZOR.dwg`.


## 11) Spusť první extrakci 2D půdorysu
Jakmile máš upravený `work/floorplan_config.json`, spusť:

```powershell
.\scripts\run_extract_floorplan.ps1
```

Vygeneruje se:
- `output/floorplan_raw.dxf`
- `output/floorplan_normalized.dxf`
- `output/floorplan_qa.json`
- `output/floorplan_walls.dxf`

## 12) Co zkontrolovat po běhu
```powershell
Get-Content output\floorplan_qa.json
```

Zkontroluj hlavně:
- `slice_points_count` > 0
- `normalized_points_count` > 0
- `wall_segments_count` > 0
- že vrstva bodů/čar odpovídá `layers.walls` v configu (nebo že je uvedena sanitizace v `layers_used_in_dxf`).

Poznámka: v této verzi už vzniká i `floorplan_walls.dxf` (multi-angle first-pass, nejen 0/90°).
Poznámka 2: při diakritice/nespeciálních znacích ve vrstvách se název automaticky převádí na ASCII-safe variantu pro kompatibilitu DXF parserů.


## 13) Když jsou linky děravé nebo špatně spojené
Uprav v `work/floorplan_config.json` sekci `extraction`:


Doporučený start (balanced):
- `slice_thickness_m = 0.15`
- `snap_grid_m = 0.02`
- `line_max_gap_m = 0.08`
- `line_min_density = 0.30`
- `wall_min_length_m = 0.50`
- `min_cell_hits = 3`
- `min_component_cells = 24`

- `line_max_gap_m` (doporučení 0.05 až 0.12):
  - vyšší = spojí více přerušených úseků
  - příliš vysoké = může spojit i to, co spojit nechceš
- `line_min_density` (doporučení 0.25 až 0.40):
  - nižší = toleruje větší mezery v datech
  - vyšší = přísnější, méně falešných spojení
- `wall_min_length_m` (doporučení 0.20 až 0.50):
  - nižší = více krátkých segmentů
  - vyšší = čistší výstup, ale může ztrácet drobné prvky
- `min_cell_hits` (doporučení 2 až 5):
  - vyšší = méně osamoceného šumu
  - příliš vysoké = může zahodit slabě naskenované části stěn
- `min_component_cells` (doporučení 16 až 80):
  - vyšší = odstraní malé ostrůvky nábytku/ruchu
  - příliš vysoké = může zahodit malé konstrukce

Po změně znovu spusť:

```powershell
.\scripts\run_extract_floorplan.ps1
```

A zkontroluj v `output/floorplan_qa.json` hlavně `wall_segments_count` a `warnings`.


## 14) Auto-tuning (když chceš, aby to ladilo parametry samo)

Spusť:

```powershell
.\scripts\run_autotune_floorplan.ps1
```

Co to udělá:
- vyzkouší více kombinací `line_max_gap_m`, `line_min_density`, `wall_min_length_m`, `orthogonal_angle_step_deg`, `orthogonal_angle_jitter_deg`,
- každou kombinaci vyexportuje do `work/autotune/<trial>/...`,
- vybere nejlepší kombinaci podle skóre kontinuity linek,
- uloží report do `work/autotune_report.json`,
- uloží doporučený config do `work/floorplan_config.tuned.json`.

Pak použij doporučený config:

```powershell
Copy-Item work\floorplan_config.tuned.json work\floorplan_config.json -Force
.\scripts\run_extract_floorplan.ps1
```


## 15) Git push krok po kroku (po úspěšném běhu)
Kopíruj po jednom řádku:

```powershell
git status
git add scripts docs
git commit -m "Improve rotated-orthogonal wall extraction and add one-command pipeline"
git push
```
