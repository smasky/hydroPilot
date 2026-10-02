from pathlib import Path
from types import SimpleNamespace
import sqlite3
import logging
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydropilot.runtime.context import apply_on_error_defaults
from hydropilot.runtime.errors import RunError
from hydropilot.runtime import Executor, Session, Workspace
from hydropilot.evaluation import Evaluator
from hydropilot.params import ParamApplier, ParamSpace, ParamWritePlan
from hydropilot.series import ObsStore, SeriesExtractor, SeriesPlan
from hydropilot.api import BatchRunResult
from hydropilot.reporting import RunReporter
from hydropilot.reporting.storage import readLastBatchId
from hydropilot.reporting.records import build_csv_fields, collect_error_entries, parse_report_ids
from hydropilot.config.schema.parameters import ParametersSpec
from hydropilot.config.schema.series import ReaderSpec


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


def _copyPostValues(context, state, targets):
    state.values.update(context)
    state.completed.update(targets)


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
            _fixed_width_param("p2", 6, "params.txt"),
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
    write_plan.initialize(str(project))

    assert space.get_param_info()[0] == 2
    assert applier.get_physical_params([1.0, 2.0]).tolist() == [11.0, 22.0]


def test_session_close_cleans_instances_by_default():
    session = Session.__new__(Session)
    session._closed = False
    session._inputSnapshots = []
    session.cfg = _ns(basic=_ns(keepCopies=False))
    session.reporter = _CloseReporter()
    session.workspace = _CleanupWorkspace()

    Session.close(session)

    assert session.reporter.closed is True
    assert session.workspace.cleanup_count == 1


def test_session_close_keeps_instances_when_requested():
    session = Session.__new__(Session)
    session._closed = False
    session._inputSnapshots = []
    session.cfg = _ns(basic=_ns(keepCopies=True))
    session.reporter = _CloseReporter()
    session.workspace = _CleanupWorkspace()

    Session.close(session)

    assert session.reporter.closed is True
    assert session.workspace.cleanup_count == 0


def test_workspace_reuses_named_work_dir_and_fills_missing_instances(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "params.txt").write_text("source\n", encoding="ascii")

    work = tmp_path / "work"
    run_path = work / "named_run"
    inst0 = run_path / "instance_0"
    inst0.mkdir(parents=True)
    (inst0 / "params.txt").write_text("existing\n", encoding="ascii")

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("version: general\n", encoding="utf-8")
    cfg = _ns(
        basic=_ns(
            projectPath=project,
            workPath=work,
            workDirName="named_run",
            parallel=2,
        ),
        series=[],
    )

    workspace = Workspace(cfg, str(cfg_path))

    assert workspace.runPath == run_path
    assert (run_path / "instance_0" / "params.txt").read_text(encoding="ascii") == "existing\n"
    assert (run_path / "instance_1" / "params.txt").read_text(encoding="ascii") == "source\n"
    assert (run_path / "archive" / "config.yaml").exists()


def test_session_reporter_uses_physical_parameter_labels_without_transformer():
    cfg = _ns(
        parameters=_ns(
            transformer=None,
            physical=[
                _ns(name="p1"),
                _ns(name="p2"),
            ],
        )
    )

    assert Session._physical_parameter_labels(cfg) == ["p1", "p2"]


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
    project_run = work_path
    project_run.mkdir()
    (project_run / "params_a.txt").write_text("  1.0\n", encoding="ascii")
    (project_run / "params_b.txt").write_text("  2.0\n", encoding="ascii")
    write_plan.initialize(str(project_run))
    context = {"warnings": []}
    applier.apply(str(project_run), np.array([10.0]), context)

    assert len(context["warnings"]) == 1
    warning = context["warnings"][0]
    assert warning.code == "CLAMPED"
    assert warning.target == "x1"
    assert "affected 2/2 files" in warning.message
    assert "clamped to 5" in warning.message
    assert "5.0" in (project_run / "params_a.txt").read_text(encoding="ascii")
    assert "5.0" in (project_run / "params_b.txt").read_text(encoding="ascii")


