from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydropilot.api.apply import apply_design_params
from hydropilot.config.loader import ConfigPreparationError, load_config, prepare_config
from hydropilot.params.write_plan import ParamWritePlan
from hydropilot.io.readers import getReader
from hydropilot.io.writers import getWriter
from hydropilot.models.registry import get_template
from hydropilot.models.swatplus.discovery import discover_swatplus_project
from hydropilot.models.swatplus.library import (
    SWATPLUS_DB,
    SWATPLUS_PARAM_LIBRARY,
    get_known_output_files,
    get_known_variable_names,
    lookupSeriesVariable,
)
from hydropilot.models.swatplus.series import (
    _detectFrequency,
    inferSwatPlusObjectType as _inferObjectType,
)
from hydropilot.models.swatplus.template import SwatPlusTemplate
from hydropilot.models.swatplus.validate import validate_swatplus_config
from hydropilot.validation.diagnostics import has_error
from hydropilot.validation.entry import validate_config


# ── fixture helpers (Ames_sub1 aligned) ────────────────────────────


def _write_swatplus_project(path: Path, n_hrus: int = 3) -> None:
    """Create a minimal SWAT+ project mirroring Ames_sub1 structure.

    Creates the core files: file.cio, time.sim, print.prt, hru-data.hru,
    parameters.bsn, hydrology.hyd, basin_wb_aa.txt.
    """
    path.mkdir(parents=True, exist_ok=True)

    (path / "file.cio").write_text(
        "file.cio: ames_sub1\n"
        "simulation        time.sim          print.prt         null              object.cnt        null\n"
        "basin             codes.bsn         parameters.bsn\n"
        "hru               hru-data.hru      null\n"
        "hydrology         hydrology.hyd     topography.hyd    null\n",
        encoding="utf-8",
    )

    (path / "time.sim").write_text(
        "time.sim\n"
        "       0      1975         0      1980         0\n",
        encoding="utf-8",
    )

    (path / "print.prt").write_text(
        "print.prt\n"
        "   0           0         1975         0      1980         1\n",
        encoding="utf-8",
    )

    hru_lines = [
        "hru-data.hru",
        "      id  name                          topo             hydro              soil            lu_mgt   soil_plant_init         surf_stor              snow             field",
    ]
    lu_mgts = {1: "cosy_lum", 2: "mntill_corn_lum"}  # HRU 2 is different (Ames_sub1 pattern)
    for i in range(1, n_hrus + 1):
        lu = lu_mgts.get(i, "cosy_lum")
        hru_lines.append(
            f"       {i}  hru{i:04d}                topohru{i:04d}           hyd{i:04d}"
            f"           soil_{i:02d}          {lu}        soilplant1              null           snow001              null"
        )
    (path / "hru-data.hru").write_text("\n".join(hru_lines) + "\n", encoding="utf-8")

    (path / "parameters.bsn").write_text(
        "parameters.bsn: written by SWAT+ editor\n"
        "  lai_noevap       sw_init      surq_lag      adj_pkrt\n"
        "     3.00000       0.50000       4.00000       1.00000\n",
        encoding="utf-8",
    )

    hyd_lines = [
        "hydrology.hyd",
        "name                 lat_ttime       lat_sed       can_max          esco          epco       bio_mix         perco",
    ]
    for i in range(1, n_hrus + 1):
        hyd_lines.append(
            f"hyd{i:04d}                0.00000       0.00000       0.00000       0.95000       1.00000       0.20000       0.50000"
        )
    (path / "hydrology.hyd").write_text("\n".join(hyd_lines) + "\n", encoding="utf-8")

    (path / "basin_wb_aa.txt").write_text(
        " demo                      SWAT+ 2025-03-31        MODULAR Rev 2025.61.0.2.11\n",
        encoding="utf-8",
    )

    # soils.sol — Ames_sub1-style profiles
    sol_lines = [
        "soils.sol test",
        "   name               NLY  HYD_GRP        ZMX    ANION_EXCL     CRK       TEXTURE        DEPTH        BD       AWC        K        CBN      CLAY      SILT      SAND      ROCK       ALB     USLE_K       EC       CAL        PH",
    ]
    for i in range(1, n_hrus + 1):
        sol_lines.append(f"soil_{i:02d}                 4        B   2000.000        0.500    0.500       L- L- L- L")
        for depth in (50, 150, 840, 2000):
            sol_lines.append(f"{'':>90}{depth:>8.2f}     1.200     0.200   30.000     1.500    21.000    34.000    45.000     8.000     0.160     0.240     0.000     0.000     5.700")
    # hydro-variant: soil_01-h1, soil_03-h3
    for suffix, base_i in [("h1", 1), ("h3", 3)]:
        sol_lines.append(f"soil_{base_i:02d}-{suffix}                 4        B   2000.000        0.500    0.500       L- L- L- L")
        for depth in (50, 150, 840, 2000):
            sol_lines.append(f"{'':>90}{depth:>8.2f}     1.200     0.200   30.000     1.500    21.000    34.000    45.000     8.000     0.160     0.240     0.000     0.000     5.700")
    (path / "soils.sol").write_text("\n".join(sol_lines) + "\n", encoding="utf-8")


def _base_config(project: Path, work: Path) -> dict:
    return {
        "version": "swatplus",
        "basic": {
            "projectPath": str(project),
            "workPath": str(work),
            "command": "swatplus.exe",
        },
        "parameters": {
            "design": [
                {"name": "surq_lag"},
                {"name": "esco", "bounds": [0.1, 0.9]},
            ],
            "physical": [
                {"name": "surq_lag", "mode": "v"},
                {"name": "esco", "mode": "v"},
            ],
        },
        "series": [
            {
                "id": "flow",
                "sim": {
                    "file": "basin_wb_aa.txt",
                    "variable": "WYLD",
                    "id": 1,
                    "period": [1977, 1980],
                },
                "obs": {
                    "file": "obs.txt",
                    "rowRanges": [[1, 4]],
                    "colNum": 1,
                },
            },
        ],
        "objectives": [{"id": "obj_flow", "ref": "flow.sim", "sense": "max"}],
    }


# ── database + library tests ─────────────────────────────────────


def test_db_loads_parameters():
    assert SWATPLUS_DB is not None
    assert "parameters" in SWATPLUS_DB
    assert "series" in SWATPLUS_DB
    assert "surq_lag" in SWATPLUS_PARAM_LIBRARY
    assert "esco" in SWATPLUS_PARAM_LIBRARY
    assert SWATPLUS_PARAM_LIBRARY["surq_lag"]["type"] == "float"
    assert SWATPLUS_PARAM_LIBRARY["esco"]["bounds"] == [0.0, 1.0]


