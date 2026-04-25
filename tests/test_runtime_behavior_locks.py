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
from hydro_pilot.runtime import Executor, Session
from hydro_pilot.evaluation import Evaluator
from hydro_pilot.params import ParamApplier, ParamSpace, ParamWritePlan
from hydro_pilot.series import ObsStore, SeriesExtractor, SeriesPlan
from hydro_pilot.api import BatchRunResult
from hydro_pilot.reporting.records import build_csv_fields, collect_error_entries, parse_report_ids
from hydro_pilot.config.schema.parameters import ParametersSpec
from hydro_pilot.config.schema.series import ReaderSpec


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


class _CloseReporter:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _CleanupWorkspace:
    def __init__(self):
        self.cleanup_count = 0

    def cleanup_instances(self):
        self.cleanup_count += 1


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
    parameters = ParametersSpec.from_raw(
        {
            "design": design,
            "physical": physical,
            "transformer": transformer,
            "hardBound": hard_bound,
        },
        project_path,
    )
    return _ns(
        basic=_ns(projectPath=str(project_path)),
        parameters=parameters,
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


def test_session_close_cleans_instances_by_default():
    session = Session.__new__(Session)
    session._closed = False
    session.cfg = _ns(basic=_ns(keepInstances=False))
    session.reporter = _CloseReporter()
    session.workspace = _CleanupWorkspace()

    Session.close(session)

    assert session.reporter.closed is True
    assert session.workspace.cleanup_count == 1


def test_session_close_keeps_instances_when_requested():
    session = Session.__new__(Session)
    session._closed = False
    session.cfg = _ns(basic=_ns(keepInstances=True))
    session.reporter = _CloseReporter()
    session.workspace = _CleanupWorkspace()

    Session.close(session)

    assert session.reporter.closed is True
    assert session.workspace.cleanup_count == 0


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
        objectives=_ns(items=[]),
        constraints=_ns(items=[]),
        diagnostics=_ns(
            items=[_ns(id="diag_only", ref="derived_only", on_error=-999.0)],
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
            items=[_ns(id="obj_flow", ref="derived_needed", sense="min", on_error=np.inf)],
        ),
        constraints=_ns(items=[]),
        diagnostics=_ns(items=[]),
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
        objectives=_ns(items=[_ns(id="obj", on_error=-1.0)]),
        constraints=_ns(items=[_ns(id="con", on_error=999.0)]),
        diagnostics=_ns(items=[_ns(id="diag", on_error=np.nan)]),
    )
    context = {}

    apply_on_error_defaults(context, cfg)

    assert context["obj"] == -1.0
    assert context["con"] == 999.0
    assert np.isnan(context["diag"])


