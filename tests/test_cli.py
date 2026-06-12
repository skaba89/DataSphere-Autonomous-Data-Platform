"""
Tests for datasphere.cli.main — non-interactive argparse commands and REPL methods.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_main(argv: list[str], input_lines: list[str] | None = None):
    """Run main() with given argv, capture stdout, return (stdout, exit_code)."""
    from datasphere.cli.main import main

    buf = io.StringIO()
    exit_code = 0

    stdin_patch = None
    if input_lines is not None:
        stdin_patch = "\n".join(input_lines) + "\n"

    with patch("datasphere.cli.main._print", side_effect=lambda msg="": buf.write(str(msg) + "\n")):
        if stdin_patch is not None:
            with patch("datasphere.cli.main._input", side_effect=input_lines):
                try:
                    main(argv)
                except SystemExit as exc:
                    exit_code = exc.code or 0
        else:
            try:
                main(argv)
            except SystemExit as exc:
                exit_code = exc.code or 0

    return buf.getvalue(), exit_code


# ---------------------------------------------------------------------------
# 1. test_version_command
# ---------------------------------------------------------------------------

def test_version_command():
    out, code = _run_main(["version"])
    assert "1.2.0" in out
    assert code == 0


# ---------------------------------------------------------------------------
# 2. test_templates_command_no_args
# ---------------------------------------------------------------------------

def test_templates_command_no_args():
    out, code = _run_main(["templates"])
    assert code == 0
    assert "startup-analytics" in out
    assert "modern-data-stack-aws" in out
    assert "Cost/mo" in out or "$" in out


# ---------------------------------------------------------------------------
# 3. test_templates_command_with_id
# ---------------------------------------------------------------------------

def test_templates_command_with_id():
    out, code = _run_main(["templates", "startup-analytics"])
    assert code == 0
    assert "Startup Analytics" in out
    assert "postgresql" in out.lower() or "startup" in out.lower()


# ---------------------------------------------------------------------------
# 4. test_templates_command_filter_category
# ---------------------------------------------------------------------------

def test_templates_command_filter_category():
    out, code = _run_main(["templates", "--category", "startup"])
    assert code == 0
    assert "startup-analytics" in out or "open-source-stack" in out


# ---------------------------------------------------------------------------
# 5. test_diff_command_from_files
# ---------------------------------------------------------------------------

def test_diff_command_from_files(tmp_path):
    from_stack = {"data_warehouse": "redshift", "orchestrator": "airflow"}
    to_stack = {"data_warehouse": "snowflake", "orchestrator": "dagster"}

    from_file = tmp_path / "from.json"
    to_file = tmp_path / "to.json"
    from_file.write_text(json.dumps(from_stack))
    to_file.write_text(json.dumps(to_stack))

    out, code = _run_main(["diff", "--from-file", str(from_file), "--to-file", str(to_file)])
    assert code == 0
    assert "Migration plan" in out
    assert "redshift" in out.lower()
    assert "snowflake" in out.lower()
    assert "days" in out.lower()


# ---------------------------------------------------------------------------
# 6. test_status_command_server_down
# ---------------------------------------------------------------------------

def test_status_command_server_down():
    # Server is not running — should not raise, just print error message
    out, code = _run_main(["status", "--server", "http://localhost:19999"])
    assert code == 0  # graceful failure — no sys.exit
    assert "19999" in out or "unreachable" in out.lower() or "Status" in out


# ---------------------------------------------------------------------------
# 7. test_generate_command_with_args
# ---------------------------------------------------------------------------

def test_generate_command_with_args():
    mock_result = {
        "stack_summary": "snowflake + airflow + dbt + metabase",
        "estimated_monthly_usd": 1250,
        "warnings": ["test warning"],
    }

    with patch("datasphere.cli.main._run_generate_local", return_value=mock_result) as mock_gen:
        out, code = _run_main([
            "generate", "Pipeline analytics e-commerce",
            "--cloud", "aws",
            "--warehouse", "snowflake",
            "--orchestrator", "airflow",
            "--budget", "medium",
        ])

    assert code == 0
    assert "snowflake" in out
    assert "1,250" in out or "1250" in out
    mock_gen.assert_called_once()


# ---------------------------------------------------------------------------
# 8. test_generate_command_saves_output_file
# ---------------------------------------------------------------------------

def test_generate_command_saves_output_file(tmp_path):
    mock_result = {
        "stack_summary": "snowflake + airflow + dbt + metabase",
        "estimated_monthly_usd": 1250,
        "warnings": [],
    }
    output_file = str(tmp_path / "result.json")

    with patch("datasphere.cli.main._run_generate_local", return_value=mock_result):
        out, code = _run_main([
            "generate", "Pipeline e-commerce",
            "--output", output_file,
        ])

    assert code == 0
    assert os.path.exists(output_file)
    with open(output_file) as fh:
        saved = json.load(fh)
    assert saved["estimated_monthly_usd"] == 1250


# ---------------------------------------------------------------------------
# 9. test_repl_version_command
# ---------------------------------------------------------------------------

def test_repl_version_command():
    from datasphere.cli.main import DataSphereCLI

    buf = io.StringIO()
    with patch("datasphere.cli.main._print", side_effect=lambda msg="": buf.write(str(msg) + "\n")):
        cli = DataSphereCLI()
        cli.do_version("")

    assert "1.2.0" in buf.getvalue()


# ---------------------------------------------------------------------------
# 10. test_repl_templates_command
# ---------------------------------------------------------------------------

def test_repl_templates_command():
    from datasphere.cli.main import DataSphereCLI

    buf = io.StringIO()
    with patch("datasphere.cli.main._print", side_effect=lambda msg="": buf.write(str(msg) + "\n")):
        cli = DataSphereCLI()
        cli.do_templates("")  # list all

    out = buf.getvalue()
    assert "startup-analytics" in out
    assert "modern-data-stack-aws" in out


# ---------------------------------------------------------------------------
# 11. test_repl_diff_basic
# ---------------------------------------------------------------------------

def test_repl_diff_basic():
    from datasphere.cli.main import DataSphereCLI

    buf = io.StringIO()
    inputs = iter(["redshift", "airflow", "snowflake", "dagster"])

    with patch("datasphere.cli.main._print", side_effect=lambda msg="": buf.write(str(msg) + "\n")):
        with patch("datasphere.cli.main._input", side_effect=inputs):
            cli = DataSphereCLI()
            cli.do_diff("")

    out = buf.getvalue()
    assert "Migration plan" in out
    assert "days" in out.lower()


# ---------------------------------------------------------------------------
# 12. test_serve_command_checks_uvicorn
# ---------------------------------------------------------------------------

def test_serve_command_checks_uvicorn():
    """serve command prints helpful message when uvicorn is not installed."""
    buf = io.StringIO()

    with patch("datasphere.cli.main._print", side_effect=lambda msg="": buf.write(str(msg) + "\n")):
        # Simulate uvicorn not available by patching the import
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "uvicorn":
                raise ImportError("No module named 'uvicorn'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(SystemExit):
                from datasphere.cli.main import _start_server
                _start_server(host="0.0.0.0", port=8000, reload=False, workers=1)

    out = buf.getvalue()
    assert "uvicorn" in out.lower() or "install" in out.lower()