def test_get_known_output_files():
    files = get_known_output_files()
    assert "basin_wb_aa.txt" in files
    assert "output.rch" not in files


def test_get_known_variable_names():
    names = get_known_variable_names()
    assert "WYLD" in names
    assert "PREC" in names
    assert "FLOW_OUT" in names


def test_lookup_series_variable_resolves_file_and_colspan():
    result = lookupSeriesVariable("WYLD")
    assert result is not None
    assert result["file"] == "basin_wb_aa.txt"
    assert result["colSpan"] == [25, 36]

    result = lookupSeriesVariable("PREC")
    assert result is not None
    assert result["file"] == "basin_wb_aa.txt"
    assert result["colSpan"] == [1, 12]

    result = lookupSeriesVariable("FLOW_OUT")
    assert result is not None
    assert result["colNum"] == 11


def test_infer_object_type_recognises_swatplus_prefixes():
    assert _inferObjectType("basin_wb_aa.txt") == "basin"
    assert _inferObjectType("hru_wb_aa.txt") == "hru"
    assert _inferObjectType("hru-lte_wb_aa.txt") == "hru-lte"
    assert _inferObjectType("channel_sd_aa.txt") == "channel"
    assert _inferObjectType("ru_aa.txt") == "ru"
    assert _inferObjectType("aquifer_wb_aa.txt") == "aquifer"
    assert _inferObjectType("reservoir_wb_aa.txt") == "reservoir"
    assert _inferObjectType("hydout_aa.txt") is None  # "hydout" ≠ "hyd_" prefix
    assert _inferObjectType("region_wb_aa.txt") == "region"
    assert _inferObjectType("lsunit_wb_aa.txt") == "lsunit"


# ── discovery tests ───────────────────────────────────────────────


def test_discovery_parses_ames_sub1_metadata(tmp_path: Path):
    _write_swatplus_project(tmp_path)
    meta = discover_swatplus_project(tmp_path)

    assert meta["start_year"] == 1975
    assert meta["end_year"] == 1980
    assert meta["nyskip"] == 0
    assert meta["output_start_year"] == 1975
    assert meta["output_end_year"] == 1980
    assert meta["timestep"] == "daily"
    assert meta["n_hrus"] >= 1


def test_discovery_counts_hrus(tmp_path: Path):
    _write_swatplus_project(tmp_path, n_hrus=5)
    meta = discover_swatplus_project(tmp_path)
    assert meta["n_hrus"] == 5


def test_discovery_respects_nyskip(tmp_path: Path):
    _write_swatplus_project(tmp_path)
    (tmp_path / "print.prt").write_text(
        "print.prt\n"
        "   2           0         1975         0      1980         1\n",
        encoding="utf-8",
    )
    meta = discover_swatplus_project(tmp_path)
    assert meta["nyskip"] == 2
    assert meta["output_start_year"] == 1977


def test_discovery_daily_vs_monthly_interval(tmp_path: Path):
    _write_swatplus_project(tmp_path)
    meta_daily = discover_swatplus_project(tmp_path)
    assert meta_daily["timestep"] == "daily"

    (tmp_path / "print.prt").write_text(
        "print.prt\n"
        "   0           0         1975         0      1980         0\n",
        encoding="utf-8",
    )
    meta_monthly = discover_swatplus_project(tmp_path)
    assert meta_monthly["timestep"] == "monthly"

    (tmp_path / "print.prt").write_text(
        "print.prt\n"
        "   0           0         1975         0      1980         2\n",
        encoding="utf-8",
    )
    meta_yearly = discover_swatplus_project(tmp_path)
    assert meta_yearly["timestep"] == "yearly"