def test_param_write_plan_isolates_handlers_per_instance(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "params.txt").write_text("  1.0  2.0\n", encoding="ascii")

    cfg = _make_param_cfg(
        project_path=project,
        design=[
            {"name": "x1", "bounds": [0, 10]},
            {"name": "x2", "bounds": [0, 10]},
        ],
        physical=[
            _fixed_width_param("x1", 1, "params.txt"),
            _fixed_width_param("x2", 6, "params.txt"),
        ],
    )

    class DummyFuncManager:
        def call(self, func_name, *args):
            raise AssertionError("transform should not be called in direct mode")

    write_plan = ParamWritePlan(cfg)
    applier = ParamApplier(cfg, DummyFuncManager(), write_plan)

    inst0 = tmp_path / "instance_0"
    inst1 = tmp_path / "instance_1"
    inst0.mkdir()
    inst1.mkdir()
    (inst0 / "params.txt").write_text("  1.0  2.0\n", encoding="ascii")
    (inst1 / "params.txt").write_text("  1.0  2.0\n", encoding="ascii")

    write_plan.initialize(str(inst0))
    write_plan.initialize(str(inst1))

    task0 = next(iter(write_plan.get_instance_tasks(str(inst0)).values()))
    task1 = next(iter(write_plan.get_instance_tasks(str(inst1)).values()))
    assert task0["handler"] is not task1["handler"]

    applier.apply(str(inst0), np.array([3.0, 4.0]), {"warnings": []})
    applier.apply(str(inst1), np.array([7.0, 8.0]), {"warnings": []})

    assert "3.0" in (inst0 / "params.txt").read_text(encoding="ascii")
    assert "4.0" in (inst0 / "params.txt").read_text(encoding="ascii")
    assert "7.0" in (inst1 / "params.txt").read_text(encoding="ascii")
    assert "8.0" in (inst1 / "params.txt").read_text(encoding="ascii")


def test_executor_reset_restores_touched_inputs_and_keeps_outputs(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "params.txt").write_text("  1.0\n", encoding="ascii")

    cfg = _make_param_cfg(
        project_path=project,
        design=[{"name": "x1", "bounds": [0, 10]}],
        physical=[_fixed_width_param("x1", 1, "params.txt")],
    )
    cfg.basic.command = "noop"
    cfg.basic.timeout = -1
    cfg.basic.parallel = 1
    cfg.basic.reset = True

    class DummyFuncManager:
        def call(self, func_name, *args):
            raise AssertionError("transform should not be called in direct mode")

    class DummyRunner:
        def run(self, work_path, command, timeout):
            (Path(work_path) / "output.rch").write_text("result\n", encoding="ascii")
            return 0

    class DummyExtractor:
        def extract(self, work_path, context):
            return context

    class DummyEvaluator:
        def evaluate_all(self, context):
            return {"obj": 1.0}

    class DummyWorkspace:
        def __init__(self, path):
            self.path = str(path)
            self.archivePath = path / "archive"
            self.released = []

        def acquire_instance(self):
            return self.path

        def release_instance(self, path):
            self.released.append(path)

    instance = tmp_path / "instance_0"
    instance.mkdir()
    (instance / "params.txt").write_text("  1.0\n", encoding="ascii")

    write_plan = ParamWritePlan(cfg)
    write_plan.initialize(str(instance))
    applier = ParamApplier(cfg, DummyFuncManager(), write_plan)

    executor = Executor.__new__(Executor)
    executor.initializeBatchCounter(0)
    executor.cfg = cfg
    executor.workspace = DummyWorkspace(instance)
    executor.reporter = None
    executor.services = _ns(
        paramWritePlan=write_plan,
        paramApplier=applier,
        runner=DummyRunner(),
        seriesExtractor=DummyExtractor(),
        evaluator=DummyEvaluator(),
    )
    from hydropilot.runtime.input_restore import InputRestorer
    executor.inputRestorer = InputRestorer(write_plan)

    context = Executor._run_one(executor, np.array([9.0]), 0, 1)

    assert "obj" not in context
    np.testing.assert_array_equal(context["P"], [9.0])
    assert (instance / "params.txt").read_text(encoding="ascii") == "  1.0\n"
    assert (instance / "output.rch").read_text(encoding="ascii") == "result\n"
    assert executor.workspace.released == [str(instance)]


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
        objectives=_ns(items=[_ns(id="obj_b"), _ns(id="obj_a", on_error=np.inf)]),
        constraints=_ns(items=[_ns(id="con_a")]),
        diagnostics=_ns(items=[_ns(id="diag_b"), _ns(id="diag_a")]),
        derived=[_ns(id="derived_2"), _ns(id="derived_1")],
        reporter=_ns(series=["flow", "sed.sim"]),
    )

    all_series_ids, all_scalar_ids, out_series_ids = parse_report_ids(cfg)
    fields = build_csv_fields(all_scalar_ids, ["x1", "x2"], ["p1"])
    entries = collect_error_entries(
        {"stage": "params", "code": "FILE_WRITE_ERROR", "target": "params.txt", "message": "failed"},
        [RunError(stage="series", code="FILE_READ_ERROR", target="flow", message="boom", severity="warning")],
    )

    assert all_series_ids == ["flow.sim", "sed.sim"]
    assert all_scalar_ids == [
        "obj_b",
        "obj_a",
        "con_a",
        "diag_b",
        "diag_a",
        "derived_2",
        "derived_1",
    ]
    assert out_series_ids == ["flow.sim", "sed.sim"]
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
        "sim_status",
        "obj_state",
        "con_state",
        "diag_state",
    ]
    assert entries[0]["stage"] == "params"
    assert entries[1]["stage"] == "series"
    assert entries[1]["severity"] == "warning"