def test_reporting_records_lock_summary_field_order_and_error_entry_semantics():
    cfg = _ns(
        series_index={"flow": object(), "sed": object()},
        objectives=_ns(items=[_ns(id="obj_b"), _ns(id="obj_a")]),
        constraints=_ns(items=[_ns(id="con_a")]),
        diagnostics=_ns(items=[_ns(id="diag_b"), _ns(id="diag_a")]),
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


def test_executor_run_returns_structured_batch_result():
    executor = Executor.__new__(Executor)
    executor.cfg = _ns(
        basic=_ns(parallel=1),
        parameters=_ns(physical=[_ns(name="p1"), _ns(name="p2")]),
        objectives=_ns(items=[_ns(id="obj_a"), _ns(id="obj_b")]),
        constraints=_ns(items=[_ns(id="con_a")]),
        diagnostics=_ns(items=[_ns(id="diag_a")]),
        series_index={"flow": _ns(size=2, sim=_ns(spec=None))},
        series=[object()],
    )
    executor.services = _ns(
        evaluator=_ns(nOutput=2, nConstraints=1),
    )
    executor.reporter = _ns(newBatchId=lambda: 1)
    executor.optSign = [1, -1]

    records = [
        {
            "i": 0,
            "obj_a": 1.0,
            "obj_b": 2.0,
            "con_a": 3.0,
            "diag_a": 4.0,
            "P": np.array([10.0, 20.0]),
            "flow.sim": np.array([100.0, 200.0]),
        },
        {
            "i": 1,
            "obj_a": 5.0,
            "obj_b": 6.0,
            "con_a": 7.0,
            "diag_a": 8.0,
            "P": np.array([30.0, 40.0]),
            "flow.sim": np.array([300.0, 400.0]),
        },
    ]

    executor._run_one = lambda X, i, batch_id: records[i]

    result = Executor.run(executor, np.array([[1.0, 2.0], [3.0, 4.0]]))

    assert isinstance(result, BatchRunResult)
    assert np.allclose(result.X, np.array([[1.0, 2.0], [3.0, 4.0]]))
    assert np.allclose(result.P, np.array([[10.0, 20.0], [30.0, 40.0]]))
    assert np.allclose(result.objs, np.array([[1.0, 2.0], [5.0, 6.0]]))
    assert np.allclose(result.cons, np.array([[3.0], [7.0]]))
    assert np.allclose(result.diags, np.array([[4.0], [8.0]]))
    assert set(result.series.keys()) == {"flow"}
    assert np.allclose(result.series["flow"], np.array([[100.0, 200.0], [300.0, 400.0]]))


def test_executor_run_pads_series_length_mismatch_with_nan_and_warning():
    executor = Executor.__new__(Executor)
    executor.cfg = _ns(
        basic=_ns(parallel=1),
        parameters=_ns(physical=[]),
        objectives=_ns(items=[_ns(id="obj_a")]),
        constraints=_ns(items=[]),
        diagnostics=_ns(items=[]),
        series_index={"flow": _ns(size=4, sim=_ns(spec=None))},
        series=[object()],
    )
    executor.services = _ns(
        evaluator=_ns(nOutput=1, nConstraints=0),
    )
    executor.reporter = _ns(newBatchId=lambda: 1)
    executor.optSign = [1]

    records = [
        {"i": 0, "obj_a": 1.0, "flow.sim": np.array([10.0, 20.0, 30.0, 40.0]), "warnings": []},
        {"i": 1, "obj_a": 2.0, "flow.sim": np.array([50.0, 60.0]), "warnings": []},
    ]

    executor._run_one = lambda X, i, batch_id: records[i]

    result = Executor.run(executor, np.array([[1.0], [2.0]]))

    assert np.allclose(result.objs, np.array([[1.0], [2.0]]))
    assert np.allclose(result.series["flow"][0], np.array([10.0, 20.0, 30.0, 40.0]))
    assert np.allclose(result.series["flow"][1, :2], np.array([50.0, 60.0]))
    assert np.isnan(result.series["flow"][1, 2])
    assert np.isnan(result.series["flow"][1, 3])
    assert len(records[1]["warnings"]) == 1
    assert records[1]["warnings"][0].code == "LENGTH_MISMATCH"


def test_executor_run_keeps_failed_series_row_as_nan():
    executor = Executor.__new__(Executor)
    executor.cfg = _ns(
        basic=_ns(parallel=1),
        parameters=_ns(physical=[]),
        objectives=_ns(items=[_ns(id="obj_a")]),
        constraints=_ns(items=[]),
        diagnostics=_ns(items=[]),
        series_index={"flow": _ns(size=3, sim=_ns(spec=None))},
        series=[object()],
    )
    executor.services = _ns(
        evaluator=_ns(nOutput=1, nConstraints=0),
    )
    executor.reporter = _ns(newBatchId=lambda: 1)
    executor.optSign = [1]

    records = [
        {"i": 0, "obj_a": 1.0, "flow.sim": np.array([1.0, 2.0, 3.0]), "warnings": []},
        {"i": 1, "obj_a": np.inf, "warnings": [], "error": RunError(stage="subprocess", code="TIMEOUT", target="simulation", message="failed")},
    ]

    executor._run_one = lambda X, i, batch_id: records[i]

    result = Executor.run(executor, np.array([[1.0], [2.0]]))

    assert np.allclose(result.series["flow"][0], np.array([1.0, 2.0, 3.0]))
    assert np.isnan(result.series["flow"][1]).all()