def test_discovery_rejects_missing_file_cio(tmp_path: Path):
    (tmp_path / "time.sim").write_text("time.sim\n       0      1975         0      1980         0\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="file.cio"):
        discover_swatplus_project(tmp_path)


def test_discovery_rejects_missing_time_sim(tmp_path: Path):
    _write_swatplus_project(tmp_path)
    (tmp_path / "time.sim").unlink()
    with pytest.raises(FileNotFoundError, match="time.sim"):
        discover_swatplus_project(tmp_path)


def test_discovery_rejects_missing_print_prt(tmp_path: Path):
    _write_swatplus_project(tmp_path)
    (tmp_path / "print.prt").unlink()
    with pytest.raises(FileNotFoundError, match="print.prt"):
        discover_swatplus_project(tmp_path)


# ── registry tests ───────────────────────────────────────────────


def test_swatplus_registered_and_io_types():
    template = get_template("swatplus")
    assert isinstance(template, SwatPlusTemplate)
    assert template.get_writer_type() == "formatted_text"
    assert template.get_reader_type() == "text"


# ── template expansion tests ─────────────────────────────────────


def test_template_expands_to_general(tmp_path: Path):
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n2\n3\n4\n", encoding="ascii")

    raw = _base_config(project, work)
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    assert expanded["version"] == "general"

    # design: names kept, bounds auto-completed from db
    assert expanded["parameters"]["design"][0]["name"] == "surq_lag"
    assert expanded["parameters"]["design"][0]["bounds"] == [0.05, 24.0]
    assert expanded["parameters"]["design"][1]["name"] == "esco"
    assert expanded["parameters"]["design"][1]["bounds"] == [0.1, 0.9]

    # physical: both params now target calibration.cal via formatted_text
    phys = expanded["parameters"]["physical"]
    assert len(phys) == 2
    for p in phys:
        assert p["writerType"] == "formatted_text"
        assert p["file"]["name"] == "calibration.cal"
        assert p["file"]["col"] == 30
        assert p["file"]["width"] == 16
        assert "_skel" in p["file"]  # skeleton injected

    # series: variable resolved from db, colSpan expanded (uses WYLD now)
    sim = expanded["series"][0]["sim"]
    assert sim["readerType"] == "text"
    assert sim["file"] == "basin_wb_aa.txt"
    assert sim["colSpan"] == [25, 36]
    assert "variable" not in sim


def test_template_auto_completes_missing_physical(tmp_path: Path):
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n2\n3\n4\n", encoding="ascii")

    raw = _base_config(project, work)
    del raw["parameters"]["physical"]
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    phys = expanded["parameters"]["physical"]
    assert len(phys) == 2
    for p in phys:
        assert p["file"]["name"] == "calibration.cal"
        assert p["writerType"] == "formatted_text"


def test_series_keeps_explicit_colspan(tmp_path: Path):
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n2\n3\n4\n", encoding="ascii")

    raw = _base_config(project, work)
    raw["series"][0]["sim"]["colSpan"] = [999, 1000]
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    assert expanded["series"][0]["sim"]["colSpan"] == [999, 1000]


def test_series_row_ranges_computed_from_id_and_period(tmp_path: Path):
    """When id+period are given, rowRanges are computed — not left as id/period."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project, n_hrus=3)
    (tmp_path / "obs.txt").write_text("1\n2\n3\n4\n", encoding="ascii")

    raw = _base_config(project, work)
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    sim = expanded["series"][0]["sim"]
    assert "rowRanges" in sim
    # id and period consumed, not passed through
    assert "id" not in sim
    assert "period" not in sim


def test_series_unknown_variable_raises(tmp_path: Path):
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)

    raw = _base_config(project, work)
    raw["series"][0]["sim"]["variable"] = "__UNKNOWN__"
    with pytest.raises(ValueError, match=r"not a known SWAT\+ output variable"):
        SwatPlusTemplate().build_config(raw, tmp_path)


# ── discovery: HRU metadata (Phase 2 filter) ─────────────────────


def test_discovery_hru_meta_parses_attributes(tmp_path: Path):
    _write_swatplus_project(tmp_path, n_hrus=3)
    meta = discover_swatplus_project(tmp_path)
    hru_meta = meta["hru_meta"]

    assert len(hru_meta) == 3
    assert hru_meta[1]["lu_mgt"] == "cosy_lum"
    assert hru_meta[1]["soil"] == "soil_01"
    assert hru_meta[1]["hydro_name"] == "hyd0001"
    assert hru_meta[2]["lu_mgt"] == "mntill_corn_lum"
    assert hru_meta[2]["soil"] == "soil_02"
    assert hru_meta[2]["hydro_name"] == "hyd0002"
    assert hru_meta[3]["lu_mgt"] == "cosy_lum"
    assert hru_meta[3]["soil"] == "soil_03"


# ── filter expansion tests ───────────────────────────────────────


def _filter_config(project: Path, work: Path) -> dict:
    """Base config with a filtered physical parameter."""
    return {
        "version": "swatplus",
        "basic": {
            "projectPath": str(project),
            "workPath": str(work),
            "command": "swatplus.exe",
        },
        "parameters": {
            "design": [
                {"name": "esco", "bounds": [0.1, 0.9]},
            ],
            "physical": [
                {
                    "name": "esco",
                    "mode": "v",
                    "filter": {"lu_mgt": "cosy_lum"},
                },
            ],
        },
        "series": [
            {
                "id": "flow",
                "sim": {
                    "file": "basin_wb_aa.txt",
                    "variable": "WYLD",
                    "id": 1,
                    "period": [1977, 1980],
                },
            },
        ],
        "objectives": [{"id": "obj_flow", "ref": "flow.sim", "sense": "max"}],
    }


def test_filter_lu_mgt_resolves_to_object_tail_in_skeleton(tmp_path: Path):
    """lu_mgt=cosy_lum filter → resolves to HRU IDs 1 and 3 → OBJ_TOT=2
    with object tail in the calibration.cal skeleton."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project, n_hrus=3)

    raw = _filter_config(project, work)
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    phys = expanded["parameters"]["physical"]
    assert len(phys) == 1
    entry = phys[0]
    assert entry["file"]["name"] == "calibration.cal"

    # filter is consumed during build — internal artifact, not in output

    # skeleton record must have OBJ_TOT=2 and object tail for HRUs 1, 3
    skel = entry["file"]["_skel"]
    for line in skel.split("\n"):
        if line.startswith("esco"):
            assert "       2" in line  # OBJ_TOT
            assert "       1" in line  # HRU 1
            assert "       3" in line  # HRU 3


def test_filter_object_id_passthrough(tmp_path: Path):
    """object_id filter → IDs used directly in the skeleton tail."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)

    raw = _filter_config(project, work)
    raw["parameters"]["physical"][0]["filter"] = {"object_id": [12, 18, 21]}
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    entry = expanded["parameters"]["physical"][0]
    skel = entry["file"]["_skel"]
    for line in skel.split("\n"):
        if line.startswith("esco"):
            assert "       3" in line   # OBJ_TOT
            assert "      12" in line
            assert "      18" in line
            assert "      21" in line


def test_filter_soil_resolves_correct_hrus(tmp_path: Path):
    """soil=soil_02 → only HRU 2 matches, OBJ_TOT=1."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project, n_hrus=3)

    raw = _filter_config(project, work)
    raw["parameters"]["physical"][0]["filter"] = {"soil": "soil_02"}
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    entry = expanded["parameters"]["physical"][0]
    skel = entry["file"]["_skel"]
    for line in skel.split("\n"):
        if line.startswith("esco"):
            assert "       1" in line   # OBJ_TOT
            assert "       2" in line   # HRU 2


def test_filter_multiple_fields_and_logic(tmp_path: Path):
    """lu_mgt=cosy_lum AND soil=soil_01 → only HRU 1 matches both."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project, n_hrus=3)

    raw = _filter_config(project, work)
    raw["parameters"]["physical"][0]["filter"] = {"lu_mgt": "cosy_lum", "soil": "soil_01"}
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    entry = expanded["parameters"]["physical"][0]
    skel = entry["file"]["_skel"]
    for line in skel.split("\n"):
        if line.startswith("esco"):
            assert "       1" in line   # OBJ_TOT
            assert "       1" in line   # HRU 1


def test_filter_no_match_returns_zero_objs(tmp_path: Path):
    """lu_mgt=nonexistent → OBJ_TOT=0, no object tail."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project, n_hrus=3)

    raw = _filter_config(project, work)
    raw["parameters"]["physical"][0]["filter"] = {"lu_mgt": "nonexistent_lum"}
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    entry = expanded["parameters"]["physical"][0]
    skel = entry["file"]["_skel"]
    for line in skel.split("\n"):
        if line.startswith("esco"):
            # OBJ_TOT must be 0, no object tail digits after it
            assert "       0" in line   # OBJ_TOT
            # The esco line should NOT have extra digit tokens after OBJ_TOT
            tokens = line.split()
            assert tokens[-1] == "0"  # last token is OBJ_TOT


def test_filter_no_filter_returns_zero_objs(tmp_path: Path):
    """No filter → OBJ_TOT=0 for all entries."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)

    raw = _base_config(project, work)
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    for entry in expanded["parameters"]["physical"]:
        skel = entry["file"]["_skel"]
        name = entry["name"]
        for line in skel.split("\n"):
            if line.startswith(name):
                assert "       0" in line  # OBJ_TOT


def test_filter_on_basin_param_ignored_obj_tot_zero(tmp_path: Path):
    """Basin-level parameter (surq_lag from parameters.bsn) with a filter
    must NOT get HRU object IDs — OBJ_TOT=0 even though HRUs match."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project, n_hrus=3)

    raw = _base_config(project, work)
    # Add filter to the basin param surq_lag (from parameters.bsn)
    raw["parameters"]["physical"] = [
        {"name": "surq_lag", "mode": "v", "filter": {"lu_mgt": "cosy_lum"}},
        {"name": "esco", "mode": "v"},
    ]
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    phys = expanded["parameters"]["physical"]
    # surq_lag is basin-scoped → OBJ_TOT=0 despite filter
    surq = [p for p in phys if p["name"] == "surq_lag"][0]
    skel = surq["file"]["_skel"]
    for line in skel.split("\n"):
        if line.startswith("surq_lag"):
            assert "       0" in line   # OBJ_TOT
            # no object tail digits after OBJ_TOT
            tokens = line.split()
            assert tokens[-1] == "0"

    # esco is HRU-scoped (no filter) → OBJ_TOT=0 (correct, no filter)
    esco = [p for p in phys if p["name"] == "esco"][0]
    assert esco.get("filter") is None


def test_filter_on_hru_param_resolves_normally(tmp_path: Path):
    """HRU-scoped parameter (esco from hydrology.hyd) with a filter
    correctly resolves to HRU IDs."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project, n_hrus=3)

    raw = _base_config(project, work)
    raw["parameters"]["physical"] = [
        {"name": "surq_lag", "mode": "v"},
        {"name": "esco", "mode": "v", "filter": {"lu_mgt": "cosy_lum"}},
    ]
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    phys = expanded["parameters"]["physical"]
    # surq_lag: basin, no filter → OBJ_TOT=0
    surq = [p for p in phys if p["name"] == "surq_lag"][0]
    skel = surq["file"]["_skel"]
    for line in skel.split("\n"):
        if line.startswith("surq_lag"):
            assert "       0" in line

    # esco: HRU, with filter → OBJ_TOT=2 (HRUs 1 and 3 are cosy_lum)
    esco = [p for p in phys if p["name"] == "esco"][0]
    skel = esco["file"]["_skel"]
    for line in skel.split("\n"):
        if line.startswith("esco"):
            assert "       2" in line   # OBJ_TOT
            assert "       1" in line   # HRU 1
            assert "       3" in line   # HRU 3


def test_validate_filter_unknown_field_errors(tmp_path: Path):
    project = tmp_path / "project"
    _write_swatplus_project(project)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "parameters": {
            "design": [{"name": "esco", "bounds": [0.1, 0.9]}],
            "physical": [{
                "name": "esco",
                "mode": "v",
                "filter": {"subbasin": 1},
            }],
        },
        "series": [],
    }
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert has_error(diagnostics)
    assert any("unknown filter field" in d.message for d in diagnostics)


def test_validate_rejects_filter_on_basin_param(tmp_path: Path):
    """Basin parameter (surq_lag from parameters.bsn) with filter must be rejected."""
    project = tmp_path / "project"
    _write_swatplus_project(project)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "parameters": {
            "design": [{"name": "surq_lag"}],
            "physical": [{
                "name": "surq_lag",
                "mode": "v",
                "filter": {"lu_mgt": "cosy_lum"},
            }],
        },
        "series": [],
    }
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert has_error(diagnostics)
    assert any("filter is only supported for per-HRU parameters" in d.message for d in diagnostics)


def test_validate_accepts_soil_filter_on_sol_param(tmp_path: Path):
    """Per-soil parameter (sol_bd from soils.sol) with soil filter passes.
    FORTRAN confirms ob_typ=sol uses sp_ob%hru — HRU IDs are the object space."""
    project = tmp_path / "project"
    _write_swatplus_project(project)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "parameters": {
            "design": [{"name": "sol_bd", "bounds": [0.9, 2.5]}],
            "physical": [{
                "name": "sol_bd",
                "mode": "v",
                "filter": {"soil": "soil_01"},
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {"file": "basin_wb_aa.txt", "variable": "WYLD", "id": 1, "period": [1977, 1980]},
        }],
    }
    (tmp_path / "obs.txt").write_text("1\n", encoding="ascii")
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert not has_error(diagnostics)


def test_validate_rejects_soil_filter_on_basin_param(tmp_path: Path):
    """Basin param with soil filter is still rejected."""
    project = tmp_path / "project"
    _write_swatplus_project(project)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "parameters": {
            "design": [{"name": "surq_lag"}],
            "physical": [{
                "name": "surq_lag",
                "mode": "v",
                "filter": {"soil": "soil_01"},
            }],
        },
        "series": [],
    }
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert has_error(diagnostics)
    assert any("does not support per-object filtering" in d.message for d in diagnostics)


def test_soil_filter_on_sol_param_resolves_hrus(tmp_path: Path):
    """soil=soil_01 on sol_bd → resolves to HRU 1 via hru_meta.soil exact match."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project, n_hrus=3)

    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": str(work), "command": "swatplus.exe"},
        "parameters": {
            "design": [{"name": "sol_bd", "bounds": [0.9, 2.5]}],
            "physical": [{
                "name": "sol_bd",
                "mode": "v",
                "filter": {"soil": "soil_01"},
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {"file": "basin_wb_aa.txt", "variable": "WYLD", "id": 1, "period": [1977, 1980]},
        }],
        "objectives": [{"id": "obj", "ref": "flow.sim", "sense": "max"}],
    }
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    entry = expanded["parameters"]["physical"][0]
    assert entry["file"]["name"] == "calibration.cal"

    skel = entry["file"]["_skel"]
    for line in skel.split("\n"):
        if line.startswith("sol_bd"):
            assert "       1" in line  # OBJ_TOT=1
            assert "       1" in line  # HRU 1


def test_validate_accepts_filter_on_hru_param(tmp_path: Path):
    """HRU parameter (esco from hydrology.hyd) with valid filter passes validation."""
    project = tmp_path / "project"
    _write_swatplus_project(project)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "parameters": {
            "design": [{"name": "esco", "bounds": [0.1, 0.9]}],
            "physical": [{
                "name": "esco",
                "mode": "v",
                "filter": {"lu_mgt": "cosy_lum"},
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {"file": "basin_wb_aa.txt", "variable": "WYLD", "id": 1, "period": [1977, 1980]},
        }],
    }
    (tmp_path / "obs.txt").write_text("1\n", encoding="ascii")
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert not has_error(diagnostics)


def test_validate_filter_valid_is_silent(tmp_path: Path):
    project = tmp_path / "project"
    _write_swatplus_project(project)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "parameters": {
            "design": [{"name": "esco", "bounds": [0.1, 0.9]}],
            "physical": [{
                "name": "esco",
                "mode": "v",
                "filter": {"lu_mgt": "cosy_lum"},
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {"file": "basin_wb_aa.txt", "variable": "WYLD", "id": 1, "period": [1977, 1980]},
        }],
    }
    (tmp_path / "obs.txt").write_text("1\n", encoding="ascii")
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert not has_error(diagnostics)


# ── skeleton ↔ physical entry consistency ──────────────────────────


def test_skeleton_row_count_matches_physical_entry_count(tmp_path: Path):
    """Skeleton has one record per resolved physical entry — not per design."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n", encoding="ascii")

    # 2 design params, 3 physical entries (esco appears twice, different modes)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": str(work), "command": "swatplus.exe"},
        "parameters": {
            "design": [
                {"name": "surq_lag"},
                {"name": "esco", "bounds": [0.1, 0.9]},
            ],
            "physical": [
                {"name": "surq_lag", "mode": "v"},
                {"name": "esco", "mode": "v"},
                {"name": "esco", "mode": "a"},  # duplicate target, different mode
            ],
        },
        "series": [{
            "id": "flow",
            "sim": {"file": "basin_wb_aa.txt", "variable": "WYLD", "id": 1, "period": [1977, 1980]},
        }],
        "objectives": [{"id": "obj", "ref": "flow.sim", "sense": "max"}],
    }
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    phys = expanded["parameters"]["physical"]
    assert len(phys) == 3  # 3 resolved physical entries

    # skeleton: check record count from the skeleton text
    skel = phys[0]["file"]["_skel"]
    skel_lines = [l for l in skel.split("\n") if l and "OBJ_TOT" not in l and l.strip().isdigit()]
    assert len(skel_lines) == 1  # the parameter count line
    assert int(skel_lines[0]) == 3  # matches physical entry count, not design count (2)


def test_skeleton_uses_resolved_mode_not_default(tmp_path: Path):
    """CHG_TYPE in skeleton reflects the resolved physical mode, not design default."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n", encoding="ascii")

    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": str(work), "command": "swatplus.exe"},
        "parameters": {
            "design": [{"name": "esco", "bounds": [0.1, 0.9]}],
            "physical": [{"name": "esco", "mode": "a"}],  # mode a → abschg
        },
        "series": [{
            "id": "flow",
            "sim": {"file": "basin_wb_aa.txt", "variable": "WYLD", "id": 1, "period": [1977, 1980]},
        }],
        "objectives": [{"id": "obj", "ref": "flow.sim", "sense": "max"}],
    }
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    phys = expanded["parameters"]["physical"]
    assert len(phys) == 1
    assert phys[0]["mode"] == "a"

    # skeleton record must contain "abschg" not "absval"
    skel = phys[0]["file"]["_skel"]
    # find the esco record line
    for line in skel.split("\n"):
        if line.startswith("esco"):
            assert "abschg" in line
            assert "absval" not in line


