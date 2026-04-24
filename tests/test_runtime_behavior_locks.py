from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydro_pilot.runtime.context import apply_on_error_defaults
from hydro_pilot.runtime.errors import RunError
from hydro_pilot.evaluation import Evaluator
from hydro_pilot.params import ParamApplier, ParamSpace, ParamWritePlan
from hydro_pilot.series import ObsStore, SeriesExtractor, SeriesPlan
from hydro_pilot.reporting.records import build_csv_fields, collect_error_entries, parse_report_ids
from hydro_pilot.config.schema.series import ReaderSpec


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


def _fixed_width_param(name, start, file_name, bounds=(0.0, 10.0)):
    return {
        "name": name,
        "type": "float",
        "bounds": list(bounds),
        "writerType": "fixed_width",
        "file": {
            "name": file_name,
            "line": 1,
            "start": start,
            "width": 5,
            "precision": 1,
        },
    }


def _make_param_cfg(project_path, design, physical, transformer=None, hard_bound=True):
    return _ns(
        basic=_ns(projectPath=str(project_path)),
        parameters=_ns(
            design=design,
            physical=physical,
            transformer=transformer,
            hardBound=hard_bound,
        ),
    )


def test_param_manager_locks_design_to_physical_transform_result(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "params.txt").write_text("  1.0  2.0\n", encoding="ascii")

    cfg = _make_param_cfg(
        project_path=project,
        design=[
            {"name": "x1", "bounds": [0, 1]},
            {"name": "x2", "bounds": [0, 1]},
        ],
        physical=[
            _fixed_width_param("p1", 1, "params.txt"),
            _fixed_width_param("p2", 7, "params.txt"),
        ],
        transformer="expand_params",
    )

    class DummyFuncManager:
        def call(self, func_name, *args):
            assert func_name == "expand_params"
            assert np.allclose(args[0], np.array([1.0, 2.0]))
            return np.array([11.0, 22.0])

    space = ParamSpace(cfg.parameters.design)
    write_plan = ParamWritePlan(cfg)
    applier = ParamApplier(cfg, DummyFuncManager(), write_plan)

    assert space.get_param_info()[0] == 2
    assert applier.get_physical_params([1.0, 2.0]).tolist() == [11.0, 22.0]


def test_param_manager_locks_clamp_warning_aggregation(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "params_a.txt").write_text("  1.0\n", encoding="ascii")
    (project / "params_b.txt").write_text("  2.0\n", encoding="ascii")

    cfg = _make_param_cfg(
        project_path=project,
        design=[{"name": "x1", "bounds": [0, 1]}],
        physical=[
            _fixed_width_param(
                name="x1",
                start=1,
                file_name=["params_a.txt", "params_b.txt"],
                bounds=(0.0, 5.0),
            )
        ],
    )

    class DummyFuncManager:
        def call(self, func_name, *args):
            raise AssertionError("transform should not be called in direct mode")

    write_plan = ParamWritePlan(cfg)
    applier = ParamApplier(cfg, DummyFuncManager(), write_plan)

    work_path = tmp_path / "run"
    work_path.mkdir()
    context = {"warnings": []}
    applier.apply(str(work_path), np.array([10.0]), context)

    assert len(context["warnings"]) == 1
    warning = context["warnings"][0]
    assert warning.code == "CLAMPED"
    assert warning.target == "x1"
    assert "affected 2/2 files" in warning.message
    assert "clamped to 5" in warning.message
    assert "5.0" in (work_path / "params_a.txt").read_text(encoding="ascii")
    assert "5.0" in (work_path / "params_b.txt").read_text(encoding="ascii")


def test_series_extractor_locks_flow_sim_and_flow_obs_context_keys():
    sim_spec = object()
    obs_spec = object()

    class DummyCfg:
        series = [_ns(id="flow", sim=sim_spec, obs=obs_spec)]
        series_index = {"flow": _ns(sim=sim_spec)}

    class StubSeriesExtractor(SeriesExtractor):
        def _read_extract(self, workPath, extractSpec):
            if workPath is None:
                return np.array([100.0, 200.0])
            return np.array([1.0, 2.0])

    plan = SeriesPlan(DummyCfg().series)

    class StubObsStore(ObsStore):
        def _load_obs(self):
            return {"flow": np.array([100.0, 200.0])}

    obs_store = StubObsStore(plan)
    extractor = StubSeriesExtractor(DummyCfg(), func_manager=None, series_plan=plan, obs_store=obs_store)
    env = extractor.extract("work", {"warnings": []})

    assert env["flow.sim"].tolist() == [1.0, 2.0]
    assert env["flow.obs"].tolist() == [100.0, 200.0]


