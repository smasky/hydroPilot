from dataclasses import dataclass
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydropilot.io.writers.formatted_text import (
    FormattedTextWriter,
    FormattedTextWriterSpec,
    FormattedTextFileSpec,
)


@dataclass
class _FakeParamSpec:
    name: str
    index: int
    modeCode: int


def _ps(name="alpha", index=1, modeCode=1) -> _FakeParamSpec:
    return _FakeParamSpec(name=name, index=index, modeCode=modeCode)


def _make_spec(
    name="alpha",
    row=2,
    col=7,
    width=5,
    precision=3,
    typ="float",
    bounds=None,
) -> FormattedTextWriterSpec:
    if bounds is None:
        bounds = [0, 10]
    return FormattedTextWriterSpec(
        name=name,
        type={"float": 0, "int": 1}.get(typ, 0),
        bounds=bounds,
        file=FormattedTextFileSpec(
            name="test.txt",
            row=row,
            col=col,
            width=width,
            precision=precision,
        ),
    )


class TestFormattedTextWriterInit:
    """Phase 1 – static skeleton initialization."""

    def test_constructor_is_lightweight(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("content\n", encoding="utf-8")
        writer = FormattedTextWriter(str(f))
        assert writer._skeleton_lines == []
        assert writer.params == {}

    def test_initialize_loads_skeleton(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("row01\nvalue 1.234\nrow03\n", encoding="utf-8")
        writer = FormattedTextWriter(str(f))
        writer.initialize(str(f))
        assert len(writer._skeleton_lines) == 3

    def test_register_param_parses_original_value_from_skeleton(self, tmp_path: Path):
        # "value 1.234" — value starts at col 7, width 5
        f = tmp_path / "test.txt"
        f.write_text("row01\nvalue 1.234\nrow03\n", encoding="utf-8")
        writer = FormattedTextWriter(str(f))
        writer.register_param(_ps(name="alpha", index=1), _make_spec())

        assert 1 in writer.params
        p = writer.params[1]
        assert p.name == "alpha"
        assert p.entries[0].original_val == pytest.approx(1.234)
        assert p.entries[0].row == 2
        assert p.entries[0].col == 7

    def test_initialize_reloads_skeleton_lines_for_instance(self, tmp_path: Path):
        # Project file has "value 1.234" on row 2, instance has "value 2.000"
        project = tmp_path / "project.txt"
        project.write_text("row01\nvalue 1.234\nrow03\n", encoding="utf-8")
        writer = FormattedTextWriter(str(project))
        writer.register_param(_ps(name="v", index=0), _make_spec())

        instance = tmp_path / "instance.txt"
        instance.write_text("row01\nvalue 2.000\nrow03\n", encoding="utf-8")
        writer.initialize(str(instance))

        # Skeleton lines now reflect the instance file
        assert "2.000" in writer._skeleton_lines[1]
        # original_val stays from project file (that's correct — it's the reference)
        assert writer.params[0].entries[0].original_val == pytest.approx(1.234)

        # Apply against the instance skeleton
        out = tmp_path / "out.txt"
        writer.set_values_and_save(str(out), indices=[0], vals=[3.5])
        content = out.read_text(encoding="utf-8")
        assert "value 3.500" in content

    def test_register_param_rejects_out_of_range_row(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("only one row\n", encoding="utf-8")
        writer = FormattedTextWriter(str(f))
        with pytest.raises(ValueError, match="out of range"):
            writer.register_param(_ps(), _make_spec(row=99))


class TestFormattedTextWriterApply:
    """Phase 2 – dynamic value backfill."""

    def test_set_values_and_save_backfills_values(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("row01\nvalue 1.234\nrow03\n", encoding="utf-8")
        writer = FormattedTextWriter(str(f))
        writer.register_param(_ps(name="alpha", index=1), _make_spec())

        out = tmp_path / "out.txt"
        result = writer.set_values_and_save(str(out), indices=[1], vals=[5.678])

        assert result["write_records"][0]["new_value"] == pytest.approx(5.678)
        assert result["write_records"][0]["old_value"] == pytest.approx(1.234)
        content = out.read_text(encoding="utf-8")
        assert "value 5.678" in content

    def test_apply_preserves_unchanged_content(self, tmp_path: Path):
        original = "row01\ncolA 0.500  colB 1.234\nrow03\n"
        f = tmp_path / "test.txt"
        f.write_text(original, encoding="utf-8")

        writer = FormattedTextWriter(str(f))
        # "colA 0.500" — 0.500 at col 6, width 5
        spec_a = _make_spec(name="colA", row=2, col=6, width=5, precision=3)
        writer.register_param(_ps(name="colA", index=0), spec_a)

        out = tmp_path / "out.txt"
        writer.set_values_and_save(str(out), indices=[0], vals=[9.999])

        content = out.read_text(encoding="utf-8")
        assert "row01\n" in content
        assert "row03\n" in content

    def test_apply_after_initialize_writes_to_instance_skeleton(self, tmp_path: Path):
        project = tmp_path / "project.txt"
        project.write_text("row01\nvalue 1.000\nrow03\n", encoding="utf-8")
        instance = tmp_path / "instance.txt"
        instance.write_text("row01\nvalue 2.000\nrow03\n", encoding="utf-8")

        writer = FormattedTextWriter(str(project))
        writer.register_param(_ps(name="v", index=0), _make_spec())
        writer.initialize(str(instance))

        out = tmp_path / "out.txt"
        result = writer.set_values_and_save(str(out), indices=[0], vals=[3.5])

        # original_val is from the project (1.0), new_value is what we wrote
        assert result["write_records"][0]["old_value"] == pytest.approx(1.000)
        assert result["write_records"][0]["new_value"] == pytest.approx(3.5)
        # Output content was built from the instance skeleton
        content = out.read_text(encoding="utf-8")
        assert "value 3.500" in content


class TestFormattedTextWriterSpec:
    def test_buildSpec_from_raw(self):
        raw = {
            "name": "beta",
            "type": "float",
            "bounds": [0, 1],
            "file": {
                "name": "config.txt",
                "row": 5,
                "col": 21,
                "width": 8,
                "precision": 2,
            },
        }
        spec = FormattedTextWriter.buildSpec(raw)
        assert spec.name == "beta"
        assert spec.type == 0
        assert spec.file.name == "config.txt"
        assert spec.file.row == 5
        assert spec.file.col == 21
        assert spec.file.width == 8
        assert spec.file.precision == 2

    def test_buildSpec_rejects_invalid_inputs(self):
        with pytest.raises(ValueError, match="missing formatted_text field 'row'"):
            FormattedTextWriter.buildSpec(
                {"name": "x", "file": {"name": "f", "col": 1, "width": 5, "precision": 2}}
            )
        with pytest.raises(ValueError, match="row must be a positive"):
            FormattedTextWriter.buildSpec(
                {"name": "x", "file": {"name": "f", "row": 0, "col": 1, "width": 5, "precision": 2}}
            )
        with pytest.raises(ValueError, match="col must be a positive"):
            FormattedTextWriter.buildSpec(
                {"name": "x", "file": {"name": "f", "row": 1, "col": -1, "width": 5, "precision": 2}}
            )


class TestFormattedTextWriterRegistry:
    def test_registered_in_writer_registry(self):
        from hydropilot.io.writers import getWriter

        cls = getWriter("formatted_text")
        assert cls is FormattedTextWriter