def test_skeleton_consistent_with_transformer(tmp_path: Path):
    """With a transformer, resolvedPhysical mirrors physical list directly —
    skeleton must match that count, not design count."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n", encoding="ascii")

    # 2 design items, but transformer is present → physical list drives
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": str(work), "command": "swatplus.exe"},
        "parameters": {
            "design": [
                {"name": "surq_lag"},
                {"name": "esco", "bounds": [0.1, 0.9]},
            ],
            "physical": [
                {"name": "esco", "mode": "r", "bounds": [-10, 10]},
            ],
            "transformer": "identity",
        },
        "series": [{
            "id": "flow",
            "sim": {"file": "basin_wb_aa.txt", "variable": "WYLD", "id": 1, "period": [1977, 1980]},
        }],
        "objectives": [{"id": "obj", "ref": "flow.sim", "sense": "max"}],
    }
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    phys = expanded["parameters"]["physical"]
    assert len(phys) == 1  # only 1 physical entry with transformer

    skel = phys[0]["file"]["_skel"]
    # skeleton must say 1 param, not 2
    for line in skel.split("\n"):
        stripped = line.strip()
        if stripped.isdigit():
            assert stripped == "1"
            break

    # and the record must match the physical entry (esco, mode r → pctchg)
    assert phys[0]["mode"] == "r"
    for line in skel.split("\n"):
        if line.startswith("esco"):
            assert "pctchg" in line


def test_prepare_config_rejects_basin_param_with_filter(tmp_path: Path):
    """Basin param (surq_lag) + filter must fail at prepare_config
    via the wired validate() call — not just direct validate_swatplus_config."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)

    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": str(work), "command": "swatplus.exe"},
        "parameters": {
            "design": [{"name": "surq_lag"}],
            "physical": [{"name": "surq_lag", "mode": "v", "filter": {"lu_mgt": "cosy_lum"}}],
        },
        "series": [],
    }
    cfg_path = tmp_path / "case.yaml"
    cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ConfigPreparationError, match="filter is only supported for per-HRU"):
        prepare_config(cfg_path)


