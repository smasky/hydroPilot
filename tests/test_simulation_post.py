from concurrent.futures import ThreadPoolExecutor
import csv
import json
from pathlib import Path
import sqlite3
import sys
from threading import Event

import numpy as np
import pytest
import yaml

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydropilot import SimModel
from hydropilot.reporting import reporter as reporting
from hydropilot.reporting.serializers import decodeArray
from hydropilot.runtime.errors import RunError


@pytest.fixture
def configPath(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "params.txt").write_text("     0.20000000000000000\n")
    (project / "runner.py").write_text(
        "from pathlib import Path\nimport sys\n"
        "x = float(Path('params.txt').read_text())\n"
        "if x > 0.95: sys.exit(3)\n"
        "values = [x + 0.12345678901234567, x + 1.2345678901234567, x + 2.345678901234567]\n"
        "Path('output.txt').write_text('\\n'.join(map(repr, values)))\n"
    )
    (tmp_path / "obs.txt").write_text("1\n2\n3\n")
    (tmp_path / "functions.py").write_text(
        "import numpy as np\n"
        "calls = {}\nfailures = set()\n"
        "def counted(name):\n"
        "    calls[name] = calls.get(name, 0) + 1\n"
        "    if name in failures: raise ValueError('failed ' + name)\n"
        "def shared(flow):\n    counted('shared')\n    return np.mean(flow)\n"
        "def goal(value):\n    counted('goal')\n    return value\n"
        "def balance(value):\n    counted('balance')\n    return value - 2\n"
        "def diagnostic(flow):\n    counted('diagnostic')\n    return np.sum(flow)\n"
        "def unused(flow):\n    counted('unused')\n    return flow[0]\n"
    )
    raw = {
        "version": "general",
        "basic": {"projectPath": str(project), "workPath": str(tmp_path / "work"),
                  "command": [sys.executable, "runner.py"], "parallel": 1, "keepCopies": False},
        "parameters": {
            "design": [{"name": "x", "bounds": [0, 1]}],
            "physical": [{"name": "p", "bounds": [0, 1], "writerType": "fixed_width",
                          "file": {"name": "params.txt", "line": 1, "start": 1, "width": 24, "precision": 17}}],
        },
        "series": [{"id": "flow",
                    "sim": {"file": "output.txt", "readerType": "text", "rowRanges": [[1, 3]], "colNum": 1},
                    "obs": {"file": "obs.txt", "readerType": "text", "rowRanges": [[1, 3]], "colNum": 1}}],
        "functions": [{"name": name, "kind": "external", "file": "functions.py"}
                      for name in ["shared", "goal", "balance", "diagnostic", "unused"]],
        "derived": [
            {"id": "shared_value", "call": {"func": "shared", "args": ["flow.sim"]}},
            {"id": "goal_value", "call": {"func": "goal", "args": ["shared_value"]}},
            {"id": "balance_value", "call": {"func": "balance", "args": ["shared_value"]}},
            {"id": "diag_value", "call": {"func": "diagnostic", "args": ["flow.sim"]}},
            {"id": "unused_value", "call": {"func": "unused", "args": ["flow.sim"]}},
        ],
        "objectives": [{"id": "objective", "ref": "goal_value", "sense": "min"}],
        "constraints": [{"id": "constraint", "ref": "balance_value"}],
        "diagnostics": [{"id": "diagnostic", "ref": "diag_value"}],
        "reporter": {"series": ["flow"], "flushInterval": 50},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return path


def counters(model):
    return model.session.executor.services.functionManager.get("shared").__globals__


def archiveRows(model):
    model.session.reporter.flush()
    with sqlite3.connect(Path(model.archivePath) / "results.db") as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute("SELECT * FROM summary ORDER BY batch_id,run_id")]