def test_runtime_continues_batch_id_from_existing_results_db(tmp_path: Path):
    archive = tmp_path / "archive"
    archive.mkdir()
    with sqlite3.connect(archive / "results.db") as connection:
        connection.execute("CREATE TABLE summary (batch_id INTEGER, run_id INTEGER, status TEXT)")
        connection.execute("INSERT INTO summary VALUES (3, 1, 'ok')")
    executor = Executor.__new__(Executor)
    executor.initializeBatchCounter(0)
    executor.initializeBatchCounter(readLastBatchId(archive))
    assert executor._nextBatchId() == 4


def test_runtime_falls_back_to_summary_csv_for_existing_batch_id(tmp_path: Path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "summary.csv").write_text(
        "batch_id,run_id,status,X_x1\n1,1,ok,0.1\n5,1,ok,0.5\n",
        encoding="utf-8-sig",
    )
    executor = Executor.__new__(Executor)
    executor.initializeBatchCounter(0)
    executor.initializeBatchCounter(readLastBatchId(archive))
    assert executor._nextBatchId() == 6


@pytest.mark.parametrize("reporterState", ["closed", "crashed"])
@pytest.mark.parametrize("modelFails", [False, True])
def test_reporter_submit_failure_is_warning_and_preserves_run_results(
    tmp_path, caplog, reporterState, modelFails,
):
    cfg = _ns(
        basic=_ns(parallel=1, reset=False, command="noop", timeout=-1),
        parameters=_ns(physical=[_ns(name="p")]),
        objectives=_ns(items=[_ns(id="NSE", on_error=-np.inf)]),
        constraints=_ns(items=[_ns(id="balance", on_error=np.inf)]),
        diagnostics=_ns(items=[_ns(id="RMSE", on_error=np.nan)]),
        series=[_ns(id="flow")],
        series_index={"flow": _ns(size=2, sim=_ns(spec=None))},
        derived=[],
        reporter=_ns(series=[]),
    )
    reporter = RunReporter(tmp_path / "archive", ["x"], ["p"], cfg)
    if reporterState == "closed":
        reporter.close()
    else:
        reporter._crashEvent.set()

    def runModel(*args):
        if modelFails:
            raise RunError(stage="subprocess", code="TIMEOUT", target="simulation", message="failed")

    def extractSeries(workPath, context):
        context["flow.sim"] = np.array([10.0, 20.0])
        return context

    released = []
    executor = Executor.__new__(Executor)
    executor.initializeBatchCounter(0)
    executor.nInput = 1
    executor.optSign = [-1]
    executor.cfg = cfg
    executor.reporter = reporter
    executor.workspace = _ns(
        archivePath=reporter.archivePath,
        acquire_instance=lambda: str(tmp_path),
        release_instance=lambda path: released.append(path),
    )
    executor.services = _ns(
        paramApplier=_ns(apply=lambda workPath, X, context: context.update(P=X.copy())),
        runner=_ns(run=runModel),
        seriesExtractor=_ns(extract=extractSeries),
        evaluator=_ns(
            nOutput=1, nConstraints=1,
            _post=lambda context, state, targets: _copyPostValues({"NSE": 0.8, "balance": 0.0, "RMSE": 2.0}, state, targets),
        ),
        obsStore=_ns(get=lambda sid: np.array([10.0, 20.0])),
    )
    contexts = []
    originalRunOne = executor._run_one

    def captureRun(*args):
        context = originalRunOne(*args)
        contexts.append(context)
        return context

    executor._run_one = captureRun
    try:
        with caplog.at_level(logging.WARNING, logger="hydropilot.runtime.executor"):
            result = executor.run([[0.2], [0.3]])
    finally:
        reporter.close()

    assert len(released) == 2
    np.testing.assert_array_equal(result.P, [[0.2], [0.3]])
    np.testing.assert_array_equal(result.obs["flow"], [10.0, 20.0])
    for context in contexts:
        assert ("error" in context) is modelFails
        assert len(context["warnings"]) == 1
        notice = context["warnings"][0]
        assert notice.severity == "warning"
        assert notice.stage == "reporter"
        assert notice.code == "REPORTER_SUBMIT_FAILED"
        assert reporterState in notice.message
    assert len(caplog.records) == 2
    assert all(record.levelno == logging.WARNING for record in caplog.records)
    assert "batch=1 run=1" in caplog.records[0].message
    assert "batch=1 run=2" in caplog.records[1].message
    if modelFails:
        np.testing.assert_array_equal(result.objs, [[-np.inf], [-np.inf]])
        np.testing.assert_array_equal(result.cons, [[np.inf], [np.inf]])
        assert np.isnan(result.diags).all()
        assert np.isnan(result.series["flow"]).all()
        assert all(context["error"].code == "TIMEOUT" for context in contexts)
    else:
        np.testing.assert_array_equal(result.objs, [[0.8], [0.8]])
        np.testing.assert_array_equal(result.cons, [[0.0], [0.0]])
        np.testing.assert_array_equal(result.diags, [[2.0], [2.0]])
        np.testing.assert_array_equal(result.series["flow"], [[10.0, 20.0], [10.0, 20.0]])


