import csv
from copy import deepcopy
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from hydropilot import SimModel
from hydropilot.config.loader import load_config, prepare_config
from hydropilot.config.schema.parameters import DesignParameterSpec
from hydropilot.models.swat.builder import buildSwatParams
from hydropilot.models.swat.library import SWAT_PARAM_LIBRARY, get_swat_library, lookupParam
from hydropilot.models.swat.validate import validate_swat_config
from hydropilot.params import ParamSpace
from hydropilot.validation.general import validate_general_config


def testSwatScopeSelectsLocationsAndMatchesPhysicalByIdentity(tmp_path):
    params = buildSwatParams({
        "design": [
            {"name": "ESCO", "scope": "bsn", "bounds": [0.1, 0.9]},
            {"name": "ESCO", "scope": "hru", "bounds": [0.2, 0.8]},
        ],
        # Deliberately reverse these: default mapping follows design identities.
        "physical": [
            {"name": "ESCO", "scope": "hru", "mode": "a"},
            {"name": "ESCO", "scope": "bsn", "mode": "v"},
        ],
    }, {}, SWAT_PARAM_LIBRARY, tmp_path)
    assert [item["name"] for item in params["design"]] == ["ESCO", "ESCO"]
    assert [item["scope"] for item in params["physical"]] == ["bsn", "hru"]
    assert [item["file"]["line"] for item in params["physical"]] == [13, 10]
    assert [item["bounds"] for item in params["physical"]] == [[0.1, 0.9], [0, 1]]
    assert [item["mode"] for item in params["physical"]] == ["v", "a"]


def testSwatScopeAutomaticallyBuildsPhysicalWithoutSuffixes(tmp_path):
    params = buildSwatParams({"design": [
        {"name": "ESCO", "scope": "bsn"}, {"name": "ESCO", "scope": "hru"},
    ]}, {}, SWAT_PARAM_LIBRARY, tmp_path)
    assert [(item["name"], item["scope"]) for item in params["physical"]] == [
        ("ESCO", "bsn"), ("ESCO", "hru"),
    ]
    assert all(item["bounds"] == [0, 1] for item in params["design"])


@pytest.mark.parametrize("name,scope", [
    ("DDRAIN", "mgt"), ("TDRAIN", "mgt"), ("GDRAIN", "mgt"),
    ("EPCO", "hru"), ("ESCO", "hru"), ("R2ADJ", "hru"), ("SURLAG", "hru"),
])
def testSwatDefaultScopeSelectsLocalDefinitionWithoutMutatingConfig(tmp_path, name, scope):
    raw = {"design": [{"name": name}], "physical": [{"name": name, "mode": "r"}]}
    original = deepcopy(raw)
    params = buildSwatParams(raw, {}, SWAT_PARAM_LIBRARY, tmp_path)
    assert raw == original
    assert params["design"][0]["scope"] == scope
    assert params["physical"][0]["scope"] == scope
    assert params["physical"][0]["file"]["name"].endswith(f".{scope}")
    assert lookupParam(name) == SWAT_PARAM_LIBRARY[f"{name}.{scope}"]


def testSwatDefaultLocalAndExplicitBasinMatchSeparately(tmp_path):
    params = buildSwatParams({
        "design": [{"name": "ESCO", "bounds": [0.2, 0.8]},
                   {"name": "ESCO", "scope": "bsn", "bounds": [0.1, 0.9]}],
        "physical": [{"name": "ESCO", "scope": "bsn", "mode": "v"},
                     {"name": "ESCO", "mode": "a"}],
    }, {}, SWAT_PARAM_LIBRARY, tmp_path)
    assert [item["scope"] for item in params["design"]] == ["hru", "bsn"]
    assert [item["scope"] for item in params["physical"]] == ["hru", "bsn"]
    assert [item["file"]["line"] for item in params["physical"]] == [10, 13]
    assert [item["mode"] for item in params["physical"]] == ["a", "v"]
    assert [item["bounds"] for item in params["physical"]] == [[0, 1], [0.1, 0.9]]


@pytest.mark.parametrize("designScope,physicalScope", [(None, "bsn"), ("bsn", None)])
def testSwatScopeMismatchCannotSilentlyDiscardExplicitPhysicalSettings(tmp_path, designScope, physicalScope):
    with pytest.raises(ValueError, match="no matching design parameter"):
        buildSwatParams({
            "design": [{"name": "ESCO", "scope": designScope, "bounds": [0, 1]}],
            "physical": [{"name": "ESCO", "scope": physicalScope, "mode": "r"}],
        }, {}, SWAT_PARAM_LIBRARY, tmp_path)