@pytest.mark.parametrize("keepCopies", [False, True])
@pytest.mark.parametrize("reset", [False, True])
def test_copy_lifecycle_restores_inputs_and_preserves_outputs(configPath, keepCopies, reset):
    raw = yaml.safe_load(configPath.read_text())
    raw["basic"].update(keepCopies=keepCopies, reset=reset, parallel=2)
    configPath.write_text(yaml.safe_dump(raw, sort_keys=False))
    source = Path(raw["basic"]["projectPath"]) / "params.txt"
    baseline = source.read_bytes()

    with SimModel(str(configPath)) as model:
        instances = [Path(model.runPath) / f"instance_{index}" for index in range(2)]
        backupPaths = [snapshot.backupDir for snapshot in model.session._inputSnapshots]
        for values in ([0.4, 0.6], [0.3, 0.7]):
            result = model.run(np.asarray(values).reshape(-1, 1))
            np.testing.assert_allclose(result.series["flow"][:, 0], np.asarray(values) + 0.12345678901234567)
            if reset:
                assert all((instance / "params.txt").read_bytes() == baseline for instance in instances)
            else:
                assert sorted(float((instance / "params.txt").read_text()) for instance in instances) == sorted(values)
        outputs = [(instance / "output.txt").read_bytes() for instance in instances]

    model.close()  # Closing twice must not repeat restoration or remove retained copies.
    if keepCopies:
        assert all((instance / "params.txt").read_bytes() == baseline for instance in instances)
        assert [(instance / "output.txt").read_bytes() for instance in instances] == outputs
        assert all((instance / "runner.stdout.log").exists() for instance in instances)
    else:
        assert all(not instance.exists() for instance in instances)
    assert source.read_bytes() == baseline
    assert all(not path.exists() for path in backupPaths)
    assert (Path(model.archivePath) / "results.db").exists()


@pytest.mark.parametrize("reset", [False, True])
def test_retained_named_copies_restore_after_failed_simulation(configPath, reset):
    raw = yaml.safe_load(configPath.read_text())
    raw["basic"].update(keepCopies=True, reset=reset, workDirName="retained")
    configPath.write_text(yaml.safe_dump(raw, sort_keys=False))
    baseline = (Path(raw["basic"]["projectPath"]) / "params.txt").read_bytes()
    with SimModel(str(configPath)) as model:
        instance = Path(model.runPath) / "instance_0"
        model.run([0.4])
        output = (instance / "output.txt").read_bytes()
        failed = model.run([0.99])
        assert np.isposinf(failed.objs).all()
        if not reset:
            assert float((instance / "params.txt").read_text()) == 0.99
    assert (instance / "params.txt").read_bytes() == baseline
    assert (instance / "output.txt").read_bytes() == output
    assert (instance / "runner.stderr.log").exists()
    with SimModel(str(configPath)) as reopened:
        assert Path(reopened.runPath) == Path(model.runPath)
        assert (instance / "params.txt").read_bytes() == baseline
        reopened.run([0.5])
        assert archiveRows(reopened)[-1]["batch_id"] == 3
    assert (instance / "params.txt").read_bytes() == baseline


@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_keep_copies_requires_boolean(configPath, value):
    from hydropilot.validation.entry import validate_config

    raw = yaml.safe_load(configPath.read_text())
    raw["basic"]["keepCopies"] = value
    configPath.write_text(yaml.safe_dump(raw, sort_keys=False))
    diagnostics = validate_config(configPath)
    assert any(item.path == "basic.keepCopies" and item.level == "error" for item in diagnostics)


def test_simulation_archives_pending_then_post_updates_one_record(configPath):
    with SimModel(str(configPath)) as model:
        simulation = model._runSimulation([0.2])
        assert counters(model)["calls"] == {}
        row = archiveRows(model)[0]
        assert row["sim_status"] == "ok"
        assert row["obj_state"] == row["con_state"] == row["diag_state"] == "pending"
        assert row["objective"] is row["constraint"] is row["diagnostic"] is None

        expected = simulation.series["flow"].mean()
        objective = model._post(simulation, "objs")
        np.testing.assert_allclose(objective.objs, [[expected]])
        assert objective.cons is None and objective.diags is None
        assert counters(model)["calls"] == {"shared": 1, "goal": 1}
        constraint = model._post(simulation, "cons")
        np.testing.assert_allclose(constraint.cons, [[expected - 2]])
        assert counters(model)["calls"] == {"shared": 1, "goal": 1, "balance": 1}
        model._post(simulation, "objs")
        model._post(simulation, "cons")
        assert counters(model)["calls"]["shared"] == 1
        assert model.session.executor._batchNo == 1
        rows = archiveRows(model)
        assert len(rows) == 1
        assert rows[0]["obj_state"] == rows[0]["con_state"] == "done"
        assert rows[0]["diag_state"] == "pending"
        with (Path(model.archivePath) / "summary.csv").open() as stream:
            csvRows = list(csv.DictReader(stream))
        assert len(csvRows) == 1 and csvRows[0]["diagnostic"] == ""
        assert csvRows[0]["diag_state"] == "pending"