def test_prepare_config_accepts_hru_param_with_filter(tmp_path: Path):
    """Valid HRU param (esco) + filter must pass prepare_config."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)

    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": str(work), "command": "swatplus.exe"},
        "parameters": {
            "design": [{"name": "esco", "bounds": [0.1, 0.9]}],
            "physical": [{"name": "esco", "mode": "v", "filter": {"lu_mgt": "cosy_lum"}}],
        },
        "series": [{
            "id": "out",
            "sim": {"file": "basin_wb_aa.txt", "variable": "WYLD", "id": 1, "period": [1977, 1980]},
        }],
    }
    (tmp_path / "obs.txt").write_text("1\n", encoding="ascii")
    cfg_path = tmp_path / "case.yaml"
    cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    prepared = prepare_config(cfg_path)
    assert prepared.config.version == "general"
    phys = prepared.config.parameters.physical
    assert len(phys) == 1
    assert phys[0].writerType == "formatted_text"


def test_prepare_config_chain_with_writer_and_reader_types(tmp_path: Path):
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n2\n3\n4\n", encoding="ascii")

    cfg_path = tmp_path / "case.yaml"
    cfg_path.write_text(yaml.safe_dump(_base_config(project, work), sort_keys=False), encoding="utf-8")

    prepared = prepare_config(cfg_path)
    assert prepared.version == "swatplus"
    assert prepared.config.version == "general"
    assert prepared.config.parameters.physical[0].writerType == "formatted_text"
    assert prepared.config.series[0].sim.readerType == "text"


def test_load_config_writes_general_yaml(tmp_path: Path):
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n2\n3\n4\n", encoding="ascii")

    cfg_path = tmp_path / "case.yaml"
    cfg_path.write_text(yaml.safe_dump(_base_config(project, work), sort_keys=False), encoding="utf-8")

    load_config(cfg_path)
    general_path = cfg_path.with_name("case_general.yaml")
    assert general_path.exists()
    general_text = general_path.read_text(encoding="utf-8")
    assert "version: general" in general_text
    assert "writerType: formatted_text" in general_text
    assert "readerType: text" in general_text


def test_skeleton_provided_file_does_not_require_project_existence(tmp_path: Path):
    """ParamWritePlan accepts _skel-bearing formatted_text entries even when
    the target file (calibration.cal) does not exist in the source project.
    It is created during instance initialization from the skeleton payload."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n2\n3\n4\n", encoding="ascii")

    cfg_path = tmp_path / "case.yaml"
    cfg_path.write_text(yaml.safe_dump(_base_config(project, work), sort_keys=False), encoding="utf-8")

    prepared = prepare_config(cfg_path)
    cfg = prepared.config

    # calibration.cal must NOT exist in the project
    assert not (project / "calibration.cal").exists()

    # ParamWritePlan construction must NOT raise FileNotFoundError
    plan = ParamWritePlan(cfg)

    # task should carry _skel and deferred pending registrations
    task = list(plan.write_tasks.values())[0]
    assert task["fileName"] == "calibration.cal"
    assert task["_skel"] is not None
    assert len(task["_pending_reg"]) == 2  # surq_lag + esco
    assert len(task["indices"]) == 2

    # initialize a mock instance — must create calibration.cal on disk
    instance = tmp_path / "instance_0"
    instance.mkdir()
    plan.initialize(str(instance))

    cal_path = instance / "calibration.cal"
    assert cal_path.exists()
    content = cal_path.read_text(encoding="utf-8")
    assert "Number of parameters:" in content
    assert "2" in content.split("\n")[1]  # parameter count
    assert "surq_lag" in content
    assert "esco" in content

    # handler should now have registered params (deferred replay succeeded)
    assert len(task["handler"].params) == 2
    assert task["handler"]._skeleton_lines  # skeleton loaded


