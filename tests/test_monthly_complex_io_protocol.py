from pathlib import Path
import sys
from datetime import date, datetime

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydropilot.config.specs import CallSpec
from hydropilot.config.loader import load_config, prepare_config
from hydropilot.validation.entry import validate_config
from hydropilot.validation.diagnostics import has_error
from hydropilot.io.writers import getWriter
from hydropilot.io.writers.fixed_width import FixedWidthWriter
from hydropilot.io.writers.csv import CsvWriter
from hydropilot.io.readers import getReader
from hydropilot.io.readers.text import TextReader
from hydropilot.io.readers.csv import CsvReader
from hydropilot.series import ObsStore, SeriesExtractor, SeriesPlan, SeriesPlanItem
from hydropilot.models.swat.discovery import discover_swat_project
from hydropilot.models.swat.library import SWAT_DB, SWAT_PARAM_LIBRARY
from hydropilot.models.swat.series import buildSwatSeries, inferSwatOutputType
from hydropilot.models.swat.variables import calcSwatOutputRows
from hydropilot.models.swat.validate import validate_swat_config
from hydropilot.runtime.errors import RunError

CFG_PATH = ROOT / "tests" / "fixtures" / "configs" / "monthly_complex.yaml"
PROJECT_PATH = Path(r"E:\BMPs\TxtInOut")


def _requires_monthly_project():
    if not PROJECT_PATH.exists():
        pytest.skip(f"SWAT monthly project not found: {PROJECT_PATH}")


def test_swat_library_reads_parameters_from_swat_db():
    assert SWAT_PARAM_LIBRARY == SWAT_DB["parameters"]
    assert "parameters" in SWAT_DB
    assert "series" in SWAT_DB
    assert "CN2" in SWAT_PARAM_LIBRARY


def test_monthly_complex_template_expands_explicit_io_types():
    _requires_monthly_project()

    diagnostics = validate_config(CFG_PATH)
    prepared = prepare_config(CFG_PATH)
    cfg = load_config(CFG_PATH)

    assert not has_error(diagnostics)
    assert any(item.path == "parameters.transformer" for item in diagnostics)
    assert prepared.version == "swat"
    assert prepared.expanded_raw["version"] == "general"
    assert "reporter" not in prepared.expanded_raw
    assert cfg.version == "general"
    assert cfg.reporter.flushInterval == 50
    assert cfg.reporter.holdingPenLimit == 20
    assert cfg.reporter.series == []
    assert len(cfg.parameters.design) == 4
    assert len(cfg.parameters.physical) == 6
    assert cfg.parameters.transformer == "monthly_transform"
    assert len(cfg.series) == 2
    assert len(cfg.objectives.items) == 2
    assert len(cfg.diagnostics.items) == 3

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
            "variable": "FLOW_OUT",
            "id": 1,
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
    assert sim["colSpan"] == [52, 61]
    assert "id" not in sim
    assert "period" not in sim
    assert sim["rowRanges"]
    assert "size" not in result[0]
    assert result[0]["obs"]["readerType"] == "text"


def test_swat_series_builder_keeps_explicit_column_when_variable_is_present():
    meta = {
        "output_start_year": 2019,
        "output_end_year": 2021,
        "n_subbasins": 3,
        "subbasins": {},
        "timestep": "monthly",
    }
    raw_series = [{
        "id": "flow",
        "sim": {
            "file": "output.rch",
            "variable": "__BAD_VARIABLE__",
            "id": 1,
            "period": [2019, 2021],
            "colSpan": [999, 1000],
        },
    }]

    result = buildSwatSeries(raw_series, meta, readerType="text")
    assert result[0]["sim"]["colSpan"] == [999, 1000]


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
        id=62,
        period=["2019-02", "2021-11"],
        timestep="monthly",
    )
    date_rows = calcSwatOutputRows(
        meta=meta,
        outputType="rch",
        id=62,
        period=[date(2019, 2, 3), datetime(2021, 11, 1, 8, 30)],
        timestep="monthly",
    )

    assert date_rows == month_rows
    assert date_rows["size"] == 34