def test_contexts_are_independent_and_post_survives_workspace_removal(configPath):
    with SimModel(str(configPath)) as model:
        X = np.array([[0.2]])
        first = model._runSimulation(X)
        X[0, 0] = 0.8
        second = model._runSimulation(X)
        model.session.workspace.cleanup_instances()
        assert not list(Path(model.runPath).glob("instance_*"))
        np.testing.assert_allclose(model._post(first, "objs").objs, [[first.series["flow"].mean()]])
        np.testing.assert_allclose(model._post(second, "objs").objs, [[second.series["flow"].mean()]])
        np.testing.assert_array_equal(first.X, [[0.2]])
        assert not first.X.flags.writeable and not first.series["flow"].flags.writeable
        assert len(archiveRows(model)) == 2


def test_batch_identity_and_repeated_post_do_not_add_evaluations(configPath):
    with SimModel(str(configPath)) as model:
        simulation = model._runSimulation([[0.2], [0.3]])
        model._post(simulation)
        before = dict(counters(model)["calls"])
        model._post(simulation)
        assert counters(model)["calls"] == before
        rows = archiveRows(model)
        assert [(row["batch_id"], row["run_id"]) for row in rows] == [(1, 1), (1, 2)]
        assert all(row["diag_state"] == "done" for row in rows)
        model._runSimulation([0.2])
        assert len(archiveRows(model)) == 3


def test_full_post_after_individual_blocks_computes_remaining_derived(configPath):
    with SimModel(str(configPath)) as model:
        context = model._runSimulation([0.2])
        for target in ("objs", "cons", "diags"):
            model._post(context, target)
        assert "unused" not in counters(model)["calls"]
        model._post(context)
        model._post(context)
        assert counters(model)["calls"] == {"shared": 1, "goal": 1, "balance": 1, "diagnostic": 1, "unused": 1}
        assert len(archiveRows(model)) == 1


def test_parameter_transform_runs_once_and_post_uses_written_parameters(configPath):
    functions = configPath.with_name("functions.py")
    with functions.open("a") as stream:
        stream.write("def transform(X):\n    counted('transform')\n    return np.asarray(X) * 2\n")
    raw = yaml.safe_load(configPath.read_text())
    raw["functions"].append({"name": "transform", "kind": "external", "file": "functions.py"})
    raw["parameters"]["transformer"] = "transform"
    configPath.write_text(yaml.safe_dump(raw))
    with SimModel(str(configPath)) as model:
        context = model._runSimulation([0.2])
        np.testing.assert_array_equal(context.P, [[0.4]])
        model._post(context)
        assert counters(model)["calls"]["transform"] == 1


