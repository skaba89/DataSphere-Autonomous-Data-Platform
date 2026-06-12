"""Execute terraform init + plan in a temp directory and capture output."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def terraform_plan(files: dict[str, str], working_dir: Optional[str] = None) -> dict:
    """
    Write Terraform files to a temp dir, run terraform init + plan.
    Returns {
        "success": bool,
        "plan_output": str,      # stdout from terraform plan
        "init_output": str,      # stdout from terraform init
        "error": str | None,
        "terraform_available": bool,
        "working_dir": str,
    }
    """
    terraform_bin = shutil.which("terraform")
    if not terraform_bin:
        return {
            "success": False,
            "plan_output": "",
            "init_output": "",
            "error": "terraform binary not found in PATH — install Terraform to use dry-run",
            "terraform_available": False,
            "working_dir": "",
        }

    tmp = tempfile.mkdtemp(prefix="datasphere_tf_")
    try:
        # Write files
        for filename, content in files.items():
            fpath = Path(tmp) / filename
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)

        # terraform init
        init_result = subprocess.run(
            [terraform_bin, "init", "-input=false", "-no-color"],
            cwd=tmp, capture_output=True, text=True, timeout=120
        )

        # terraform plan
        plan_result = subprocess.run(
            [terraform_bin, "plan", "-input=false", "-no-color", "-compact-warnings"],
            cwd=tmp, capture_output=True, text=True, timeout=300
        )

        return {
            "success": plan_result.returncode == 0,
            "plan_output": plan_result.stdout + plan_result.stderr,
            "init_output": init_result.stdout,
            "error": plan_result.stderr if plan_result.returncode != 0 else None,
            "terraform_available": True,
            "working_dir": tmp,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "plan_output": "",
            "init_output": "",
            "error": "timeout",
            "terraform_available": True,
            "working_dir": tmp,
        }
    except Exception as e:
        return {
            "success": False,
            "plan_output": "",
            "init_output": "",
            "error": str(e),
            "terraform_available": True,
            "working_dir": tmp,
        }
    finally:
        if working_dir is None:
            shutil.rmtree(tmp, ignore_errors=True)
