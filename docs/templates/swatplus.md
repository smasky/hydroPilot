# SWAT+ Template

`version: swatplus` is the template for **SWAT+** (SWAT Plus) projects. It lets you write a compact, SWAT+-aware configuration — you declare parameter names and bounds, and the template generates calibration change records targeting `calibration.cal`. hydroPilot expands the template into a standard `version: general` config before execution.

## What the template expands into

| Aspect | Template input | Expanded general output |
|---|---|---|
| Writer type | implicit | `writerType: formatted_text` |
| Reader type | implicit | `readerType: text` |
| Parameter locations | variable name + mode + optional filter | calibration record in `calibration.cal` (`row`/`col`/`width`) |
| Series rows | `id` + `period` | calculated `rowRanges` |
| Series columns | `variable` name | resolved `colSpan` from SWAT+ series database |

The template expansion happens inside `SwatPlusTemplate.build_config()`. Parameter write targets are consolidated into a single `calibration.cal` file — the template generates a skeleton (header + placeholder records) at instance initialization and writes calibrated values into the `VAL` column at runtime.

## Configuration shape

### `version`

```yaml
version: swatplus
```

### `basic`

```yaml
basic:
  projectPath: ./Ames_sub1/TxtInOut
  workPath: ./work
  command: swatplus.exe
```

### `parameters`

Two-layer design:

- `design` — variables the optimizer sees (name, bounds, optional type, optional mode).
- `physical` — how those variables are written. The template generates `calibration.cal` records (SWAT+ parameter change format). The `mode` field maps to `CHG_TYPE`: `v` → `absval`, `a` → `abschg`, `r` → `pctchg`. When `physical` is omitted, defaults are filled from the SWAT+ parameter database.

```yaml
parameters:
  design:
    - name: surq_lag
      bounds: [0.05, 24.0]
    - name: esco
      bounds: [0.0, 1.0]

  physical:
    - name: surq_lag
      mode: v
    - name: esco
      mode: v
```

#### Parameter filtering

Filter which spatial objects a parameter applies to. The template resolves filter specs against project metadata and writes the matching object IDs into the `calibration.cal` record as an object-ID tail (`OBJ_TOT` + right-justified IDs).

**Support matrix:**

| Group | File | Object type | Supported filter keys | Notes |
|-------|------|-------------|----------------------|-------|
| A | `parameters.bsn` | basin (global) | none | OBJ_TOT=0 — global parameters, filter rejected at validation |
| B | `hydrology.hyd` | HRU | `object_id`, `lu_mgt`, `soil`, `hydro_name` | Resolved via `hru-data.hru` metadata |
| C | `hyd-sed-lte.cha` | channel reach | `object_id` (only) | Reach IDs = sequential row numbers in `channel-lte.cha` |
| D | `soils.sol` | soil selector, HRU-indexed calibration space | `soil` | User-facing selector is soil name; final calibration object IDs are HRU IDs |

Filter rules: list values within a key are OR, different keys are AND.

```yaml
physical:
  - name: esco
    mode: v
    filter:
      lu_mgt: cosy_lum          # Group B — HRU filter
  - name: ch_mann
    mode: v
    filter:
      object_id: [1, 3, 5]      # Group C — channel reach IDs
  - name: sol_bd
    mode: v
    filter:
      soil: soil_01             # Group D — soil name selector, resolves to HRU IDs
```

**Current filter boundaries:**

- Native calibration condition syntax (`cal_group`, `hsg`, texture, plant class, etc.) is not yet implemented — filters always resolve to object IDs.
- Soils.sol targeting in SWAT+ calibration is HRU-indexed. Soil/profile names are only used to discover which HRUs should be targeted.
- Soils.sol filter uses exact soil-name match. Hydro-suffixed variants (e.g., `soil_01-h1`) do not match their base name (`soil_01`) — use the exact name from `hru-data.hru`.
- Channel filter only supports `object_id` passthrough. Attribute-based channel selectors (name, order) are not implemented.
- Layer-level targeting (selectIndex, LYR1/LYR2) is not implemented — soil parameter changes apply to all layers of matched profiles.
- Non-HRU objects (aquifer, reservoir) are not yet supported for filter-based targeting.

### `series`

SWAT+ series describe how to extract simulation output from SWAT+ text output files.

```yaml
series:
  - id: flow
    sim:
      file: basin_wb_mo.txt
      variable: WYLD
      id: 1
      period: [2010, 2020]
    obs:
      file: obs_flow_monthly.txt
      rowRanges: [[1, 132]]
      colNum: 1
```

When `variable` is used, the template looks up the column range from the SWAT+ series database (`swatplus_db.yaml`).

### `functions`, `derived`, `objectives`

Same structure as general mode.

## Project discovery

The template reads the SWAT+ project directory to extract metadata:

| File | What is read |
|---|---|
| `file.cio` | File mappings (time.sim, print.prt, hru-data.hru, etc.) |
| `time.sim` | Simulation start/end years, step |
| `print.prt` | Output interval (monthly/daily/yearly), nyskip |
| `hru-data.hru` | HRU count, HRU attributes (lu_mgt, soil, hydro_name) |
| `channel-lte.cha` | Channel reach count for `hyd-sed-lte.cha` `object_id` validation |

This metadata is used to calculate `rowRanges` for series extraction and validate spatial IDs.

## Parameter database

The SWAT+ parameter database (`swatplus_db.yaml`) provides parameter names, types, and bounds for validation and default completion. Currently covers four file groups:

| Group | File | Parameter count | Status |
|---|---|---|---|
| A | `parameters.bsn` | 26 | Global (basin); no filter |
| B | `hydrology.hyd` | 14 | HRU filter: `object_id`, `lu_mgt`, `soil`, `hydro_name` |
| C | `hyd-sed-lte.cha` | 6 | Channel filter: `object_id` (reach IDs from `channel-lte.cha`) |
| D | `soils.sol` | 8 | Soil-name selector; calibration object space is HRU IDs |

All design parameters are written to a single `calibration.cal` file via `formatted_text` records — individual parameter file positions in the database are retained for forward compatibility but not used by the current writer path.

## Series database

The SWAT+ series database covers Tier 1 flow extraction files across all standard frequencies: `hydout`, `hydin`, `basin_wb`, and `channel_sd` at `aa` (annual average), `yr` (yearly), `mo` (monthly), and `da` (daily). Additional report types at non-`aa` frequencies are planned.

## See also

- [SWAT+ flow extraction guide](../guides/swatplus-flow-extraction.md) — how to extract streamflow from SWAT+ output files.
- [SWAT 2012 template](swat-2012.md) — the SWAT 2012 equivalent.
- [Configuration reference](../configuration-reference.md) — all general-mode fields.