@pytest.mark.parametrize("secondScope", [None, "hru"])
def testSwatRejectsDuplicateDesignIdentityAfterResolvingDefault(tmp_path, secondScope):
    (tmp_path / "file.cio").touch()
    (tmp_path / "fig.fig").touch()
    diagnostics = validate_swat_config({
        "basic": {"projectPath": str(tmp_path)},
        "parameters": {"design": [{"name": "ESCO"}, {"name": "ESCO", "scope": secondScope}]},
        "series": [],
    }, tmp_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].level == "error"
    assert diagnostics[0].message == "duplicate design parameter identity: ESCO.hru"


def testSwatLibraryGeneratedDefinitionsSeparateNamesAndScopes():
    result = get_swat_library(["ESCO.bsn", "ESCO.hru", "CN2"], {})
    design = result["design_params"]["design_parameters"]
    physical = result["library"]["parameter_library"]
    for items in [design, physical]:
        assert [(item["name"], item.get("scope")) for item in items] == [
            ("ESCO", "bsn"), ("ESCO", "hru"), ("CN2", None),
        ]


def testSwatLibraryGeneratesDefaultLocalDefinitions():
    result = get_swat_library(["ESCO", "DDRAIN"], {})
    for items in [result["design_params"]["design_parameters"], result["library"]["parameter_library"]]:
        assert [(item["name"], item["scope"]) for item in items] == [("ESCO", "hru"), ("DDRAIN", "mgt")]


def testSwatTransformerPreservesRepeatedPhysicalScopes(tmp_path):
    params = buildSwatParams({
        "design": [{"name": "factor", "bounds": [0, 1]}],
        "physical": [{"name": "ESCO", "scope": scope, "mode": "v"}
                     for scope in ["bsn", "hru", "hru"]],
        "transformer": "expand",
    }, {}, SWAT_PARAM_LIBRARY, tmp_path)
    assert [item["scope"] for item in params["physical"]] == ["bsn", "hru", "hru"]
    assert len(params["design"]) == 1 and params["transformer"] == "expand"


@pytest.mark.parametrize("designScope,physicalScope", [(None, "mgt"), ("mgt", None)])
def testUnambiguousScopeMayBeOmittedOnEitherSide(tmp_path, designScope, physicalScope):
    params = buildSwatParams({
        "design": [{"name": "CN2", "scope": designScope, "bounds": [-0.2, 0.2]}],
        "physical": [{"name": "CN2", "scope": physicalScope, "mode": "r"}],
    }, {}, SWAT_PARAM_LIBRARY, tmp_path)
    assert params["physical"][0]["mode"] == "r"
    assert params["physical"][0]["bounds"] == [35, 98]
    assert params["physical"][0]["scope"] == "mgt"


@pytest.mark.parametrize("item,expected", [
    ({"name": "ESCO", "scope": "mgt"}, "invalid scope"),
    ({"name": "CN2", "scope": "bsn"}, "invalid scope"),
    ({"name": "ESCO.bsn"}, "must separate name and scope"),
    ({"name": "ESCO", "scope": " "}, "scope must be"),
    ({"name": "ESCO", "scope": 1}, "scope must be"),
])
@pytest.mark.parametrize("side", ["design", "physical"])
def testSwatScopeErrorsAreDiagnosedBeforeExpansion(tmp_path, item, expected, side):
    project = tmp_path / "project"
    project.mkdir()
    (project / "file.cio").touch()
    (project / "fig.fig").touch()
    params = {"design": [{"name": "x", "bounds": [0, 1]}], "physical": []}
    params[side] = [dict(item, bounds=[0, 1])]
    raw = {"basic": {"projectPath": str(project)}, "parameters": params, "series": []}
    diagnostics = validate_swat_config(raw, tmp_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].path.startswith(f"parameters.{side}")
    assert expected in diagnostics[0].message
    with pytest.raises(ValueError, match=expected):
        buildSwatParams(params, {}, SWAT_PARAM_LIBRARY, tmp_path)