def test_apply_writes_without_simulating_and_simulate_uses_prepared_inputs(configPath, monkeypatch):
    with SimModel(str(configPath)) as model:
        services = model.session.executor.services
        transformCalls = []

        def transform(X):
            transformCalls.append(np.array(X, copy=True))
            return np.asarray(X) * 2

        monkeypatch.setattr(services.paramApplier.transformer, "transform", transform)
        workPath = model.session.workspace.acquire_instance()
        try:
            design = np.array([0.2])
            context = {"X": design.copy(), "warnings": []}
            prepared = model._apply(workPath, design, context)
            np.testing.assert_array_equal(prepared["P"], [0.4])
            assert float((Path(workPath) / "params.txt").read_text()) == 0.4
            assert not (Path(workPath) / "output.txt").exists()
            assert prepared["param.writeRecords"][0]["new_value"] == 0.4
            assert model.session.executor._batchNo == 0
            assert archiveRows(model) == []

            def unexpectedApply(*args):
                raise AssertionError("Simulation must use the already written input")

            monkeypatch.setattr(services.paramApplier, "apply", unexpectedApply)
            simulated = model._simulate(workPath, prepared)
            expected = [0.4 + 0.12345678901234567, 0.4 + 1.2345678901234567,
                        0.4 + 2.345678901234567]
            np.testing.assert_allclose(simulated["flow.sim"], expected, rtol=0, atol=1e-15)
            np.testing.assert_array_equal(simulated["P"], [0.4])
            assert len(transformCalls) == 1
            assert counters(model)["calls"] == {}
            assert model.session.executor._batchNo == 0
            assert archiveRows(model) == []
        finally:
            model.session.workspace.release_instance(workPath)


def test_batch_apply_and_simulate_share_instances_when_samples_exceed_parallelism(configPath, monkeypatch):
    raw = yaml.safe_load(configPath.read_text())
    raw["basic"]["parallel"] = 2
    configPath.write_text(yaml.safe_dump(raw))
    with SimModel(str(configPath)) as model:
        executor = model.session.executor
        originalApply, originalSimulate = executor._apply, executor._simulate
        applied = {}

        def apply(workPath, X, context):
            prepared = originalApply(workPath, X, context)
            applied[context["i"]] = (workPath, float(prepared["P"][0]))
            return prepared

        def simulate(workPath, context):
            expectedPath, expectedValue = applied[context["i"]]
            assert workPath == expectedPath
            assert float((Path(workPath) / "params.txt").read_text()) == expectedValue
            return originalSimulate(workPath, context)

        monkeypatch.setattr(executor, "_apply", apply)
        monkeypatch.setattr(executor, "_simulate", simulate)
        X = np.array([[0.1], [0.2], [0.3], [0.4], [0.5]])
        result = model.run(X)
        assert len(applied) == len(X)
        np.testing.assert_array_equal(result.P, X)
        np.testing.assert_allclose(result.series["flow"][:, 0], X[:, 0] + 0.12345678901234567)
        rows = archiveRows(model)
        assert [(row["batch_id"], row["run_id"]) for row in rows] == [(1, i + 1) for i in range(len(X))]
        assert all(row["sim_status"] == "ok" for row in rows)


def test_apply_failure_skips_model_and_releases_instance_for_next_sample(configPath, monkeypatch):
    with SimModel(str(configPath)) as model:
        executor = model.session.executor
        originalApply = executor.services.paramApplier.apply
        originalRun = executor.services.runner.run
        modelCalls = []

        def apply(workPath, X, context):
            if X[0] == 0.2:
                raise RunError("params", "TEST_WRITE_FAILED", "p", "cannot write parameters")
            return originalApply(workPath, X, context)

        def run(*args):
            modelCalls.append(args[0])
            return originalRun(*args)

        monkeypatch.setattr(executor.services.paramApplier, "apply", apply)
        monkeypatch.setattr(executor.services.runner, "run", run)
        result = model.run([[0.2], [0.3]])
        assert len(modelCalls) == 1
        assert np.isinf(result.objs[0, 0])
        assert np.isnan(result.series["flow"][0]).all()
        np.testing.assert_allclose(result.objs[1, 0], result.series["flow"][1].mean())
        rows = archiveRows(model)
        assert [row["sim_status"] for row in rows] == ["error", "ok"]
        assert executor.workspace.runQueue.qsize() == 1


