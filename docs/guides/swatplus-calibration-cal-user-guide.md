# SWAT+ `calibration.cal` User Guide

This guide focuses on how to use hydroPilot's SWAT+ template after the parameter-writing path moved to `calibration.cal`.

It is a user guide, not an internal design note.

## What you need to know first

When you use:

```yaml
version: swatplus
```

hydroPilot now writes SWAT+ calibration parameters through `calibration.cal`.

You do not need to:

- prepare line and column positions by hand
- edit `parameters.bsn`, `hydrology.hyd`, or similar files directly in your config
- create `calibration.cal` manually in the source project

The template handles those steps for you.

## Typical user workflow

The normal workflow is:

1. point `projectPath` to a SWAT+ project
2. declare design parameters in `parameters.design`
3. optionally refine how they should be written in `parameters.physical`
4. define output series and objectives
5. run hydroPilot as usual

For most users, the main difference from the old route is simple:

- before: think in terms of direct file edits
- now: think in terms of SWAT+ calibration records

## Minimal example

```yaml
version: swatplus

basic:
  projectPath: ./Ames_sub1/TxtInOut
  workPath: ./work
  command: swatplus.exe

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
      mode: a

series:
  - id: flow
    sim:
      file: hydout_mon.txt
      variable: FLOW_OUT
      id: 1
      period: [2010, 2020]
    obs:
      file: obs_flow_monthly.txt
      rowRanges: [[1, 132]]
      colNum: 1

objectives:
  - name: nse
    series: flow
    metric: nse
    sense: max
```

## How to think about `design` and `physical`

### `design`

`design` is what the optimizer sees.

Example:

```yaml
design:
  - name: esco
    bounds: [0.0, 1.0]
```

This means:

- the optimization variable is called `esco`
- hydroPilot will sample values within `[0.0, 1.0]`

### `physical`

`physical` controls how that parameter is written into SWAT+ calibration records.

Example:

```yaml
physical:
  - name: esco
    mode: v
```

This means:

- write `esco` through a `calibration.cal` record
- use `mode: v`, which maps to SWAT+ `CHG_TYPE = absval`

## `mode` mapping

hydroPilot `mode` values map to SWAT+ `CHG_TYPE` like this:

| `mode` | `CHG_TYPE` | Meaning |
|---|---|---|
| `v` | `absval` | assign an absolute value |
| `a` | `abschg` | apply an absolute change |
| `r` | `pctchg` | apply a percent change |

If you already know how SWAT 2012 modes were used in hydroPilot, the user-facing idea is still familiar. The main change is the final write target.

## Do I need to create `calibration.cal` myself?

No.

hydroPilot creates the instance-level `calibration.cal` file during initialization.

That means the source SWAT+ project can stay as-is, even if it does not already contain a `calibration.cal` file.

## Do I still need to care about source parameter files?

Usually no.

You still choose parameters by their SWAT+ names, but the template no longer asks you to think in terms of:

- which file the parameter originally came from
- where the line number is
- where the numeric column starts

That knowledge stays inside the template and parameter database.

## Using filters

Filter support varies by parameter group. The template resolves filter specs against project metadata and writes matched object IDs into the `calibration.cal` record tail (`OBJ_TOT` + right-justified IDs).

**Per-group filter support:**

| Group | File | Filter keys | Example |
|-------|------|-------------|---------|
| A | `parameters.bsn` | none (global) | No filter — basin-wide parameters |
| B | `hydrology.hyd` | `object_id`, `lu_mgt`, `soil`, `hydro_name` | `filter: {lu_mgt: cosy_lum}` |
| C | `hyd-sed-lte.cha` | `object_id` only | `filter: {object_id: [1, 3, 5]}` |
| D | `soils.sol` | `soil` (exact match) | `filter: {soil: soil_01}` |

```yaml
physical:
  - name: esco
    mode: v
    filter:
      lu_mgt: cosy_lum          # HRU filter — 4 supported keys
  - name: ch_mann
    mode: v
    filter:
      object_id: [2, 4]         # Channel reach IDs (from channel-lte.cha)
  - name: sol_bd
    mode: v
    filter:
      soil: soil_01             # Soil name selector; final calibration IDs are HRU IDs
```

Filter rules: list values within a key are OR, different keys are AND.

## What is already stable

These parts are already in place:

- SWAT+ template writes through `calibration.cal`
- `formatted_text` is the generic writer used underneath
- `calibration.cal` skeleton creation is automatic
- source projects do not need a pre-existing `calibration.cal`
- Tier 1 flow extraction for SWAT+ output is already documented and available

## What is still a current boundary

You should still treat these as current boundaries:

- native calibration condition syntax (`cal_group`, `hsg`, texture, plant class, etc.) is not yet implemented — filters always resolve to object IDs
- soils.sol targeting in SWAT+ calibration is HRU-indexed. Soil/profile names are only used to find matching HRUs.
- soils.sol filter uses exact soil-name match; hydro-suffixed variants (`soil_01-h1`) do not match their base name (`soil_01`)
- channel filter only supports `object_id` passthrough; attribute-based selectors (name, order) are not implemented
- layer-level targeting (selectIndex, LYR1/LYR2) is not implemented for soil parameters
- non-HRU objects (aquifer, reservoir) are not yet supported
- broader real-project verification is still worth continuing

This means the route is now the official main direction, but some deeper corners are still being filled in.

## Recommended reading order

If you are using SWAT+ for the first time in hydroPilot, read in this order:

1. [SWAT+ template](../templates/swatplus.md)
2. [SWAT+ `calibration.cal` write path](swatplus-calibration-cal.md)
3. [SWAT+ flow extraction guide](swatplus-flow-extraction.md)

## Summary

As a user, the practical takeaway is simple:

- keep writing `version: swatplus`
- declare parameters in template form
- let hydroPilot generate and manage `calibration.cal`
- focus on parameter meaning, mode, and calibration goals instead of file positions