def test_validate_swat_config_rejects_sim_timestep_override(tmp_path: Path):
    project = tmp_path / "TxtInOut"
    project.mkdir()
    (project / "file.cio").write_text("stub\n", encoding="utf-8")
    (project / "fig.fig").write_text("stub\n", encoding="utf-8")

    raw = {
        "version": "swat",
        "basic": {
            "projectPath": str(project),
            "workPath": "./work",
            "command": "swat.exe",
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.rch",
                "variable": "FLOW_OUT",
                "id": 1,
                "period": [2019, 2021],
                "timestep": "monthly",
            },
            "obs": {
                "file": "obs.txt",
                "rowRanges": [[1, 36]],
                "colSpan": [1, 12],
            },
        }],
    }

    diagnostics = validate_swat_config(
        raw,
        tmp_path,
        meta_override={
            "timestep": "monthly",
            "output_start_year": 2019,
            "output_end_year": 2021,
            "n_subbasins": 3,
            "subbasins": {},
        },
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].level == "error"
    assert diagnostics[0].path == "series[flow].sim.timestep"
    assert diagnostics[0].message == "sim.timestep is not supported for SWAT; timestep is derived from project metadata"


def test_validate_swat_config_warns_when_period_is_clipped_to_output_window(tmp_path: Path):
    project = tmp_path / "TxtInOut"
    project.mkdir()
    (project / "file.cio").write_text("stub\n", encoding="utf-8")
    (project / "fig.fig").write_text("stub\n", encoding="utf-8")

    raw = {
        "version": "swat",
        "basic": {
            "projectPath": str(project),
            "workPath": "./work",
            "command": "swat.exe",
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.rch",
                "variable": "FLOW_OUT",
                "id": 1,
                "period": [2018, 2022],
            },
            "obs": {
                "file": "obs.txt",
                "rowRanges": [[1, 36]],
                "colSpan": [1, 12],
            },
        }],
    }

    diagnostics = validate_swat_config(
        raw,
        tmp_path,
        meta_override={
            "timestep": "monthly",
            "output_start_year": 2019,
            "output_end_year": 2021,
            "n_subbasins": 3,
            "subbasins": {},
        },
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].level == "warning"
    assert diagnostics[0].path == "series[flow].sim.period"
    assert "extends outside the SWAT output window [2019-01-01, 2021-12-31]" in diagnostics[0].message



def test_series_extractor_warns_and_flattens_called_series_shape():
    call_spec = CallSpec(func="make_series", args=["flow.sim"])

    class DummyFuncManager:
        def call(self, func_name, *args):
            assert func_name == "make_series"
            return [[1.0, 2.0], [3.0, 4.0]]

    class DummyCfg:
        series = []
        series_index = {"flow": type("SeriesNode", (), {"sim": None})()}

    plan = SeriesPlan([])
    plan.seriesItems = {
        "derived_flow": SeriesPlanItem(id="derived_flow", obs=None, sim=call_spec)
    }

    class DummyObsStore(ObsStore):
        def __init__(self):
            self.obs_data = {}

    extractor = SeriesExtractor(DummyCfg(), DummyFuncManager(), plan, DummyObsStore())

    context = {"flow.sim": [10.0, 20.0], "warnings": []}
    env = extractor.extract("work", context)

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

    plan = SeriesPlan([])
    plan.seriesItems = {
        "early": SeriesPlanItem(id="early", obs=None, sim=call_spec)
    }

    class DummyObsStore(ObsStore):
        def __init__(self):
            self.obs_data = {}

    extractor = SeriesExtractor(DummyCfg(), DummyFuncManager(), plan, DummyObsStore())

    with pytest.raises(RunError, match="defined earlier in series order"):
        extractor.extract("work", {"warnings": []})



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
            "id": 3,
            "period": [2019, 2021],
            "rowRanges": [[1, 3]],
            "colSpan": [1, 12],
        },
    }]

    result = buildSwatSeries(raw_series, meta={}, readerType="text")

    sim = result[0]["sim"]
    assert sim["readerType"] == "text"
    assert sim["id"] == 3
    assert sim["period"] == [2019, 2021]
    assert sim["rowRanges"] == [[1, 3]]
    assert sim["colSpan"] == [1, 12]
    assert "size" not in result[0]


def test_non_swat_output_series_with_variable_requires_explicit_column():
    raw_series = [{
        "id": "custom",
        "sim": {
            "file": "custom_output.txt",
            "variable": "FLOW_OUT",
            "id": 3,
            "period": [2019, 2021],
        },
    }]

    with pytest.raises(ValueError, match="requires a SWAT output file"):
        buildSwatSeries(raw_series, meta={"timestep": "monthly"}, readerType="text")


def test_swat_series_variable_must_match_file():
    raw_series = [{
        "id": "bad",
        "sim": {
            "file": "output.rch",
            "variable": "__NOT_A_SWAT_VARIABLE__",
            "id": 1,
            "period": [2019, 2021],
        },
    }]

    with pytest.raises(ValueError, match="does not match file"):
        buildSwatSeries(raw_series, meta={"timestep": "monthly"}, readerType="text")


