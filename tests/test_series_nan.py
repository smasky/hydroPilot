import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import numpy as np
import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydropilot.config.specs import CallSpec
from hydropilot.reporting import RunReporter
from hydropilot.runtime.context import create_context
from hydropilot.series import SeriesExtractor, SeriesPlan


@pytest.mark.parametrize("useCall", [False, True])
def test_nan_warning_is_saved_only_for_affected_run(tmp_path, useCall):
    simSpec = CallSpec(func="simulate", args=[]) if useCall else object()
    cfg = SimpleNamespace(
        series=[SimpleNamespace(id="flow", sim=simSpec, obs=object())],
        series_index={"flow": object()},
        objectives=SimpleNamespace(items=[]),
        constraints=SimpleNamespace(items=[]),
        diagnostics=SimpleNamespace(items=[]),
        derived=[],
        reporter=SimpleNamespace(series=["flow"]),
    )
    sourceObs = np.array([10.0, 20.0, 30.0])
    simRows = iter([np.array([10.0, np.nan, 30.0]), np.array([10.0, 20.0, 30.0])])
    obsStore = SimpleNamespace(get=lambda sid: sourceObs)
    funcManager = SimpleNamespace(call=lambda *args: next(simRows))
    extractor = SeriesExtractor(cfg, funcManager, SeriesPlan(cfg.series), obsStore)
    extractor._read_extract = lambda *args: next(simRows)

    badContext = extractor.extract(str(tmp_path), create_context([1.0], 0, 1))
    goodContext = extractor.extract(str(tmp_path), create_context([0.0], 1, 1))
    assert "error" not in badContext
    assert len(badContext["warnings"]) == 1
    notice = badContext["warnings"][0]
    assert notice.severity == "warning"
    assert notice.code == "SIM_NAN"
    assert notice.target == "flow.sim"
    assert "1/3 NaN" in notice.message
    assert np.isnan(badContext["flow.sim"][1])
    assert goodContext["warnings"] == []
    np.testing.assert_array_equal(badContext["flow.obs"], sourceObs)
    np.testing.assert_array_equal(goodContext["flow.obs"], [10.0, 20.0, 30.0])

    archive = tmp_path / "archive"
    with RunReporter(archive, ["x"], [], cfg) as reporter:
        reporter.submit(badContext)
        reporter.submit(goodContext)

    entries = [json.loads(line) for line in (archive / "error.jsonl").read_text().splitlines()]
    assert len(entries) == 1
    assert entries[0]["code"] == "SIM_NAN"
    assert entries[0]["severity"] == "warning"
    assert entries[0]["run"] == 1
    with sqlite3.connect(archive / "results.db") as conn:
        assert conn.execute("SELECT run_id, status FROM summary ORDER BY run_id").fetchall() == [
            (1, "warning"), (2, "ok"),
        ]
