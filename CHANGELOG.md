# Change log

## 0.1.4 — 2026-10-02

### Runtime and UQPyL

- Separate parameter application, simulation and post-processing through internal `_apply`, `_simulate` and `_post` stages. `SimModel.run(X)` remains the standalone public entry point.
- Adapt native UQPyL `ModelProblem` interfaces with independent simulation contexts. Objective and constraint calls use the supplied context, validate its ownership and parameters, and reuse computed dependencies.
- Support simulation series without observations for ordinary optimization. Run-specific simulation NaNs produce warnings without changing shared observations or masks.

### Archiving and workspace

- Archive simulation snapshots before post-processing, then update the same `(batch_id, run_id)` record. SQLite commits precede CSV exports.
- Resume batch numbering from compatible existing archives. Rebuild incompatible archives when summary fields change.
- Report archive submission failures as warnings while preserving returned computation results.
- Rename `basic.keepInstances` to `basic.keepCopies`. Retained copies restore touched inputs to their session-start contents on close while keeping outputs and logs.
- Keep `basic.reset`, defaulting to `false`, for restoring inputs after each simulation during debugging.

### Parameters and SWAT

- Fix CN2 fixed-width input handling and preserve delimiters and comments.
- Handle different HRU soil-layer counts: warn and skip partially missing selected layers, and reject selections with no writable targets.
- Separate parameter names from `scope`. Ambiguous SWAT names default to the local HRU or management definition; explicit `scope: bsn` selects the basin definition.
- Validate design/physical parameter identities and scoped labels. Relative mode remains `original * (1 + r)`; the optional transformer remains available.
- Add the sihu configuration and deterministic evaluation example. Include SWAT+ parameter data in distribution packages.

### Validation

- Full local suite: **331 passed, 4 skipped**. Skipped cases require unavailable real-project paths.
- SWAT2012 sihu: seven deterministic 1461-day runs with no simulation NaNs. A further retained-copy check restored all 494 touched input files while preserving outputs, logs and archive records.
- These checks cover the generic runtime and SWAT2012 sihu; they do not establish complete real-model validation for every registered template.

### Configuration changes

- Use `keepCopies` in place of `keepInstances`.
- Use separate `name` and `scope` fields in SWAT template parameters.
- UQPyL integration currently requires the updated development checkout exposing `SimContext`, `SimulatorBase` and `ModelEvaluatorBase`. The published PyPI UQPyL 2.1.6 lacks these interfaces; its version number alone does not establish compatibility. Importing the adapter with that package now gives an explicit dependency error.
