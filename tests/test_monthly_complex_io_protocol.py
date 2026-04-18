from pathlib import Path
import sys
from datetime import date, datetime

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hydro_pilot.config.specs import CallSpec
from hydro_pilot.config.loader import load_config
from hydro_pilot.params.writers import getWriter
from hydro_pilot.params.writers.fixed_width import FixedWidthWriter
from hydro_pilot.series.readers import getReader
from hydro_pilot.series.readers.text_reader import TextReader
from hydro_pilot.series.extractor import SeriesExtractor
from hydro_pilot.templates.swat.discovery import discover_swat_project
from hydro_pilot.templates.swat.series import buildSwatSeries, inferSwatOutputType
from hydro_pilot.templates.swat.variables import calcSwatOutputRows
from hydro_pilot.errors import RunError

CFG_PATH = ROOT / "examples" / "test_monthly_complex.yaml"
PROJECT_PATH = Path(r"E:\BMPs\TxtInOut")


def _requires_monthly_project():
    if not PROJECT_PATH.exists():
        pytest.skip(f"SWAT monthly project not found: {PROJECT_PATH}")


def test_monthly_complex_template_expands_explicit_io_types():
    _requires_monthly_project()

    cfg = load_config(CFG_PATH)

    assert cfg.version == "general"
    assert len(cfg.parameters.design) == 4
    assert len(cfg.parameters.physical) == 6
    assert cfg.parameters.transformer == "monthly_transform"
    assert len(cfg.series) == 2
    assert len(cfg.objectives.use) == 2
    assert len(cfg.diagnostics.use) == 3

    assert {p.writerType for p in cfg.parameters.physical} == {"fixed_width"}
    assert all(s.sim.readerType == "text" for s in cfg.series)
    assert all(s.obs is not None and s.obs.readerType == "text" for s in cfg.series)

    general_path = CFG_PATH.with_name(f"{CFG_PATH.stem}_general.yaml")
    assert general_path.exists()
    general_text = general_path.read_text(encoding="utf-8")
    assert "writerType: fixed_width" in general_text
    assert "readerType: text" in general_text


def test_swat_series_builder_extracts_monthly_rows_and_defaults():
    _requires_monthly_project()

    meta = discover_swat_project(PROJECT_PATH)
    raw_series = [{
        "id": "flow",
        "sim": {
            "file": "output.rch",
            "subbasin": 1,
            "period": [2019, 2021],
        },
        "obs": {
            "file": "obs_flow_monthly.txt",
            "rowRanges": [[1, 36]],
            "colSpan": [1, 12],
        },
    }]

    result = buildSwatSeries(raw_series, meta, readerType="text")

    sim = result[0]["sim"]
    assert sim["readerType"] == "text"
    assert "subbasin" not in sim
    assert "period" not in sim
    assert sim["rowRanges"]
    assert result[0]["size"] == 36
    assert result[0]["obs"]["readerType"] == "text"


def test_swat_period_accepts_yaml_date_objects_for_monthly_rows():
    meta = {
        "output_start_year": 2019,
        "output_end_year": 2021,
        "n_subbasins": 62,
        "subbasins": {},
        "timestep": "monthly",
    }

    month_rows = calcSwatOutputRows(
        meta=meta,
        outputType="rch",
        subbasin=62,
        period=["2019-02", "2021-11"],
        timestep="monthly",
    )
    date_rows = calcSwatOutputRows(
        meta=meta,
        outputType="rch",
        subbasin=62,
        period=[date(2019, 2, 3), datetime(2021, 11, 1, 8, 30)],
        timestep="monthly",
    )

    assert date_rows == month_rows
    assert date_rows["size"] == 34



def test_series_extractor_warns_and_flattens_called_series_shape():
    call_spec = CallSpec(func="make_series", args=["flow.sim"])

    class DummyFuncManager:
        def call(self, func_name, *args):
            assert func_name == "make_series"
            return [[1.0, 2.0], [3.0, 4.0]]

    class DummyCfg:
        series = []
        series_index = {"flow": type("SeriesNode", (), {"sim": None})()}

    extractor = SeriesExtractor(DummyCfg(), DummyFuncManager())
    extractor.seriesDict = {
        "derived_flow": {"obs": None, "simItem": call_spec, "obsItem": None}
    }

    context = {"flow.sim": [10.0, 20.0], "warnings": []}
    env = extractor.extract_all("work", context)

    assert env["derived_flow.sim"].tolist() == [1.0, 2.0, 3.0, 4.0]
    assert len(env["warnings"]) == 1
    assert env["warnings"][0].code == "SERIES_CALL_NON_1D"



def test_series_extractor_requires_called_series_dependencies_in_order():
    call_spec = CallSpec(func="make_series", args=["later.sim"])

    class DummyFuncManager:
        def call(self, func_name, *args):
            return args

    class DummyCfg:
        series = []
        series_index = {"later": type("SeriesNode", (), {"sim": None})()}

    extractor = SeriesExtractor(DummyCfg(), DummyFuncManager())
    extractor.seriesDict = {
        "early": {"obs": None, "simItem": call_spec, "obsItem": None}
    }

    with pytest.raises(RunError, match="defined earlier in series order"):
        extractor.extract_all("work", {"warnings": []})



def test_infer_swat_output_type_handles_supported_paths():
    assert inferSwatOutputType("output.rch") == "rch"
    assert inferSwatOutputType("foo/output.sub") == "sub"
    assert inferSwatOutputType(r"foo\output.hru") == "hru"
    assert inferSwatOutputType("output.txt") is None


def test_non_swat_output_series_keeps_general_fields():
    raw_series = [{
        "id": "custom",
        "sim": {
            "file": "custom_output.txt",
            "subbasin": 3,
            "period": [2019, 2021],
            "rowRanges": [[1, 3]],
            "colSpan": [1, 12],
        },
    }]

    result = buildSwatSeries(raw_series, meta={}, readerType="text")

    sim = result[0]["sim"]
    assert sim["readerType"] == "text"
    assert sim["subbasin"] == 3
    assert sim["period"] == [2019, 2021]
    assert sim["rowRanges"] == [[1, 3]]
    assert sim["colSpan"] == [1, 12]
    assert "size" not in result[0]


def test_minimal_io_registries_dispatch_existing_implementations():
    assert getWriter("fixed_width") is FixedWidthWriter
    assert getReader("text") is TextReader

    with pytest.raises(ValueError, match="Unknown writer type"):
        getWriter("missing_writer")
    with pytest.raises(ValueError, match="Unknown reader type"):
        getReader("missing_reader")