def test_called_series_stays_in_simulation_phase_and_keeps_all_data(configPath):
    functions = configPath.with_name("functions.py")
    with functions.open("a") as stream:
        stream.write("def scaled(flow):\n    counted('scaled')\n    return np.asarray(flow) * 2\n")
    raw = yaml.safe_load(configPath.read_text())
    raw["functions"].append({"name": "scaled", "kind": "external", "file": "functions.py"})
    raw["series"].append({"id": "doubled", "sim": {"call": {"func": "scaled", "args": ["flow.sim"]}}})
    raw["derived"][0]["call"]["args"] = ["doubled.sim"]
    configPath.write_text(yaml.safe_dump(raw))
    with SimModel(str(configPath)) as model:
        context = model._runSimulation([0.2])
        assert counters(model)["calls"] == {"scaled": 1}
        np.testing.assert_array_equal(context.series["doubled"], context.series["flow"] * 2)
        np.testing.assert_allclose(model._post(context, "objs").objs, [[context.series["doubled"].mean()]])


def test_failed_called_series_without_observations_returns_fallback(configPath):
    pytest.importorskip("UQPyL")
    from hydropilot.integrations import UQPyLAdapter
    functions = configPath.with_name("functions.py")
    with functions.open("a") as stream:
        stream.write("def generated(X):\n    return np.asarray(X)\n")
    raw = yaml.safe_load(configPath.read_text())
    raw["functions"].append({"name": "generated", "kind": "external", "file": "functions.py"})
    raw["series"] = [{"id": "flow", "sim": {"call": {"func": "generated", "args": ["X"]}}}]
    configPath.write_text(yaml.safe_dump(raw))
    with UQPyLAdapter(str(configPath)) as problem:
        result = problem.evaluate([0.99])
        assert result.sims.shape == (1, 0, 1)
        assert np.isinf(result.objs).all()
        assert archiveRows(problem.model)[0]["sim_status"] == "error"


def test_same_context_concurrent_post_reuses_shared_derived(configPath):
    with SimModel(str(configPath)) as model:
        context = model._runSimulation([0.2])
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(model._post, context, "objs")
            second = pool.submit(model._post, context, "cons")
            assert np.isfinite(first.result().objs).all()
            assert np.isfinite(second.result().cons).all()
        assert counters(model)["calls"] == {"shared": 1, "goal": 1, "balance": 1}
        assert len(archiveRows(model)) == 1


def test_post_failure_keeps_successful_simulation_and_archived_series(configPath):
    with SimModel(str(configPath)) as model:
        counters(model)["failures"].add("goal")
        context = model._runSimulation([0.2])
        original = context.series["flow"].copy()
        assert np.isinf(model._post(context, "objs").objs).all()
        row = archiveRows(model)[0]
        assert row["sim_status"] == "ok" and row["obj_state"] == "error"
        assert row["con_state"] == "pending"
        np.testing.assert_array_equal(context.series["flow"], original)
        assert np.isfinite(model._post(context, "cons").cons).all()
        with sqlite3.connect(Path(model.archivePath) / "results.db") as connection:
            assert connection.execute("SELECT COUNT(*) FROM series").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM errors WHERE severity='fatal'").fetchone()[0] == 1
        model._post(context, "objs")
        assert counters(model)["calls"]["goal"] == 1


def test_diagnostic_failure_is_warning_and_simulation_failure_uses_on_error(configPath):
    with SimModel(str(configPath)) as model:
        counters(model)["failures"].add("diagnostic")
        context = model._runSimulation([0.2])
        result = model._post(context)
        assert np.isfinite(result.objs).all() and np.isnan(result.diags).all()
        row = archiveRows(model)[0]
        assert row["status"] == "warning" and row["obj_state"] == "done"
        failed = model._runSimulation([0.99])
        before = dict(counters(model)["calls"])
        result = model._post(failed)
        assert np.isinf(result.objs).all() and np.isinf(result.cons).all()
        assert np.isnan(result.diags).all() and np.isnan(failed.series["flow"]).all()
        assert counters(model)["calls"] == before
        assert archiveRows(model)[1]["sim_status"] == "error"


