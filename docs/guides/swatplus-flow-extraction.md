# SWAT+ Flow Extraction Guide

How to extract streamflow time series from SWAT+ output files using the hydroPilot `version: swatplus` template. This guide covers the three main routes for flow extraction and explains how the template resolves `variable` + `id` + `period` into concrete column and row positions.

## Quick reference: which file should I use?

| What you want | File | Variable | `id` means | Availability |
|---|---|---|---|---|
| Basin outlet water yield | `basin_wb_*.txt` | `WYLD` | always `1` | Always |
| HRU water yield | `hru_wb_*.txt` | `WYLD` | HRU number | Always |
| Hydrology outlet flow | `hydout_*.txt` | `FLOW_OUT` | hydrology object ID | Needs hydrology objects |
| Hydrology inlet flow | `hydin_*.txt` | `FLOW_IN` | hydrology object ID | Needs hydrology objects |
| Channel reach outflow | `channel_sd_*.txt` | `flo_out` | reach ID | Needs channel objects |

## Route 1: Basin outlet water yield

The most common route. Extracts total water yield at the basin outlet in mm. Equivalent to SWAT 2012's `output.sub` + `WYLD`.

**Variables available in the series database**: `PREC`, `ET`, `WYLD`, `PERC`, `SURQ`

**Frequency options:**

| Frequency | File name | Rows per year | Use case |
|---|---|---|---|
| Annual average (`aa`) | `basin_wb_aa.txt` | 1 | Annual water balance |
| Yearly (`yr`) | `basin_wb_yr.txt` | 1 | Year-by-year calibration |
| Monthly (`mo`) | `basin_wb_mo.txt` | 12 | Monthly calibration |
| Daily (`da`) | `basin_wb_da.txt` | 365 | Daily calibration |

**Example — monthly:**

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

- `variable: WYLD` — the template resolves `colSpan` from the series database automatically.
- `id: 1` — basin objects always use id 1 (there is one basin per project).
- `period: [2010, 2020]` — extracts years 2010 through 2020 inclusive. The template calculates `rowRanges` from project metadata.
- WYLD units are mm. To convert to m³/s, use a `derived` entry with the basin area.

**You do not need to write `colSpan` or `rowRanges` manually.** The template resolves both from the series database and project discovery metadata.

## Route 2: Hydrology outlet flow

Extracts flow (m³/s) at a specific hydrology object — the SWAT+ equivalent of a stream gauge. Corresponds to SWAT 2012's `output.rch` + `FLOW_OUT`.

**Variables available in the series database**: `FLOW_OUT`, `FLOW_IN`

**Frequency options:**

| Frequency | File name | Rows per year |
|---|---|---|
| Annual average (`aa`) | `hydout_aa.txt` | 1 |
| Yearly (`yr`) | `hydout_yr.txt` | 1 |
| Monthly (`mo`) | `hydout_mo.txt` | 12 |
| Daily (`da`) | `hydout_da.txt` | 365 |

**Example — daily:**

```yaml
series:
  - id: flow_at_gauge
    sim:
      file: hydout_da.txt
      variable: FLOW_OUT
      id: 1
      period: [2018, 2020]
    obs:
      file: obs_flow_daily.txt
      rowRanges: [[1, 1095]]
      colNum: 1
```

- `hydout_*.txt` reports flow in m³/s — no area conversion needed.
- `id` is the hydrology object number. It maps to the `hydro_name` column in `hru-data.hru` (e.g. `hyd0001` → id 1, `hyd0003` → id 3).

**How to find the correct id:**

1. Open the project's `hydrology.hyd` file. The first column (`name`) lists hydrology object names like `hyd0001`, `hyd0002`.
2. `id` = the numeric suffix: `hyd0003` → `id: 3`.
3. Alternatively, check `hru-data.hru`: the `hydro_name` column shows which hydrology object each HRU drains to.

## Route 3: Channel reach outflow

Extracts flow at a specific channel reach. Equivalent to SWAT 2012's `output.rch` + `FLOW_OUT` at a reach.

**Important:** This route requires channel objects in the project. Projects without routing (e.g. Ames_sub1 with channel count = 0 in `object.cnt`) cannot use this route.

**Variables available** (channel output): `flo_out`, `flo_in`, `evap`, `tlost`, `sed_out`

**Example — monthly:**

```yaml
series:
  - id: reach_flow
    sim:
      file: channel_sd_mo.txt
      variable: flo_out
      id: 3
      period: [2010, 2020]
    obs:
      file: obs_reach_flow.txt
      rowRanges: [[1, 132]]
      colNum: 1
```

- `id` is the reach number (1-based), matching the row order in `channel-lte.cha`.
- Channel output variable names differ from basin/hru output (e.g. `flo` not `FLOW_OUT`). Always use the exact name registered in the series database.

## SWAT 2012 → SWAT+ mapping

| SWAT 2012 | SWAT+ | Notes |
|---|---|---|
| `file: output.rch` + `FLOW_OUT` + `id: 33` | `file: hydout_*.txt` + `FLOW_OUT` + `id: <hyd_obj>` | Reach flow → hydrology object flow |
| `file: output.sub` + `WYLD` + `id: N` | `file: basin_wb_*.txt` + `WYLD` + `id: 1` | Subbasin yield → basin yield |
| `file: output.hru` + `WYLD` | `file: hru_wb_*.txt` + `WYLD` | HRU water yield |
| `period: [2010, 2015]` | `period: [2010, 2015]` | Same notation |

Key differences from SWAT 2012:

- SWAT 2012's `output.rch` splits into `hydout_*` (hydrology objects) and `channel_sd_*` (channel reaches) in SWAT+.
- SWAT 2012 reach IDs do not directly map to SWAT+ IDs — verify against the project's `hydrology.hyd` or `channel-lte.cha`.
- Basin output (`basin_wb_*`) is always available regardless of routing configuration.

## Configuration checklist

Follow these steps when writing a series entry for flow extraction:

1. **Pick the spatial target**
   - Basin outlet → `basin_wb_*.txt` + `WYLD` + `id: 1`
   - Stream gauge → `hydout_*.txt` + `FLOW_OUT` + `id: <hyd_id>`
   - Channel reach → `channel_sd_*.txt` + `flo_out` + `id: <reach_id>`

2. **Pick the temporal resolution**
   - Annual → `_aa.txt` or `_yr.txt`
   - Monthly → `_mo.txt`
   - Daily → `_da.txt`

3. **Set the time range**
   - `period: [start_year, end_year]` — inclusive of both endpoints

4. **Define observation data**
   - `obs.file` — path to observation file (relative to config location)
   - `obs.colNum` or `obs.colSpan` — column position of observed values

5. **Verify the spatial ID**
   - The template validates that `id` is within `[1, object_count]`. An out-of-range id raises a clear `ValueError`.

## What the template resolves automatically

You write this:

```yaml
sim:
  file: basin_wb_mo.txt
  variable: WYLD
  id: 1
  period: [2010, 2020]
```

The template resolves:

- `colSpan` — looked up from `swatplus_db.yaml` by matching the output file and variable name.
- `rowRanges` — calculated from project metadata (start year, end year, output frequency, object count, and header lines).
- `readerType` — set to `text` for fixed-width SWAT+ output files.

The expanded `_general.yaml` config will contain explicit `colSpan` and `rowRanges` — you can inspect it to verify the resolution.

## See also

- [SWAT+ template](../templates/swatplus.md) — full template reference for `version: swatplus`.
- [SWAT 2012 template](../templates/swat-2012.md) — the SWAT 2012 equivalent.
- [Configuration reference](../configuration-reference.md) — all general-mode fields.
