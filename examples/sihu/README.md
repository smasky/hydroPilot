# sihu SWAT2012 example

This example evaluates seven deterministic parameter vectors against 1461 daily flow observations for Reach 40, from 2011 through 2014. It uses 21 design variables, no transformer, the SWAT local parameter scopes and `original * (1 + r)` relative updates.

The SWAT project and executable are external inputs and are not included in this repository. Before running, adjust `basic.projectPath` and `basic.command` in [config.yaml](./config.yaml) for your machine. The current paths refer to the Linux development environment used to validate this example.

```bash
python examples/sihu/run_example.py
```

The script writes metrics to `work/sihu_calibration/results.json`. HydroPilot archives each run under the configured work directory. With `keepCopies: true` and `reset: false`, outputs and logs are retained and touched inputs are restored once when the session closes. Enable `reset` for per-simulation input restoration during debugging.

The sample points verify execution and extraction; they are not calibration optima. `FLOW_OUT` is the interpretation used for the legacy `scenario.obj` target, whose original reader implementation was unavailable.