def test_full_run_keeps_existing_fatal_fallbacks_for_all_blocks(configPath):
    raw = yaml.safe_load(configPath.read_text())
    raw["objectives"][0].update(sense="max", on_error=-123.0)
    raw["constraints"][0]["on_error"] = 456.0
    raw["diagnostics"][0]["on_error"] = -789.0
    configPath.write_text(yaml.safe_dump(raw))
    with SimModel(str(configPath)) as model:
        counters(model)["failures"].add("goal")
        result = model.run([0.2])
        np.testing.assert_array_equal(result.objs, [[-123.0]])
        np.testing.assert_array_equal(result.cons, [[456.0]])
        np.testing.assert_array_equal(result.diags, [[-789.0]])
        assert np.isfinite(result.series["flow"]).all()
        row = archiveRows(model)[0]
        assert row["sim_status"] == "ok" and row["obj_state"] == row["con_state"] == "error"


def test_post_rejects_foreign_context_and_bad_target_before_computing(configPath):
    with SimModel(str(configPath)) as first, SimModel(str(configPath)) as second:
        context = first._runSimulation([0.2])
        with pytest.raises(ValueError, match="created by this SimModel"):
            second._post(context)
        with pytest.raises(ValueError, match="Unknown post-processing target"):
            first._post(context, "unknown")
        assert counters(first)["calls"] == counters(second)["calls"] == {}


def test_cached_diagnostic_failure_becomes_fatal_when_objective_needs_it(configPath):
    raw = yaml.safe_load(configPath.read_text())
    raw["diagnostics"][0]["ref"] = "shared_value"
    configPath.write_text(yaml.safe_dump(raw))
    with SimModel(str(configPath)) as model:
        counters(model)["failures"].add("shared")
        context = model._runSimulation([0.2])
        assert np.isnan(model._post(context, "diags").diags).all()
        assert np.isinf(model._post(context, "objs").objs).all()
        assert counters(model)["calls"] == {"shared": 1}
        archiveRows(model)
        with sqlite3.connect(Path(model.archivePath) / "results.db") as connection:
            severities = connection.execute("SELECT severity FROM errors WHERE target='shared_value' ORDER BY rowid").fetchall()
        assert severities == [("warning",), ("fatal",)]


def test_archive_preserves_array_precision_and_observations_once(configPath):
    with SimModel(str(configPath)) as model:
        context = model._runSimulation([[0.2], [0.3]])
        model._post(context)
        archiveRows(model)
        with sqlite3.connect(Path(model.archivePath) / "results.db") as connection:
            rows = connection.execute("SELECT dtype,shape,data FROM series ORDER BY run_id").fetchall()
            restored = np.vstack([decodeArray(data, dtype, shape) for dtype, shape, data in rows])
            assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM observation_refs").fetchone()[0] == 2
            obsRow = connection.execute("SELECT dtype,shape,data FROM observations").fetchone()
            assert connection.execute("SELECT COUNT(*) FROM derived").fetchone()[0] == 10
        np.testing.assert_array_equal(restored, context.series["flow"])
        assert restored.dtype == context.series["flow"].dtype == np.float64
        assert np.any(restored != restored.astype(np.float32).astype(np.float64))
        np.testing.assert_array_equal(decodeArray(obsRow[2], obsRow[0], obsRow[1]), context.obs["flow"])


def test_runtime_ids_continue_from_database_even_when_csv_is_stale(configPath):
    raw = yaml.safe_load(configPath.read_text())
    raw["basic"]["workDirName"] = "persistent"
    configPath.write_text(yaml.safe_dump(raw))
    with SimModel(str(configPath)) as model:
        model.run([0.2])
        archive = Path(model.archivePath)
    (archive / "summary.csv").write_text("stale\n")
    with SimModel(str(configPath)) as model:
        model._runSimulation([0.2])
        assert [(row["batch_id"], row["run_id"]) for row in archiveRows(model)] == [(1, 1), (2, 1)]