def test_apply_design_writes_calibration_cal_skeleton(tmp_path: Path):
    """apply_design_params must initialize the calibration.cal skeleton in the
    output directory, not leave it empty.  Proves the apply path calls the
    initialization boundary."""
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n2\n3\n4\n", encoding="ascii")

    cfg_path = tmp_path / "case.yaml"
    cfg_path.write_text(yaml.safe_dump(_base_config(project, work), sort_keys=False), encoding="utf-8")
    cfg = load_config(cfg_path)

    out_dir = tmp_path / "applied"
    apply_design_params(cfg, {"surq_lag": 5.0, "esco": 0.75}, out_dir)

    cal_path = out_dir / "calibration.cal"
    assert cal_path.exists(), "calibration.cal must be created by apply init"
    content = cal_path.read_text(encoding="utf-8")
    assert "Number of parameters:" in content
    assert "surq_lag" in content
    assert "esco" in content


# ── channel object_id filter ────────────────────────────────────────

def _write_channel_lte_cha(project: Path, n_reaches: int = 5) -> None:
    """Write a minimal channel-lte.cha to the project."""
    lines = [
        "channel-lte.cha: test",
        "      id  name                       cha_ini           cha_hyd           cha_sed           cha_nut",
    ]
    for i in range(1, n_reaches + 1):
        lines.append(f"       {i}  cha{i:02d}                     initcha1          hydcha{i:02d}              null           nutcha1")
    (project / "channel-lte.cha").write_text("\n".join(lines), encoding="utf-8")

    # Also need hyd-sed-lte.cha for the param to exist (builder reads it for register_param)
    # Empty skeleton file is enough for template build test
    (project / "hyd-sed-lte.cha").write_text(
        "hyd-sed-lte.cha: test\n"
        "name order wd dp slp len mann k erod_fact cov_fact wd_rto eq_slp d50 clay carbon dry_bd side_slp bed_load fps fpn n_conc p_conc p_bio\n"
        + "\n".join(f"hydcha{i:02d} {i} 10.0 0.5 0.001 2.0 0.05 5.0 0.01 0.005 20.0 0.001 12.0 50.0 0.04 1.0 0.5 0.5 0.00001 0.1 0.0 0.0 0.0" for i in range(1, n_reaches + 1))
        + "\n", encoding="utf-8")


class TestChaObjectIdFilter:
    def test_cha_object_id_filter_produces_object_tail(self, tmp_path: Path):
        """ch_mann (hyd-sed-lte.cha) + object_id filter → OBJ_TOT > 0 in skeleton."""
        project = tmp_path / "project"
        work = tmp_path / "work"
        _write_swatplus_project(project)
        _write_channel_lte_cha(project, n_reaches=5)
        (tmp_path / "obs.txt").write_text("1\n", encoding="ascii")

        raw = {
            "version": "swatplus",
            "basic": {"projectPath": str(project), "workPath": str(work), "command": "swatplus.exe"},
            "parameters": {
                "design": [
                    {"name": "ch_mann"},
                ],
                "physical": [
                    {"name": "ch_mann", "mode": "v", "filter": {"object_id": [2, 4]}},
                ],
            },
            "series": [],
        }
        cfg_path = tmp_path / "case.yaml"
        cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

        expanded = SwatPlusTemplate().build_config(raw, tmp_path)
        phys = expanded["parameters"]["physical"]
        assert len(phys) == 1
        entry = phys[0]

        skel = entry["file"]["_skel"]
        for line in skel.split("\n"):
            if line.startswith("ch_mann"):
                # OBJ_TOT=2, object IDs 2 and 4 in tail
                assert "       2" in line  # OBJ_TOT
                assert "       4" in line  # reach 4
                assert "       2" in line  # reach 2

    def test_cha_object_id_single_value(self, tmp_path: Path):
        """Single object_id scalar (not list) works."""
        project = tmp_path / "project"
        work = tmp_path / "work"
        _write_swatplus_project(project)
        _write_channel_lte_cha(project, n_reaches=3)
        (tmp_path / "obs.txt").write_text("1\n", encoding="ascii")

        raw = {
            "version": "swatplus",
            "basic": {"projectPath": str(project), "workPath": str(work), "command": "swatplus.exe"},
            "parameters": {
                "design": [{"name": "ch_erod"}],
                "physical": [{"name": "ch_erod", "mode": "a", "filter": {"object_id": 1}}],
            },
            "series": [],
        }
        cfg_path = tmp_path / "case.yaml"
        cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

        expanded = SwatPlusTemplate().build_config(raw, tmp_path)
        entry = expanded["parameters"]["physical"][0]
        skel = entry["file"]["_skel"]
        for line in skel.split("\n"):
            if line.startswith("ch_erod"):
                assert "       1" in line  # OBJ_TOT
                assert "       1" in line  # reach 1

    def test_cha_non_object_id_filter_rejected(self, tmp_path: Path):
        """lu_mgt filter on cha param → rejected by validation."""
        project = tmp_path / "project"
        work = tmp_path / "work"
        _write_swatplus_project(project)
        _write_channel_lte_cha(project)
        (tmp_path / "obs.txt").write_text("1\n", encoding="ascii")

        raw = {
            "version": "swatplus",
            "basic": {"projectPath": str(project), "workPath": str(work), "command": "swatplus.exe"},
            "parameters": {
                "design": [{"name": "ch_mann"}],
                "physical": [{"name": "ch_mann", "mode": "v", "filter": {"lu_mgt": "cosy_lum"}}],
            },
            "series": [],
        }
        from hydropilot.models.swatplus.validate import validate_swatplus_config
        diags = validate_swatplus_config(raw, tmp_path)
        errors = [d for d in diags if d.level == "error"]
        assert any("channel parameters only support 'object_id'" in d.message for d in errors)

    def test_cha_out_of_range_id_rejected(self, tmp_path: Path):
        """object_id > n_reaches → ValueError at build time."""
        project = tmp_path / "project"
        work = tmp_path / "work"
        _write_swatplus_project(project)
        _write_channel_lte_cha(project, n_reaches=3)
        (tmp_path / "obs.txt").write_text("1\n", encoding="ascii")

        raw = {
            "version": "swatplus",
            "basic": {"projectPath": str(project), "workPath": str(work), "command": "swatplus.exe"},
            "parameters": {
                "design": [{"name": "ch_mann"}],
                "physical": [{"name": "ch_mann", "mode": "v", "filter": {"object_id": [1, 99]}}],
            },
            "series": [],
        }
        with pytest.raises(ValueError, match="object_id 99 is out of range"):
            SwatPlusTemplate().build_config(raw, tmp_path)

    def test_discovery_extracts_reach_count(self, tmp_path: Path):
        """discover() must parse channel-lte.cha and return n_reaches."""
        project = tmp_path / "project"
        _write_swatplus_project(project)
        _write_channel_lte_cha(project, n_reaches=7)
        from hydropilot.models.swatplus.discovery import discover_swatplus_project
        meta = discover_swatplus_project(project)
        assert meta["n_reaches"] == 7