def test_executor_run_returns_structured_batch_result():
    executor = Executor.__new__(Executor)
    executor.initializeBatchCounter(0)
    executor.nInput = 2
    executor.cfg = _ns(
        basic=_ns(parallel=1),
        parameters=_ns(physical=[_ns(name="p1"), _ns(name="p2")]),
        objectives=_ns(items=[_ns(id="obj_a", on_error=np.inf), _ns(id="obj_b")]),
        constraints=_ns(items=[_ns(id="con_a")]),
        diagnostics=_ns(items=[_ns(id="diag_a")]),
        series_index={"flow": _ns(size=2, sim=_ns(spec=None))},
        series=[object()],
    )
    executor.services = _ns(
        evaluator=_ns(nOutput=2, nConstraints=1, _post=_copyPostValues),
        obsStore=_ns(get=lambda sid: np.array([10.0, 20.0]) if sid == "flow" else None),
    )
    executor.reporter = None
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
    assert set(result.obs.keys()) == {"flow"}
    assert np.allclose(result.obs["flow"], np.array([10.0, 20.0]))


def test_executor_run_pads_series_length_mismatch_with_nan_and_warning():
    executor = Executor.__new__(Executor)
    executor.initializeBatchCounter(0)
    executor.nInput = 1
    executor.cfg = _ns(
        basic=_ns(parallel=1),
        parameters=_ns(physical=[]),
        objectives=_ns(items=[_ns(id="obj_a", on_error=np.inf)]),
        constraints=_ns(items=[]),
        diagnostics=_ns(items=[]),
        series_index={"flow": _ns(size=4, sim=_ns(spec=None))},
        series=[object()],
    )
    executor.services = _ns(
        evaluator=_ns(nOutput=1, nConstraints=0, _post=_copyPostValues),
        obsStore=_ns(get=lambda sid: None),
    )
    executor.reporter = None
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
    executor.initializeBatchCounter(0)
    executor.nInput = 1
    executor.cfg = _ns(
        basic=_ns(parallel=1),
        parameters=_ns(physical=[]),
        objectives=_ns(items=[_ns(id="obj_a", on_error=np.inf)]),
        constraints=_ns(items=[]),
        diagnostics=_ns(items=[]),
        series_index={"flow": _ns(size=3, sim=_ns(spec=None))},
        series=[object()],
    )
    executor.services = _ns(
        evaluator=_ns(nOutput=1, nConstraints=0, _post=_copyPostValues),
        obsStore=_ns(get=lambda sid: None),
    )
    executor.reporter = None
    executor.optSign = [1]

    records = [
        {"i": 0, "obj_a": 1.0, "flow.sim": np.array([1.0, 2.0, 3.0]), "warnings": []},
        {"i": 1, "obj_a": np.inf, "warnings": [], "error": RunError(stage="subprocess", code="TIMEOUT", target="simulation", message="failed")},
    ]

    executor._run_one = lambda X, i, batch_id: records[i]

    result = Executor.run(executor, np.array([[1.0], [2.0]]))

    assert np.allclose(result.series["flow"][0], np.array([1.0, 2.0, 3.0]))
    assert np.isnan(result.series["flow"][1]).all()


def test_executor_run_rejects_wrong_input_width_before_running():
    executor = Executor.__new__(Executor)
    executor.initializeBatchCounter(0)
    executor.nInput = 2

    with pytest.raises(ValueError, match="Expected 2 input parameters, got 3"):
        Executor.run(executor, np.array([1.0, 2.0, 3.0]))


def test_executor_run_rejects_non_vector_or_matrix_input():
    executor = Executor.__new__(Executor)
    executor.initializeBatchCounter(0)
    executor.nInput = 2

    with pytest.raises(ValueError, match="Expected X to be a 1D or 2D array"):
        Executor.run(executor, np.zeros((1, 2, 1)))
