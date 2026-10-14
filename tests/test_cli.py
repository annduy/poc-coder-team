"""End-to-end tests for the skuv CLI (grows through M1-M4)."""

import os
import subprocess
import sys
from pathlib import Path

from skuv.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

SIMPLE_CSV = "ean,description,price\n5901234123457,Tau vuong Thom Binh,120000\n"


def write_csv(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "list.csv"
    path.write_text(text, encoding="utf-8")
    return path


def run_module(args, cwd):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run(
        [sys.executable, "-m", "skuv", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def test_help_exits_zero(capsys):
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("--help must exit via SystemExit")
    assert "INPUTFILE" in capsys.readouterr().out


def test_no_args_exits_two(capsys):
    try:
        main([])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("usage error must exit via SystemExit")
    assert "usage" in capsys.readouterr().err.lower()


def test_missing_input_exits_two(tmp_path):
    code = main([str(tmp_path / "nope.csv"), "-o", str(tmp_path / "out")])
    assert code == 2


def test_stub_run_on_readable_csv_exits_zero(tmp_path):
    source = write_csv(tmp_path, SIMPLE_CSV)
    assert main([str(source), "-o", str(tmp_path / "out")]) == 0


def test_module_entry_point_runs(tmp_path):
    source = write_csv(tmp_path, SIMPLE_CSV)
    proc = run_module([str(source), "-o", str(tmp_path / "out")], tmp_path)
    assert proc.returncode == 0, proc.stderr


INVALID_CSV = "ean,description,price\n5901234123458,Sua tam,99000\n"
MISSING_COLUMN_CSV = "ean,price\n5901234123457,120000\n"


def test_any_invalid_row_exits_one(tmp_path):
    source = write_csv(tmp_path, INVALID_CSV)
    assert main([str(source), "-o", str(tmp_path / "out")]) == 1


def test_missing_required_column_exits_two(tmp_path, capsys):
    source = write_csv(tmp_path, MISSING_COLUMN_CSV)
    assert main([str(source), "-o", str(tmp_path / "out")]) == 2
    assert "description" in capsys.readouterr().err


def test_all_valid_rows_exit_zero(tmp_path):
    source = write_csv(tmp_path, SIMPLE_CSV)
    assert main([str(source), "-o", str(tmp_path / "out")]) == 0
