"""Evaluate seven deterministic parameter vectors against sihu observations."""
from pathlib import Path
import json
import shutil
import sys
import time

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from hydropilot import SimModel


def main():
    configPath = Path(__file__).with_name("config.yaml")
    config = yaml.safe_load(configPath.read_text())
    projectPath = (configPath.parent / config["basic"]["projectPath"]).resolve()
    if not projectPath.exists():
        sourcePath = Path("/home/wmtsky/projects/swat2012/examples/sihu/TxtInOut")
        shutil.copytree(
            sourcePath,
            projectPath,
            ignore=shutil.ignore_patterns("output.*", "*.bak", "*.log", "*.exe", "*.out"),
        )
    if not (projectPath / "tmp1.tmp").exists():
        shutil.copy2(projectPath / "Tmp1.Tmp", projectPath / "tmp1.tmp")
    outputPath = ROOT / "work/sihu_calibration/results.json"
    rows = []
    with SimModel(str(configPath)) as model:
        midpoint = (np.asarray(model.lb) + np.asarray(model.ub)) / 2
        lower = np.asarray(model.lb)
        span = np.asarray(model.ub) - lower
        samples = [
            ("midpoint", midpoint),
            ("quantile_25", lower + 0.25 * span),
            ("quantile_75", lower + 0.75 * span),
        ]
        for label, parameter, value in [
            ("cn2_relative_1.1", "CN2", 1.1),
            ("esco_0.2", "ESCO.hru", 0.2),
            ("epco_0.8", "EPCO.hru", 0.8),
            ("surlag_4.0", "SURLAG.hru", 4.0),
        ]:
            vector = midpoint.copy()
            vector[model.xLabels.index(parameter)] = value
            samples.append((label, vector))
        print("Run directory:", model.runPath, flush=True)
        for label, vector in samples:
            assert np.all(vector >= lower) and np.all(vector <= lower + span)
            started = time.monotonic()
            result = model.run(vector)
            sim = result.series["flow"][0]
            obs = result.obs["flow"]
            assert sim.size == obs.size == 1461
            assert np.isfinite(sim).all() and np.isfinite(obs).all()
            assert np.isfinite(result.objs).all() and np.isfinite(result.diags).all()
            assert np.array_equal(result.P[0], vector)
            nse = float(1 - np.sum((sim - obs) ** 2) / np.sum((obs - obs.mean()) ** 2))
            assert np.isclose(nse, result.objs[0, 0])
            # Independently select reach/day rows to verify template extraction.
            allFlow = []
            for line in (Path(model.runPath) / "instance_0/output.rch").open():
                if line.startswith("REACH") and int(line[5:10]) == 40:
                    allFlow.append(float(line[51:61]))
            from datetime import date
            start = (date(2011, 1, 1) - date(2008, 1, 1)).days
            assert np.array_equal(sim, np.asarray(allFlow[start:start + 1461]))
            row = {
                "sample": label,
                "seconds": round(time.monotonic() - started, 2),
                "X": dict(zip(model.xLabels, map(float, vector))),
                "P": result.P[0].tolist(),
                "nse": nse,
                "rmse": float(result.diags[0, 0]),
                "pbias": float(result.diags[0, 1]),
                "length": int(sim.size),
                "nan_count": int(np.isnan(sim).sum()),
                "mean_sim": float(sim.mean()),
                "mean_obs": float(obs.mean()),
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
            outputPath.write_text(json.dumps({"run_path": str(model.runPath), "archive_path": str(model.archivePath), "config": str(configPath), "runs": rows}, indent=2))
    print("Finished; results:", outputPath, flush=True)


if __name__ == "__main__":
    main()