def test_csv_export_failure_keeps_committed_sqlite_and_can_retry(configPath, monkeypatch, caplog):
    original = reporting.exportStorage
    attempts = []
    def failFirst(connection, archive, fields, seriesIds):
        with sqlite3.connect(archive / "results.db") as reader:
            attempts.append(reader.execute("SELECT COUNT(*) FROM summary").fetchone()[0])
        if len(attempts) == 1:
            raise OSError("CSV temporarily unavailable")
        return original(connection, archive, fields, seriesIds)
    monkeypatch.setattr(reporting, "exportStorage", failFirst)
    with SimModel(str(configPath)) as model:
        context = model._runSimulation([0.2])
        model.session.reporter.flush()
        assert attempts == [1]
        assert not model.session.reporter._crashEvent.is_set()
        assert "REPORTER_EXPORT_FAILED" in caplog.text
        assert np.isfinite(model._post(context).objs).all()
        model.session.reporter.flush()
        with (Path(model.archivePath) / "summary.csv").open() as stream:
            assert list(csv.DictReader(stream))[0]["obj_state"] == "done"
        notices = [json.loads(line) for line in (Path(model.archivePath) / "error.jsonl").read_text().splitlines()]
        assert any(item["code"] == "REPORTER_EXPORT_FAILED" and item["severity"] == "warning" for item in notices)


def test_reporter_queue_owns_snapshot_of_arrays_and_errors(configPath, monkeypatch):
    ready, release = Event(), Event()
    original = reporting.writeRecord
    def gatedWrite(*args):
        ready.set()
        if not release.wait(10):
            raise RuntimeError("test gate timed out")
        return original(*args)
    monkeypatch.setattr(reporting, "writeRecord", gatedWrite)
    with SimModel(str(configPath)) as model:
        values = np.array([1.12345678901234, 2.0, 3.0])
        warning = RunError("series", "NOTICE", "flow.sim", "original", severity="warning")
        record = {"batch_id": 1, "i": 0, "X": np.array([0.2]), "P": np.array([0.2]),
                  "flow.sim": values, "warnings": [warning]}
        try:
            model.session.reporter.submit(record)
            assert ready.wait(10)
            values[:] = 99
            warning.message = "changed"
        finally:
            release.set()
        model.session.reporter.flush()
        with sqlite3.connect(Path(model.archivePath) / "results.db") as connection:
            dtype, shape, data = connection.execute("SELECT dtype,shape,data FROM series").fetchone()
            assert connection.execute("SELECT message FROM errors").fetchone()[0] == "original"
        np.testing.assert_array_equal(decodeArray(data, dtype, shape), [1.12345678901234, 2.0, 3.0])


@pytest.mark.parametrize("target", [None, "objs", "cons", "sims"])
def test_uqpyl_native_targets_really_separate_simulation_and_post(configPath, target):
    pytest.importorskip("UQPyL")
    from hydropilot.integrations import UQPyLAdapter
    with UQPyLAdapter(str(configPath)) as problem:
        result = problem.evaluate([0.2], target=target)
        calls = counters(problem.model)["calls"]
        expected = {None: {"shared", "goal", "balance", "diagnostic", "unused"},
                    "objs": {"shared", "goal"}, "cons": {"shared", "balance"}, "sims": set()}
        assert set(calls) == expected[target]
        assert all(count == 1 for count in calls.values())
        assert (result.objs is not None) == (target in (None, "objs"))
        assert (result.sims is not None) == (target in (None, "sims"))
        assert len(archiveRows(problem.model)) == 1


def test_uqpyl_split_calls_keep_context_results_and_one_archive_record(configPath):
    pytest.importorskip("UQPyL")
    from hydropilot.integrations import UQPyLAdapter
    with UQPyLAdapter(str(configPath)) as problem:
        first = problem.simulate([0.2])
        second = problem.simulate([0.3])
        assert counters(problem.model)["calls"] == {}
        np.testing.assert_allclose(problem.objFunc([0.2], first), [[first.sims.mean()]])
        np.testing.assert_allclose(problem.conFunc([0.2], first), [[first.sims.mean() - 2]])
        problem.objFunc([0.2], first)
        assert counters(problem.model)["calls"] == {"shared": 1, "goal": 1, "balance": 1}
        np.testing.assert_allclose(problem.objFunc([0.3], second), [[second.sims.mean()]])
        assert len(archiveRows(problem.model)) == 2