# ── soil profile mapping ──────────────────────────────────────────


class TestSoilProfileMapping:
    def test_discovery_extracts_soil_profiles(self, tmp_path: Path):
        project = tmp_path / "project"
        _write_swatplus_project(project, n_hrus=3)
        from hydropilot.models.swatplus.discovery import discover_swatplus_project
        meta = discover_swatplus_project(project)
        assert meta["n_soils"] == 5  # soil_01,02,03 + soil_01-h1, soil_03-h3
        assert meta["soil_profiles"][1]["name"] == "soil_01"
        assert meta["soil_profiles"][1]["nly"] == 4
        assert meta["soil_profiles"][1]["hyd_grp"] == "B"

    def test_soil_profile_map_direct_match(self, tmp_path: Path):
        """HRU 2 has soil=soil_02 → maps to profile index 2."""
        project = tmp_path / "project"
        _write_swatplus_project(project, n_hrus=3)
        from hydropilot.models.swatplus.discovery import discover_swatplus_project
        meta = discover_swatplus_project(project)
        # HRU 2 has soil_02 → profile index 2
        assert meta["soil_profile_map"][2] == 2

    def test_soil_profile_map_hydro_suffix(self, tmp_path: Path):
        """HRU 1 has soil=soil_01 → maps to profile index 1.
        HRU 3 has soil=soil_03 → maps to profile index 3.
        Note: the test fixture uses soil_{i:02d} for HRU i.
        The hydro variants soil_01-h1 and soil_03-h3 should also map.
        """
        project = tmp_path / "project"
        _write_swatplus_project(project, n_hrus=3)
        from hydropilot.models.swatplus.discovery import discover_swatplus_project
        meta = discover_swatplus_project(project)
        assert meta["soil_profile_map"][1] == 1  # soil_01 → profile 1
        assert meta["soil_profile_map"][3] == 3  # soil_03 → profile 3

    def test_soil_profile_map_hydro_variant_exact_match(self, tmp_path: Path):
        """HRU soil=soil_01-h1 → exact match to profile 4 (separate entry in soils.sol)."""
        project = tmp_path / "project"
        _write_swatplus_project(project, n_hrus=3)
        # Override HRU 2 to use soil_01-h1
        hru_path = project / "hru-data.hru"
        lines = hru_path.read_text(encoding="utf-8").split("\n")
        fixed = []
        for line in lines:
            if line.strip().startswith("2 ") and "soil_02" in line:
                line = line.replace("soil_02", "soil_01-h1")
            fixed.append(line)
        hru_path.write_text("\n".join(fixed), encoding="utf-8")

        from hydropilot.models.swatplus.discovery import discover_swatplus_project
        meta = discover_swatplus_project(project)
        # soil_01-h1 EXISTS as separate profile (index 4 in fixture)
        assert meta["soil_profile_map"][2] == 4

    def test_soil_profile_map_hydro_suffix_falls_back_to_base(self, tmp_path: Path):
        """HRU soil=soil_01-h99 → no exact match, strip -h99 → match soil_01 (profile 1)."""
        project = tmp_path / "project"
        _write_swatplus_project(project, n_hrus=3)
        # Override HRU 2 to use a hydro-variant that does NOT exist in soils.sol
        hru_path = project / "hru-data.hru"
        lines = hru_path.read_text(encoding="utf-8").split("\n")
        fixed = []
        for line in lines:
            if line.strip().startswith("2 ") and "soil_02" in line:
                line = line.replace("soil_02", "soil_01-h99")
            fixed.append(line)
        hru_path.write_text("\n".join(fixed), encoding="utf-8")

        from hydropilot.models.swatplus.discovery import discover_swatplus_project
        meta = discover_swatplus_project(project)
        # soil_01-h99 does NOT exist → strip -h99 → match soil_01 (profile 1)
        assert meta["soil_profile_map"][2] == 1

    def test_soil_profile_map_omits_unmatched(self, tmp_path: Path):
        """HRU with unknown soil name → omitted from map."""
        project = tmp_path / "project"
        _write_swatplus_project(project, n_hrus=3)
        hru_path = project / "hru-data.hru"
        lines = hru_path.read_text(encoding="utf-8").split("\n")
        fixed = []
        for line in lines:
            if line.strip().startswith("2 ") and "soil_02" in line:
                line = line.replace("soil_02", "nonexistent_soil")
            fixed.append(line)
        hru_path.write_text("\n".join(fixed), encoding="utf-8")

        from hydropilot.models.swatplus.discovery import discover_swatplus_project
        meta = discover_swatplus_project(project)
        assert 2 not in meta["soil_profile_map"]  # HRU 2 unmapped

    def test_no_soils_sol_returns_empty_map(self, tmp_path: Path):
        """Project without soils.sol → n_soils=0, empty map."""
        project = tmp_path / "project"
        project.mkdir()
        # Write only required files, no soils.sol
        (project / "file.cio").write_text(
            "file.cio:\nsimulation        time.sim          print.prt\n"
            "basin             codes.bsn         parameters.bsn\n"
            "hru               hru-data.hru      null\n"
            "hydrology         hydrology.hyd     topography.hyd\n", encoding="utf-8")
        (project / "time.sim").write_text("time.sim\n       0      1975         0      1980         0\n")
        (project / "print.prt").write_text("print.prt\n   0           0         1975         0      1980         1\n")
        (project / "hru-data.hru").write_text(
            "hru-data.hru\n      id  name  topo  hydro  soil  lu_mgt\n"
            "       1  hru1  topo1  hyd1  soil_01  cosy_lum\n", encoding="utf-8")

        from hydropilot.models.swatplus.discovery import discover_swatplus_project
        meta = discover_swatplus_project(project)
        assert meta["n_soils"] == 0
        assert meta["soil_profile_map"] == {}


