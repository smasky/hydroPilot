import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydropilot.config.schema.parameters import ParametersSpec
from hydropilot.models.swat.builder import buildSwatParams
from hydropilot.models.swat.library import SWAT_PARAM_LIBRARY
from hydropilot.params import ParamApplier, ParamWritePlan


def makeCn2Applier(project, rawParams, newline=b"\n", hardBound=True, functionManager=None):
    original = newline.join(
        [b"SWAT management input"] * 9
        + [b"            0.92    | BIOMIX", b"           80.76    | CN2", b"            1.00    | USLE_P"]
    ) + newline
    target = project / "000010001.mgt"
    target.write_bytes(original)
    expanded = buildSwatParams(rawParams, {}, SWAT_PARAM_LIBRARY, project)
    expanded["hardBound"] = hardBound
    cfg = SimpleNamespace(
        basic=SimpleNamespace(projectPath=str(project)),
        parameters=ParametersSpec.from_raw(expanded, project),
    )
    plan = ParamWritePlan(cfg)
    plan.initialize(str(project))
    return ParamApplier(cfg, functionManager, plan), target, original, expanded


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
@pytest.mark.parametrize(
    "mode,bounds,inputs,expected",
    [
        ("v", [35, 98], [72.5, 61.25, 72.5], [72.5, 61.25, 72.5]),
        ("r", [-0.2, 0.2], [0.1, -0.1, 0.1], [88.84, 72.68, 88.84]),
        ("a", [-10, 10], [-5, 5, -5], [75.76, 85.76, 75.76]),
    ],
)
def testCn2ModesUseOriginalValueAndPreserveFile(tmp_path, newline, mode, bounds, inputs, expected):
    applier, target, original, expanded = makeCn2Applier(
        tmp_path,
        {"design": [{"name": "CN2", "bounds": bounds}], "physical": [{"name": "CN2", "mode": mode}]},
        newline,
    )
    assert expanded["physical"][0]["bounds"] == [35, 98]
    originalLines = original.splitlines(keepends=True)
    for value, expectedValue in zip(inputs, expected):
        context = {}
        applier.apply(str(tmp_path), [value], context)
        lines = target.read_bytes().splitlines(keepends=True)
        assert float(lines[10][:16]) == expectedValue
        assert lines[:10] == originalLines[:10]
        assert lines[11:] == originalLines[11:]
        assert lines[10][16:] == originalLines[10][16:]
        assert context["param.writeRecords"][0]["old_value"] == 80.76
        assert not context.get("warnings")


@pytest.mark.parametrize("mode", ["v", "r", "a"])
def testCn2ExplicitPhysicalBoundsOverrideDesign(tmp_path, mode):
    applier, target, _, expanded = makeCn2Applier(
        tmp_path,
        {
            "design": [{"name": "CN2", "bounds": [-10, 100]}],
            "physical": [{"name": "CN2", "mode": mode, "bounds": [40, 85]}],
        },
    )
    assert expanded["physical"][0]["bounds"] == [40, 85]
    context = {}
    applier.apply(str(tmp_path), [100], context)
    assert float(target.read_bytes().splitlines()[10][:16]) == 85
    assert context["warnings"][0].code == "CLAMPED"


def testCn2ValueModeRetainsDesignBoundsWhenPhysicalBoundsAbsent(tmp_path):
    _, _, _, expanded = makeCn2Applier(
        tmp_path,
        {"design": [{"name": "CN2", "bounds": [50, 90]}], "physical": [{"name": "CN2"}]},
    )
    assert expanded["physical"][0]["bounds"] == [50, 90]


@pytest.mark.parametrize("hardBound,expected", [(True, 98), (False, 121.14)])
def testCn2RelativeChangesRespectHardBound(tmp_path, hardBound, expected):
    applier, target, _, _ = makeCn2Applier(
        tmp_path,
        {"design": [{"name": "CN2", "bounds": [-0.5, 0.5]}], "physical": [{"name": "CN2", "mode": "r"}]},
        hardBound=hardBound,
    )
    context = {}
    applier.apply(str(tmp_path), [0.5], context)
    assert float(target.read_bytes().splitlines()[10][:16]) == expected
    assert bool(context.get("warnings")) == hardBound


def testSihuDefaultMappingUsesParRelativeChangesWithoutSubtractingOne(tmp_path):
    raw = yaml.safe_load((ROOT / "examples/sihu/config.yaml").read_text())
    params = raw["parameters"]
    assert not params.get("transformer")
    assert all(item["kind"] == "builtin" for item in raw["functions"])
    assert [item["name"] for item in params["design"]] == [item["name"] for item in params["physical"]]
    design = next(item for item in params["design"] if item["name"] == "CN2")
    physical = next(item for item in params["physical"] if item["name"] == "CN2")
    assert design["bounds"] == [0.5, 1.5]
    applier, target, _, expanded = makeCn2Applier(
        tmp_path, {"design": [design], "physical": [physical]}
    )
    assert expanded["physical"][0]["bounds"] == [35, 98]
    context = {}
    applier.apply(str(tmp_path), [1.1], context)
    np.testing.assert_array_equal(context["P"], [1.1])
    # 80.76 * (1 + 1.1) is clipped at 98; interpreting 1.1 as a
    # multiplier would write 88.84 and would not produce this warning.
    assert float(target.read_bytes().splitlines()[10][:16]) == 98
    assert context["warnings"][0].code == "CLAMPED"


@pytest.mark.parametrize("factor,expected", [(0.8, 64.61), (1.0, 80.76), (1.2, 96.91)])
def testMonthlyTransformerWritesCn2Multiplier(tmp_path, factor, expected):
    moduleSpec = importlib.util.spec_from_file_location("monthly_transform", ROOT / "examples/monthly_transform.py")
    module = importlib.util.module_from_spec(moduleSpec)
    moduleSpec.loader.exec_module(module)
    params = yaml.safe_load((ROOT / "examples/test_monthly_complex.yaml").read_text())["parameters"]
    assert params["design"][0]["bounds"] == [0.8, 1.2]
    assert params["physical"][0]["mode"] == "r"
    result = module.monthly_transform([factor, 0.7, 100, 4])
    assert np.allclose(result, [factor - 1, factor - 1, 0.7, 0.7, 100, 4])

    class FunctionManager:
        def call(self, name, values):
            assert name == "monthly_transform"
            return module.monthly_transform(values)

    applier, target, _, expanded = makeCn2Applier(
        tmp_path,
        {
            "design": params["design"],
            "physical": [{"name": "CN2", "mode": "r"}],
            "transformer": "monthly_transform",
        },
        functionManager=FunctionManager(),
    )
    assert expanded["physical"][0]["bounds"] == [35, 98]
    applier.apply(str(tmp_path), [factor, 0.7, 100, 4], {})
    assert float(target.read_bytes().splitlines()[10][:16]) == expected