@pytest.mark.parametrize("scopes,message", [
    ([None, "hru"], "scope is required"),
    (["bsn", "bsn"], "duplicate design parameter identity"),
])
def testGeneralAndParamSpaceRejectAmbiguousDesignIdentities(tmp_path, scopes, message):
    design = [{"name": "ESCO", "scope": scope, "bounds": [0, 1]} for scope in scopes]
    raw = {"version": "general", "basic": {"projectPath": ".", "workPath": "work", "command": "model"},
           "parameters": {"design": design, "physical": [
               {"name": "ESCO", "scope": scope, "writerType": "fixed_width",
                "file": {"name": "input", "line": 1, "start": 1, "width": 16, "precision": 3}}
               for scope in scopes]}, "series": []}
    assert any(message in item.message for item in validate_general_config(raw, tmp_path))
    with pytest.raises(ValueError, match=f"(?i){message}"):
        ParamSpace([DesignParameterSpec(**item) for item in design])


@pytest.fixture(params=[None, "hru"])
def scopedConfig(tmp_path, request):
    project = tmp_path / "project"
    project.mkdir()
    for name, count in [("basins.bsn", 20), ("000010001.hru", 15)]:
        (project / name).write_text("".join(f"{0.5:16.3f} | input\n" for _ in range(count)))
    (project / "runner.py").write_text(
        "from pathlib import Path\n"
        "bsn = float(Path('basins.bsn').read_text().splitlines()[12][:16])\n"
        "hru = float(Path('000010001.hru').read_text().splitlines()[9][:16])\n"
        "Path('output.txt').write_text(f'{bsn}\\n{hru}\\n')\n"
    )
    (tmp_path / "obs.txt").write_text("0\n1\n")
    parameters = buildSwatParams({"design": [
        {"name": "ESCO", "scope": "bsn", "bounds": [0, 1]},
        {"name": "ESCO", "scope": request.param, "bounds": [0, 1]},
    ]}, {}, SWAT_PARAM_LIBRARY, tmp_path)
    raw = {"version": "general",
           "basic": {"projectPath": str(project), "workPath": str(tmp_path / "work"),
                     "command": [sys.executable, "runner.py"]},
           "parameters": parameters,
           "series": [{"id": "flow",
                       "sim": {"readerType": "text", "file": "output.txt", "rowRanges": [[1, 2]], "colNum": 1},
                       "obs": {"readerType": "text", "file": "obs.txt", "rowRanges": [[1, 2]], "colNum": 1}}],
           "functions": [{"name": "RMSE", "kind": "builtin"}],
           "derived": [{"id": "rmse", "call": {"func": "RMSE", "args": ["flow.sim", "flow.obs"]}}],
           "objectives": [{"id": "rmse", "ref": "rmse", "sense": "min"}]}
    path = tmp_path / "scoped.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return path


def testScopedParametersWriteSeparatelyAndArchiveUniqueColumns(scopedConfig):
    with SimModel(str(scopedConfig)) as model:
        assert model.xLabels == ["ESCO.bsn", "ESCO.hru"]
        X = np.array([[0.2, 0.8], [0.7, 0.3]])
        result = model.run(X)
        np.testing.assert_array_equal(result.P, X)
        np.testing.assert_allclose(result.series["flow"], X)
        np.testing.assert_allclose(result.objs[:, 0], [0.2, 0.7])
        model.session.reporter.flush()
        archive = Path(model.archivePath)
        with sqlite3.connect(archive / "results.db") as connection:
            assert connection.execute('SELECT DISTINCT status FROM summary').fetchall() == [("ok",)]
            rows = connection.execute(
                'SELECT "X_ESCO_bsn", "X_ESCO_hru", "P_ESCO_bsn", "P_ESCO_hru" '
                'FROM summary ORDER BY run_id'
            ).fetchall()
        np.testing.assert_allclose(rows, [[0.2, 0.8, 0.2, 0.8], [0.7, 0.3, 0.7, 0.3]])
        with (archive / "summary.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        assert rows[0]["X_ESCO_bsn"] != rows[0]["X_ESCO_hru"]
        assert rows[1]["P_ESCO_bsn"] != rows[1]["P_ESCO_hru"]
    resolved = scopedConfig.with_name("scoped_general.yaml")
    loaded = load_config(resolved)
    assert [(item.name, item.scope) for item in loaded.parameters.design] == [("ESCO", "bsn"), ("ESCO", "hru")]
    assert prepare_config(resolved).expanded_raw["parameters"]["physical"][0]["scope"] == "bsn"


def testUQPyLAcceptsTwoScopedDesignVariables(scopedConfig):
    pytest.importorskip("UQPyL")
    from hydropilot.integrations import UQPyLAdapter
    with UQPyLAdapter(str(scopedConfig)) as problem:
        assert problem.xLabels == ["ESCO.bsn", "ESCO.hru"]
        result = problem.evaluate(np.array([[0.25, 0.75]]))
        np.testing.assert_allclose(result.objs, [[0.25]])