def test_sim_reader_spec_keeps_runtime_relative_file_path(tmp_path: Path):
    spec = ReaderSpec.from_raw(
        raw={
            "readerType": "text",
            "file": "output.rch",
            "rowRanges": [[1, 3]],
            "colSpan": [1, 10],
        },
        base_path=tmp_path,
        field_name="series[flow].sim",
        check_file=False,
    )

    assert str(spec.spec.file) == "output.rch"


def test_evaluator_locks_nonfatal_derived_failures_to_warning_and_nan():
    cfg = _ns(
        objectives=_ns(use=[], items={}),
        constraints=_ns(use=[], items={}),
        diagnostics=_ns(
            use=["diag_only"],
            items={"diag_only": _ns(ref="derived_only", on_error=-999.0)},
        ),
        derived=[
            _ns(id="derived_only", call=_ns(func="calc", args=["missing.sim"])),
        ],
    )

    class DummyFuncManager:
        def call(self, func_name, *args):
            raise AssertionError("derived function should not be called when dependency is missing")

    evaluator = Evaluator(cfg, DummyFuncManager())
    context = {"warnings": []}

    result = evaluator.evaluate_all(context)

    assert np.isnan(result["diag_only"])
    assert len(context["warnings"]) == 1
    assert context["warnings"][0].code == "DEPENDENCY_MISSING"
    assert context["warnings"][0].target == "derived_only"


def test_evaluator_locks_fatal_derived_failures_for_objective_dependency():
    cfg = _ns(
        objectives=_ns(
            use=["obj_flow"],
            items={"obj_flow": _ns(ref="derived_needed", sense="min", on_error=np.inf)},
        ),
        constraints=_ns(use=[], items={}),
        diagnostics=_ns(use=[], items={}),
        derived=[
            _ns(id="derived_needed", call=_ns(func="calc", args=["missing.sim"])),
        ],
    )

    class DummyFuncManager:
        def call(self, func_name, *args):
            raise AssertionError("derived function should not be called when dependency is missing")

    evaluator = Evaluator(cfg, DummyFuncManager())

    with pytest.raises(RunError, match="requires context key 'missing.sim'"):
        evaluator.evaluate_all({"warnings": []})


def test_context_locks_on_error_default_backfill():
    cfg = _ns(
        objectives=_ns(use=["obj"], items={"obj": _ns(on_error=-1.0)}),
        constraints=_ns(use=["con"], items={"con": _ns(on_error=999.0)}),
        diagnostics=_ns(use=["diag"], items={"diag": _ns(on_error=np.nan)}),
    )
    context = {}

    apply_on_error_defaults(context, cfg)

    assert context["obj"] == -1.0
    assert context["con"] == 999.0
    assert np.isnan(context["diag"])


def test_reporting_records_lock_summary_field_order_and_error_entry_semantics():
    cfg = _ns(
        series_index={"flow": object(), "sed": object()},
        objectives=_ns(use=["obj_b", "obj_a"]),
        constraints=_ns(use=["con_a"]),
        diagnostics=_ns(use=["diag_b", "diag_a"]),
        derived=[_ns(id="derived_2"), _ns(id="derived_1")],
        reporter=_ns(series=["flow", "sed_sim"]),
    )

    all_series_ids, all_scalar_ids, out_series_ids = parse_report_ids(cfg)
    fields = build_csv_fields(all_scalar_ids, ["x1", "x2"], ["p1"])
    entries = collect_error_entries(
        {"stage": "params", "code": "FILE_WRITE_ERROR", "target": "params.txt", "message": "failed"},
        [RunError(stage="series", code="FILE_READ_ERROR", target="flow", message="boom", severity="warning")],
    )

    assert all_series_ids == ["flow_sim", "sed_sim"]
    assert all_scalar_ids == [
        "obj_b",
        "obj_a",
        "con_a",
        "diag_b",
        "diag_a",
        "derived_2",
        "derived_1",
    ]
    assert out_series_ids == ["flow_sim", "sed_sim"]
    assert fields == [
        "batch_id",
        "run_id",
        "status",
        "obj_b",
        "obj_a",
        "con_a",
        "diag_b",
        "diag_a",
        "derived_2",
        "derived_1",
        "X_x1",
        "X_x2",
        "P_p1",
    ]
    assert entries[0]["stage"] == "params"
    assert entries[1]["stage"] == "series"
    assert entries[1]["severity"] == "warning"
