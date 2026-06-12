"""Tests for POST /terraform/plan endpoint and terraform_runner module."""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Unit tests for terraform_runner.terraform_plan()
# ---------------------------------------------------------------------------

def test_terraform_plan_no_binary():
    """When terraform is not in PATH, returns terraform_available=False."""
    from datasphere.api.terraform_runner import terraform_plan
    with patch("shutil.which", return_value=None):
        result = terraform_plan({"main.tf": 'resource "null_resource" "x" {}'})
    assert result["terraform_available"] is False
    assert result["success"] is False
    assert "not found" in result["error"]
    assert result["plan_output"] == ""
    assert result["init_output"] == ""


def test_terraform_plan_empty_files_no_binary():
    """With empty files dict and no terraform binary, returns expected shape."""
    from datasphere.api.terraform_runner import terraform_plan
    with patch("shutil.which", return_value=None):
        result = terraform_plan({})
    assert isinstance(result["success"], bool)
    assert isinstance(result["terraform_available"], bool)
    assert "plan_output" in result
    assert "init_output" in result
    assert "error" in result
    assert "working_dir" in result


def test_terraform_plan_success_mock():
    """Mock a successful terraform init + plan run."""
    from datasphere.api.terraform_runner import terraform_plan

    mock_init = MagicMock()
    mock_init.stdout = "Terraform initialized successfully.\n"
    mock_init.stderr = ""
    mock_init.returncode = 0

    mock_plan = MagicMock()
    mock_plan.stdout = "Plan: 3 to add, 0 to change, 0 to destroy.\n"
    mock_plan.stderr = ""
    mock_plan.returncode = 0

    with patch("shutil.which", return_value="/usr/bin/terraform"), \
         patch("subprocess.run", side_effect=[mock_init, mock_plan]):
        result = terraform_plan({"main.tf": 'resource "null_resource" "x" {}'})

    assert result["success"] is True
    assert result["terraform_available"] is True
    assert "Plan:" in result["plan_output"]
    assert "initialized" in result["init_output"]
    assert result["error"] is None


def test_terraform_plan_failure_mock():
    """Mock a failed terraform plan run."""
    from datasphere.api.terraform_runner import terraform_plan

    mock_init = MagicMock()
    mock_init.stdout = "Terraform initialized.\n"
    mock_init.stderr = ""
    mock_init.returncode = 0

    mock_plan = MagicMock()
    mock_plan.stdout = ""
    mock_plan.stderr = "Error: Invalid resource type.\n"
    mock_plan.returncode = 1

    with patch("shutil.which", return_value="/usr/bin/terraform"), \
         patch("subprocess.run", side_effect=[mock_init, mock_plan]):
        result = terraform_plan({"main.tf": "bad content"})

    assert result["success"] is False
    assert result["terraform_available"] is True
    assert result["error"] is not None


# ---------------------------------------------------------------------------
# Integration tests for POST /terraform/plan endpoint
# ---------------------------------------------------------------------------

def test_terraform_plan_endpoint_returns_200(client):
    """POST /terraform/plan returns 200 with generated and dry_run keys."""
    payload = {
        "business_request": "analytics pipeline",
        "cloud_provider": "aws",
        "data_warehouse": "snowflake",
    }
    resp = client.post("/terraform/plan", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "generated" in data
    assert "dry_run" in data


def test_terraform_plan_endpoint_generated_shape(client):
    """generated section has provider, warehouse, file_count, files."""
    payload = {
        "business_request": "data lake pipeline",
        "cloud_provider": "aws",
        "data_warehouse": "snowflake",
    }
    resp = client.post("/terraform/plan", json=payload)
    assert resp.status_code == 200
    generated = resp.json()["generated"]
    assert "provider" in generated
    assert "warehouse" in generated
    assert "file_count" in generated
    assert "files" in generated


def test_terraform_plan_endpoint_dry_run_shape(client):
    """dry_run section has expected keys with correct types."""
    payload = {
        "business_request": "streaming pipeline",
        "cloud_provider": "gcp",
        "data_warehouse": "bigquery",
    }
    resp = client.post("/terraform/plan", json=payload)
    assert resp.status_code == 200
    dry_run = resp.json()["dry_run"]
    assert "success" in dry_run
    assert "plan_output" in dry_run
    assert "init_output" in dry_run
    assert "terraform_available" in dry_run
    assert "working_dir" in dry_run
    assert isinstance(dry_run["terraform_available"], bool)
    assert isinstance(dry_run["success"], bool)


def test_terraform_plan_endpoint_no_terraform_binary(client):
    """When terraform binary is not installed, dry_run.success is False and message mentions 'not found'."""
    with patch("datasphere.api.terraform_runner.shutil.which", return_value=None):
        payload = {
            "business_request": "simple warehouse",
            "cloud_provider": "aws",
            "data_warehouse": "redshift",
        }
        resp = client.post("/terraform/plan", json=payload)
    assert resp.status_code == 200
    dry_run = resp.json()["dry_run"]
    assert dry_run["success"] is False
    assert dry_run["terraform_available"] is False
    assert "not found" in dry_run["error"]
