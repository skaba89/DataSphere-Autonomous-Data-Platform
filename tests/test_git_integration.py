"""Tests for optional Git repository initialization of generated artifacts."""
import re
import tempfile
from pathlib import Path

import pytest

from datasphere.api.git_integration import init_git_repo


def test_init_git_repo_creates_git_directory(tmp_path):
    """init_git_repo should create a .git directory in the given path."""
    (tmp_path / "main.tf").write_text("# terraform")
    result = init_git_repo(tmp_path, "test-job-123")
    assert result["initialized"] is True
    assert (tmp_path / ".git").is_dir()


def test_init_git_repo_returns_valid_sha(tmp_path):
    """init_git_repo should return a valid 40-char hex SHA."""
    (tmp_path / "file.txt").write_text("hello")
    result = init_git_repo(tmp_path, "job-abc")
    assert result["initialized"] is True
    sha = result["commit"]
    assert re.fullmatch(r"[0-9a-f]{40}", sha), f"Not a valid SHA: {sha}"
    assert result["path"] == str(tmp_path)


def test_init_git_repo_returns_false_when_path_is_invalid(tmp_path):
    """init_git_repo should return initialized=False when the path cannot be used as a git repo."""
    # Create a file where a directory would need to be, making git init fail
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file, not a dir")
    invalid = blocker / "subdir"  # can't exist because parent is a file
    result = init_git_repo(invalid, "job-x")
    assert result["initialized"] is False
    assert "reason" in result


def test_init_git_repo_commit_message_contains_job_id(tmp_path):
    """The git commit message should contain the job_id."""
    import subprocess
    (tmp_path / "schema.sql").write_text("CREATE TABLE t (id INT);")
    job_id = "unique-job-id-42"
    result = init_git_repo(tmp_path, job_id, description="Test pipeline")
    assert result["initialized"] is True
    log = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--format=%B", "-1"],
        capture_output=True, text=True
    ).stdout
    assert job_id in log


def test_init_git_repo_creates_gitignore(tmp_path):
    """init_git_repo should write a .gitignore file."""
    (tmp_path / "data.csv").write_text("col1,col2")
    result = init_git_repo(tmp_path, "job-gi")
    assert result["initialized"] is True
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text()
    assert "*.pyc" in content
    assert "*.tfstate" in content
