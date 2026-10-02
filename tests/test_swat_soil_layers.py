from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from hydropilot.config.schema.parameters import ParametersSpec
from hydropilot.params import ParamApplier, ParamWritePlan
from hydropilot.models.swat.builder import buildSwatParams
from hydropilot.models.swat.library import SWAT_PARAM_LIBRARY


def makeLayerPlan(project, selectIndex=None):
    fileSpec = {"name": "*.sol", "line": 2, "start": 28, "width": 12, "precision": 2, "maxNum": 10}
    if selectIndex is not None:
        fileSpec["selectIndex"] = selectIndex
    parameters = ParametersSpec.from_raw({
        "design": [{"name": "SOL_AWC", "bounds": [0, 1]}],
        "physical": [{"name": "SOL_AWC", "mode": "v", "bounds": [0, 1], "writerType": "fixed_width", "file": fileSpec}],
    }, project)
    cfg = SimpleNamespace(basic=SimpleNamespace(projectPath=str(project)), parameters=parameters)
    return cfg, ParamWritePlan(cfg)


def writeLayers(path, values, newline=b"\n", tail=b""):
    line = b"Ave. AW Incl. Rock Frag  :".ljust(27) + b"".join(f"{value:12.2f}".encode() for value in values) + tail
    path.write_bytes(b"Soil header" + newline + line + newline)


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def testSelectedLayerSkipsShortHruAndRecordsCounts(tmp_path, newline):
    writeLayers(tmp_path / "one.sol", [0.1], newline)
    writeLayers(tmp_path / "three.sol", [0.1, 0.2, 0.3], newline)
    original = (tmp_path / "one.sol").read_bytes()
    cfg, plan = makeLayerPlan(tmp_path, 3)
    plan.initialize(str(tmp_path))
    assert len(plan.get_instance_tasks(str(tmp_path))) == 1
    context = {}
    ParamApplier(cfg, None, plan).apply(str(tmp_path), [0.8], context)
    assert (tmp_path / "one.sol").read_bytes() == original
    line = (tmp_path / "three.sol").read_bytes().splitlines()[1]
    assert [float(line[27 + i * 12:39 + i * 12]) for i in range(3)] == [0.1, 0.2, 0.8]
    assert context["param.registrationSummary"] == [{"index": 0, "param": "SOL_AWC", "matchedFiles": 1, "skippedFiles": 1}]
    assert len(context["param.writeRecords"]) == 1
    assert context["warnings"][0].code == "PARTIAL_TARGET_MATCH"
    assert context["warnings"][0].severity == "warning"
    plan.clear_instance_tasks()
    assert not plan.instanceRegistrationSummary


def testMissingSelectedLayerEverywhereFailsBeforeAnyWrite(tmp_path):
    writeLayers(tmp_path / "one.sol", [0.1])
    writeLayers(tmp_path / "two.sol", [0.1, 0.2])
    cfg, plan = makeLayerPlan(tmp_path, 3)
    with pytest.raises(ValueError, match="No writable entries found for parameter 'SOL_AWC' in any target file"):
        plan.initialize(str(tmp_path))
    assert not plan.instance_tasks and not plan.instanceRegistrationSummary


def testAllExistingLayersAreWrittenWithoutMissingLayerWarnings(tmp_path):
    writeLayers(tmp_path / "one.sol", [0.1], tail=b"    | layers")
    writeLayers(tmp_path / "three.sol", [0.1, 0.2, 0.3])
    cfg, plan = makeLayerPlan(tmp_path)
    plan.initialize(str(tmp_path))
    context = {}
    ParamApplier(cfg, None, plan).apply(str(tmp_path), [0.8], context)
    assert len(context["param.writeRecords"]) == 4
    assert not context.get("warnings")
    assert context["param.registrationSummary"][0]["matchedFiles"] == 2
    assert context["param.registrationSummary"][0]["skippedFiles"] == 0


@pytest.mark.parametrize("field", [b"bad".rjust(12), b"nan".rjust(12), b"inf".rjust(12), b"1\xff2".rjust(12), b" " * 12])
@pytest.mark.parametrize("selectIndex", [None, 3])
def testMalformedLayerIsNotTreatedAsMissing(tmp_path, field, selectIndex):
    writeLayers(tmp_path / "bad.sol", [0.1])
    path = tmp_path / "bad.sol"
    path.write_bytes(path.read_bytes().rstrip(b"\n") + field + f"{0.3:12.2f}".encode() + b"\n")
    cfg, plan = makeLayerPlan(tmp_path, selectIndex)
    with pytest.raises(ValueError, match="Invalid numeric fixed_width field.*bad.sol.*line=2;start=40"):
        plan.initialize(str(tmp_path))


def testTruncatedLayerIsNotTreatedAsMissing(tmp_path):
    writeLayers(tmp_path / "bad.sol", [0.1], tail=b"0.2")
    _, plan = makeLayerPlan(tmp_path, 3)
    with pytest.raises(ValueError, match="Incomplete fixed_width field"):
        plan.initialize(str(tmp_path))


def testMissingParameterRowIsNotTreatedAsMissingLayer(tmp_path):
    (tmp_path / "bad.sol").write_bytes(b"Soil header\n")
    _, plan = makeLayerPlan(tmp_path, 3)
    with pytest.raises(ValueError, match="Missing fixed_width line 2"):
        plan.initialize(str(tmp_path))


def testSwatTemplatePreservesSelectedSoilLayer(tmp_path):
    location = dict(SWAT_PARAM_LIBRARY["SOL_AWC"]["file"], selectIndex=3)
    expanded = buildSwatParams({
        "design": [{"name": "SOL_AWC", "bounds": [0, 1]}],
        "physical": [{"name": "SOL_AWC", "location": location}],
    }, {}, SWAT_PARAM_LIBRARY, tmp_path)
    assert expanded["physical"][0]["file"]["selectIndex"] == 3
