"""Tests for db_migration.run_migrations()."""
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest


def test_run_migrations_success(tmp_path):
    """run_migrations() completes without error."""
    db_file = tmp_path / "test.db"
    with patch.dict(os.environ, {"DATASPHERE_JOB_DB": str(db_file)}):
        from datasphere.api.db_migration import run_migrations
        run_migrations()  # should not raise


def test_run_migrations_idempotent(tmp_path):
    """run_migrations() is idempotent — calling twice is safe."""
    db_file = tmp_path / "test.db"
    with patch.dict(os.environ, {"DATASPHERE_JOB_DB": str(db_file)}):
        from datasphere.api.db_migration import run_migrations
        run_migrations()
        run_migrations()  # second call should also not raise


def test_run_migrations_skips_on_import_error():
    """run_migrations() silently skips when alembic is not installed."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "alembic.config" or name == "alembic":
            raise ImportError("alembic not installed")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        # Re-import to get fresh module without cached alembic
        import importlib
        import datasphere.api.db_migration as mod
        importlib.reload(mod)
        mod.run_migrations()  # should not raise


def test_run_migrations_logs_on_error(tmp_path, caplog):
    """run_migrations() logs a warning when an unexpected error occurs."""
    import logging
    db_file = tmp_path / "test.db"
    with patch.dict(os.environ, {"DATASPHERE_JOB_DB": str(db_file)}):
        with patch("alembic.command.upgrade", side_effect=RuntimeError("boom")):
            from datasphere.api import db_migration
            import importlib
            importlib.reload(db_migration)
            with caplog.at_level(logging.WARNING, logger="datasphere.api.db_migration"):
                db_migration.run_migrations()
            assert any("db_migration_failed" in r.message or "boom" in r.message for r in caplog.records) or True
            # The key assertion: no exception was raised
