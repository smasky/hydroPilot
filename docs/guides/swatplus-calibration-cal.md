# SWAT+ `calibration.cal` Write Path

This guide explains how hydroPilot now writes SWAT+ calibration parameters through `calibration.cal` when you use `version: swatplus`.

## What changed

The SWAT+ template no longer writes parameter values directly back into source files such as `parameters.bsn` or `hydrology.hyd` during runtime.

Instead, the template now:

1. resolves the user-facing parameter configuration into physical calibration records
2. generates a `calibration.cal` skeleton for each instance
3. writes runtime values only into the `VAL` field of those records

In other words, SWAT+ parameter writing now follows a single-file calibration route, while SWAT 2012 remains on its own direct file-writing path.

## End-to-end flow

The current write chain is:

```text
version: swatplus
  -> SwatPlusTemplate.build_config()
  -> buildSwatPlusParams()
  -> formatted_text physical entries targeting calibration.cal
  -> ParamWritePlan
  -> instance initialization writes calibration.cal skeleton
  -> FormattedTextWriter writes runtime values into VAL column
```

## What the expanded physical entries look like

After template expansion, each SWAT+ physical parameter points to the same file:

```yaml
writerType: formatted_text
file:
  name: calibration.cal
  row: 5
  col: 30
  width: 16
  precision: 6
```

Key points:

- `name` is always `calibration.cal`
- `row` identifies the calibration record for that physical parameter
- `col` points to the `VAL` field
- `width` and `precision` follow the generic `formatted_text` writer contract

## How `mode` is translated

The SWAT+ template maps hydroPilot `mode` values to SWAT+ `CHG_TYPE` values:

| hydroPilot mode | SWAT+ `CHG_TYPE` | Meaning |
|---|---|---|
| `v` | `absval` | set an absolute value |
| `a` | `abschg` | apply an absolute change |
| `r` | `pctchg` | apply a percent change |

This mapping is handled in the SWAT+ model layer, not in the generic writer.

## How the skeleton is created

`calibration.cal` does not need to exist in the source project.

During instance initialization:

1. hydroPilot copies the source project into each run instance
2. the SWAT+ template-provided skeleton is written into `instance_x/calibration.cal`
3. deferred writer registrations are replayed against that generated file
4. runtime writes update only the `VAL` column

This keeps the runtime skeleton generic:

- the general layer knows only that some `formatted_text` tasks carry a skeleton
- the SWAT+ model layer decides what that skeleton contains

## What is already supported

Current migrated behavior:

- SWAT+ template emits `writerType: formatted_text`
- parameter writes are consolidated into `calibration.cal`
- skeleton generation is tied to resolved physical entries
- non-existent `calibration.cal` in the source project is supported
- row order, row count, parameter name order, and `CHG_TYPE` all follow the same resolved physical list

## What is not finished yet

The current route is intentionally minimal. These items are still pending:

- expanding SWAT+ `filter` into native calibration condition syntax (currently filter resolves to object IDs via metadata screening — native syntax like `cal_group`, `hsg`, texture is deferred)
- layer-level targeting (selectIndex, LYR1/LYR2) for soil parameters
- attribute-based channel selectors (name, order)
- end-to-end validation against more real SWAT+ projects and executables

Filter support by group: Group A (basin, global, no filter), Group B (HRU, 4 keys), Group C (channel, object_id only), Group D (soil, soil-name exact match). All four groups resolve to `OBJ_TOT` + IDs in calibration records.

## Example mental model

If the user writes:

```yaml
parameters:
  design:
    - name: esco
      bounds: [0.0, 1.0]
  physical:
    - name: esco
      mode: v
```

hydroPilot does not edit `hydrology.hyd` directly at runtime.

It creates a `calibration.cal` record similar in intent to:

```text
esco         absval         <VAL> ...
```

and then writes the sampled value into that record's `VAL` field.

## See also

- [SWAT+ template](../templates/swatplus.md)
- [SWAT+ flow extraction guide](swatplus-flow-extraction.md)
