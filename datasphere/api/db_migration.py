"""Run Alembic migrations at startup."""
import os
from pathlib import Path


def run_migrations() -> None:
    """Apply pending Alembic migrations. No-op if already up to date."""
    try:
        from alembic.config import Config
        from alembic import command
        cfg = Config(str(Path(__file__).parent / "migrations" / "alembic.ini"))
        cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        db_path = os.path.expanduser(os.getenv("DATASPHERE_JOB_DB", "~/.datasphere/jobs.db"))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.upgrade(cfg, "head")
    except ImportError:
        pass  # alembic not installed — skip
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("db_migration_failed error=%s", e)
