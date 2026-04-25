from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_top_level_exports_sim_model():
    from hydro_pilot import BatchRunResult, SimModel
    from hydro_pilot.api import BatchRunResult as ApiBatchRunResult
    from hydro_pilot.api import SimModel as ApiSimModel

    assert SimModel is ApiSimModel
    assert BatchRunResult is ApiBatchRunResult


def test_migrated_layers_export_new_paths():
    from hydro_pilot.evaluation import Evaluator, FunctionManager
    from hydro_pilot.params import ParamApplier, ParamSpace, ParamWritePlan
    from hydro_pilot.series import ObsStore, SeriesExtractor, SeriesPlan, SeriesPlanItem
    from hydro_pilot.runtime import (
        ExecutionServices,
        Executor,
        Session,
        Workspace,
        create_context,
        ensure_warnings,
    )

    assert Evaluator.__name__ == "Evaluator"
    assert FunctionManager.__name__ == "FunctionManager"
    assert ParamSpace.__name__ == "ParamSpace"
    assert ParamWritePlan.__name__ == "ParamWritePlan"
    assert ParamApplier.__name__ == "ParamApplier"
    assert SeriesPlan.__name__ == "SeriesPlan"
    assert SeriesPlanItem.__name__ == "SeriesPlanItem"
    assert ObsStore.__name__ == "ObsStore"
    assert SeriesExtractor.__name__ == "SeriesExtractor"
    assert ExecutionServices.__name__ == "ExecutionServices"
    assert Executor.__name__ == "Executor"
    assert Session.__name__ == "Session"
    assert Workspace.__name__ == "Workspace"
    assert callable(create_context)
    assert callable(ensure_warnings)


def test_integrations_exports_uqpyl_adapter_when_optional_dep_available():
    pytest.importorskip("UQPyL")

    from hydro_pilot.integrations import UQPyLAdapter
    from hydro_pilot.integrations.uqpyl import UQPyLAdapter as DirectUQPyLAdapter

    assert UQPyLAdapter is DirectUQPyLAdapter
