# SWAT+ Support Status

This document summarizes the current implemented scope of hydroPilot's SWAT+ support.

It is not a roadmap pitch. It is a factual status snapshot for the current codebase.

## Current headline

SWAT+ is now on its own template path under `version: swatplus`, with:

- template expansion
- project discovery
- parameter database support
- `calibration.cal`-based parameter writing
- Tier 1 flow-series extraction
- apply-path and session-path initialization aligned

SWAT+ and SWAT 2012 remain separate model templates.

## What is implemented

### 1. Template layer

Implemented:

- `version: swatplus`
- SWAT+ project discovery from real project files
- SWAT+-specific validation
- expansion into standard `version: general`

Current model entry point:

- [`src/hydropilot/models/swatplus/template.py`](/Users/smasky/Desktop/hydroPilot/hydroPilot/src/hydropilot/models/swatplus/template.py)

### 2. Parameter writing route

Implemented:

- SWAT+ parameter writing now targets `calibration.cal`
- template emits `writerType: formatted_text`
- skeleton deployment uses the shared initializer boundary
- missing `calibration.cal` in the source project is supported
- `apply_design` / `apply_physical` now initialize skeleton-provided files before writing

Key user-facing consequence:

- users no longer need to think in terms of direct runtime edits to `parameters.bsn` or `hydrology.hyd`

### 3. Parameter database

Current database groups:

| Group | File | Status |
|---|---|---|
| A | `parameters.bsn` | global (basin); no filter |
| B | `hydrology.hyd` | HRU filter: `object_id`, `lu_mgt`, `soil`, `hydro_name` |
| C | `hyd-sed-lte.cha` | channel filter: `object_id` (reach IDs from `channel-lte.cha`) |
| D | `soils.sol` | soil-name selector; calibration object space is HRU IDs |

All four groups are connected in the calibration-record path. Filter support varies by object type — see the filter semantics section below.

### 4. Series layer

Implemented:

- SWAT+ output discovery and extraction logic
- file + variable lookup from `swatplus_db.yaml`
- frequency handling for `aa / yr / mo / da`
- real SWAT+ naming support for `_mon.txt / _day.txt`

Tier 1 flow extraction coverage is in place for:

- `hydout`
- `hydin`
- `basin_wb`
- `channel_sd`

across:

- `aa`
- `yr`
- `mo`
- `da`

### 5. Real-machine verification completed

Verified on this machine:

- SWAT+ source compiles locally with `gfortran`
- the compiled binary runs successfully on `refdata/Ames_sub1`
- hydroPilot can generate a real SWAT+ output directory from a `version: swatplus` config
- apply/session initialization semantics are now aligned

## What is partially implemented

These areas exist, but are not yet complete end-state behavior:

### 1. Filter semantics

Implemented per-group:

| Group | File | Filter keys | Resolution |
|-------|------|-------------|------------|
| A | `parameters.bsn` | none | Global — OBJ_TOT=0 |
| B | `hydrology.hyd` | `object_id`, `lu_mgt`, `soil`, `hydro_name` | Via `hru-data.hru` metadata |
| C | `hyd-sed-lte.cha` | `object_id` only | Reach IDs = `channel-lte.cha` row numbers |
| D | `soils.sol` | `soil` (exact match) | Selector uses `hru-data.hru.soil`; calibration tail carries HRU IDs |

All groups resolve to `OBJ_TOT` + object-ID tail in `calibration.cal` skeleton.

Current boundaries:

- native calibration condition syntax (`cal_group`, `hsg`, texture, plant class, etc.) is not yet implemented — filter always resolves to object IDs
- soils.sol: calibration object space is HRU-indexed in SWAT+ (`case("sol") -> sp_ob%hru`); soil names are only the selector input
- soils.sol: hydro-suffixed soil names (`soil_01-h1`) do not match base names (`soil_01`) — exact match only
- channel: attribute-based selectors (name, order) are not implemented
- layer-level targeting (selectIndex, LYR1/LYR2) is not implemented
- non-HRU objects (aquifer, reservoir) are not yet supported

### 2. Calibration support depth across parameter groups

Current state:

- `parameters.bsn` and `hydrology.hyd` are the strongest connected groups

Not complete yet:

- richer selector strategy for `hyd-sed-lte.cha` beyond `object_id`
- richer selector strategy for `soils.sol` beyond exact `soil` name

### 3. Real-project coverage

Current state:

- `Ames_sub1` path is usable for real validation

Still needed:

- more real projects
- more project shapes
- more calibration-on/off combinations
- stronger result-difference verification after writing non-default calibration values

## What is not claimed yet

The current codebase does not yet justify claiming:

- full native SWAT+ calibration condition coverage
- full parity across all SWAT+ parameter families
- broad production validation across many SWAT+ projects
- completed native calibration condition syntax support

## Recommended next implementation priorities

If development continues from the current state, the most natural next steps are:

1. implement native calibration condition syntax (`cal_group`, `hsg`, texture, etc.) for cases where object-ID resolution is insufficient
2. deepen selector support for `hyd-sed-lte.cha` and `soils.sol`
3. validate parameter-effect observability on real SWAT+ projects
4. extend series coverage beyond Tier 1 flow outputs

## See also

- [SWAT+ template](../templates/swatplus.md)
- [SWAT+ `calibration.cal` write path](swatplus-calibration-cal.md)
- [SWAT+ `calibration.cal` user guide](swatplus-calibration-cal-user-guide.md)
- [SWAT+ flow extraction guide](swatplus-flow-extraction.md)
