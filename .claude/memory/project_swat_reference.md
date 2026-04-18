---
name: SWAT Reference Info
description: SWAT test project paths, file format quirks, and template status — things not derivable from code alone
type: project
originSessionId: 88b1a5d4-a9c9-4ecc-9e65-eeee32f178a8
---
## Test Projects

- SWAT daily: `E:\DJBasin\TxtInOutFSB` (33 subbasins, 2008-2018)
- SWAT monthly: `E:\BMPs\TxtInOut` (62 subbasins, land_use: AGRL/URHD/WATR, 2019-2021)
- Command: `swat.exe`

## File Format Quirks

- SWAT files may contain non-UTF-8 chars (e.g. temperature unit ℃) — encoding fallback: try utf-8 first, then latin-1
- file.cio: fixed-format, fields located by line number (not label), `|` separates value from label
- .sub HRU file list: after "HRU: General" line, filenames are tightly concatenated (no delimiter), split by regex `\d{9}\.[a-zA-Z]{2,3}`
- .hru header: extract Luse/Soil/Slope via regex; Soil can contain spaces

## SWAT Template Status (2026-04-17)

All core modules complete: template.py, variables.py, discovery.py, builder.py, library.py, param_db.yaml (337 params).
Pending: unit tests for calcSwatOutputRows, builder 5 scenarios, discovery.

**How to apply:** Use test project paths when running integration tests. Remember encoding fallback when reading SWAT files.