def test_expanded_io_types_in_registry(tmp_path: Path):
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n2\n3\n4\n", encoding="ascii")

    raw = _base_config(project, work)
    expanded = SwatPlusTemplate().build_config(raw, tmp_path)

    for phys in expanded["parameters"]["physical"]:
        assert getWriter(phys["writerType"]) is not None
    for series in expanded["series"]:
        assert getReader(series["sim"]["readerType"]) is not None
        if series.get("obs"):
            assert getReader(series["obs"].get("readerType", "text")) is not None


# ── validation rejection tests ───────────────────────────────────


def test_validate_rejects_missing_project_dir(tmp_path: Path):
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(tmp_path / "nonexistent"), "workPath": "./work", "command": "swatplus.exe"},
        "series": [],
    }
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert has_error(diagnostics)
    assert any("not found" in d.message for d in diagnostics)


def test_validate_rejects_missing_required_files(tmp_path: Path):
    project = tmp_path / "bare"
    project.mkdir()
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "series": [],
    }
    diagnostics = validate_swatplus_config(raw, tmp_path)
    errors = [d for d in diagnostics if d.level == "error"]
    assert len(errors) >= 1


def test_validate_rejects_unknown_parameter(tmp_path: Path):
    project = tmp_path / "project"
    _write_swatplus_project(project)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "parameters": {"design": [{"name": "UNKNOWN_PARAM", "bounds": [0, 1]}]},
        "series": [],
    }
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert has_error(diagnostics)
    assert any("unknown SWAT+ parameter" in d.message for d in diagnostics)


def test_validate_rejects_unknown_variable(tmp_path: Path):
    project = tmp_path / "project"
    _write_swatplus_project(project)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "series": [{
            "id": "flow",
            "sim": {"file": "basin_wb_aa.txt", "variable": "UNKNOWN_VAR", "id": 1, "period": [2019, 2021]},
        }],
    }
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert has_error(diagnostics)
    assert any("unknown SWAT+ output variable" in d.message for d in diagnostics)


def test_validate_rejects_missing_variable_and_column(tmp_path: Path):
    project = tmp_path / "project"
    _write_swatplus_project(project)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "series": [{
            "id": "flow",
            "sim": {"file": "basin_wb_aa.txt", "id": 1, "period": [2019, 2021]},
        }],
    }
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert has_error(diagnostics)
    assert any("missing column specification" in d.message for d in diagnostics)


def test_validate_rejects_unknown_output_file(tmp_path: Path):
    project = tmp_path / "project"
    _write_swatplus_project(project)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "series": [{
            "id": "flow",
            "sim": {"file": "output.rch", "variable": "wateryld", "id": 1, "period": [2019, 2021]},
        }],
    }
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert has_error(diagnostics)
    assert any("not in the known series database" in d.message for d in diagnostics)


def test_validate_rejects_missing_row_selection(tmp_path: Path):
    project = tmp_path / "project"
    _write_swatplus_project(project)
    raw = {
        "version": "swatplus",
        "basic": {"projectPath": str(project), "workPath": "./work", "command": "swatplus.exe"},
        "series": [{
            "id": "flow",
            "sim": {"file": "basin_wb_aa.txt", "variable": "WYLD"},
        }],
    }
    diagnostics = validate_swatplus_config(raw, tmp_path)
    assert has_error(diagnostics)
    assert any("missing row selection" in d.message for d in diagnostics)


# ── _detectFrequency ─────────────────────────────────────────────


@pytest.mark.parametrize("filename,expected", [
    ("channel_aa.txt", "aa"),
    ("basin_wb_yr.txt", "yr"),
    ("hydout_mon.txt", "mo"),
    ("hydout_day.txt", "da"),
    ("basin_wb_aa.txt", "aa"),
    ("channel_yr.txt", "yr"),
    ("hru_wb_mon.txt", "mo"),
    ("hru_wb_day.txt", "da"),
])
def test_detect_frequency_real_swatplus_suffixes(filename, expected):
    assert _detectFrequency(filename) == expected


@pytest.mark.parametrize("filename,expected", [
    ("output_mo.txt", "mo"),
    ("output_da.txt", "da"),
    ("hru_wb_mo.txt", "mo"),
    ("hru_wb_da.txt", "da"),
])
def test_detect_frequency_legacy_suffixes(filename, expected):
    assert _detectFrequency(filename) == expected


def test_detect_frequency_unknown_returns_aa():
    assert _detectFrequency("unknown.txt") == "aa"
    assert _detectFrequency("output.rch") == "aa"
    assert _detectFrequency("basin_wb_weekly.txt") == "aa"


def test_detect_frequency_mon_not_misinterpreted_as_mo():
    # _mon.txt should NOT be caught by the _mo.txt check
    assert _detectFrequency("channel_mon.txt") == "mo"
    # _mo.txt should still work independently
    assert _detectFrequency("legacy_mo.txt") == "mo"


# ── end-to-end config chain ──────────────────────────────────────


def test_validate_config_passes_for_valid_swatplus(tmp_path: Path):
    project = tmp_path / "project"
    work = tmp_path / "work"
    _write_swatplus_project(project)
    (tmp_path / "obs.txt").write_text("1\n2\n3\n4\n", encoding="ascii")

    cfg_path = tmp_path / "case.yaml"
    cfg_path.write_text(yaml.safe_dump(_base_config(project, work), sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(cfg_path)
    errors = [d for d in diagnostics if d.level == "error"]
    assert errors == []