def test_obs_variable_is_not_auto_resolved():
    raw_series = [{
        "id": "flow",
        "sim": {
            "file": "output.rch",
            "variable": "FLOW_OUT",
            "id": 1,
            "period": [2019, 2021],
            "colSpan": [52, 61],
        },
        "obs": {
            "file": "obs.txt",
            "rowRanges": [[1, 10]],
            "variable": "FLOW_OUT",
        },
    }]

    result = buildSwatSeries(
        raw_series,
        meta={"timestep": "monthly", "output_start_year": 2019, "output_end_year": 2021, "n_subbasins": 3, "subbasins": {}},
        readerType="text",
    )
    assert "colSpan" not in result[0]["obs"]
    assert result[0]["obs"]["readerType"] == "text"


def test_minimal_io_registries_dispatch_existing_implementations():
    assert getWriter("fixed_width") is FixedWidthWriter
    assert getWriter("csv") is CsvWriter
    assert getReader("text") is TextReader
    assert getReader("csv") is CsvReader

    with pytest.raises(ValueError, match="Unknown writer type"):
        getWriter("missing_writer")
    with pytest.raises(ValueError, match="Unknown reader type"):
        getReader("missing_reader")


def test_csv_reader_extracts_column_after_head_skip_with_row_ranges_and_row_list(tmp_path: Path):
    source = tmp_path / "output.csv"
    source.write_text(
        "date,q,et\n"
        "1,10.5,0.1\n"
        "2,11.5,0.2\n"
        "3,12.5,0.3\n"
        "4,13.5,0.4\n",
        encoding="utf-8-sig",
    )

    spec = CsvReader.buildSpec(
        {
            "readerType": "csv",
            "file": "output.csv",
            "headSkip": 1,
            "rowRanges": [[1, 2]],
            "rowList": [4],
            "colNum": 2,
            "delimiter": ",",
        },
        base_path=tmp_path,
        check_file=True,
    )

    values = CsvReader().read(None, spec)

    assert values.tolist() == [10.5, 11.5, 13.5]


def test_csv_reader_fails_when_selected_cell_is_not_numeric(tmp_path: Path):
    source = tmp_path / "output.csv"
    source.write_text("date,q\n1,bad\n", encoding="utf-8-sig")

    spec = CsvReader.buildSpec(
        {
            "readerType": "csv",
            "file": "output.csv",
            "headSkip": 1,
            "rowRanges": [[1, 1]],
            "colNum": 2,
        },
        base_path=tmp_path,
        check_file=True,
    )

    with pytest.raises(ValueError, match="csv value is not numeric"):
        CsvReader().read(None, spec)


def test_csv_writer_updates_selected_column_after_head_skip(tmp_path: Path):
    source = tmp_path / "params.csv"
    source.write_text(
        "name,value,other\n"
        "K,1.0,9\n"
        "SM,2.0,8\n"
        "WM,3.0,7\n",
        encoding="utf-8-sig",
    )

    spec = CsvWriter.buildSpec({
        "name": "K",
        "type": "float",
        "mode": "v",
        "bounds": [0.0, 10.0],
        "writerType": "csv",
        "file": {
            "name": "params.csv",
            "headSkip": 1,
            "rowRanges": [[1, 2]],
            "colNum": 2,
            "delimiter": ",",
        },
    })
    param = type("ParamSpec", (), {"name": "K", "index": 0, "modeCode": 1})()
    writer = CsvWriter(str(source))

    assert writer.register_param(param, spec)
    result = writer.set_values_and_save(str(source), [0], [5.25])

    assert source.read_text(encoding="utf-8-sig").splitlines() == [
        "name,value,other",
        "K,5.25,9",
        "SM,5.25,8",
        "WM,3.0,7",
    ]
    assert [record["locator"] for record in result["write_records"]] == [
        "row=1;col=2",
        "row=2;col=2",
    ]
    assert not source.read_bytes().startswith(b"\xef\xbb\xbf")


def test_csv_writer_fails_when_selected_cell_is_empty(tmp_path: Path):
    source = tmp_path / "params.csv"
    source.write_text("name,value\nK,\n", encoding="utf-8-sig")

    spec = CsvWriter.buildSpec({
        "name": "K",
        "writerType": "csv",
        "file": {
            "name": "params.csv",
            "headSkip": 1,
            "rowRanges": [[1, 1]],
            "colNum": 2,
        },
    })
    param = type("ParamSpec", (), {"name": "K", "index": 0, "modeCode": 1})()
    writer = CsvWriter(str(source))

    with pytest.raises(ValueError, match="csv value is empty"):
        writer.register_param(param, spec)
