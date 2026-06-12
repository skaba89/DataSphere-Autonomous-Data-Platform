"""Optional Git initialization for generated artifacts."""
import os
import subprocess
from pathlib import Path


def init_git_repo(artifact_dir: Path, job_id: str, description: str = "") -> dict:
    """
    Initialize a git repo in artifact_dir and make an initial commit.
    Returns {"initialized": True, "commit": sha, "path": str} or {"initialized": False, "reason": str}.
    """
    try:
        # git init
        subprocess.run(["git", "init", str(artifact_dir)], check=True, capture_output=True)
        # Write .gitignore
        (artifact_dir / ".gitignore").write_text("*.pyc\n__pycache__/\n.env\n*.tfstate\n*.tfstate.backup\n")
        # git add all
        subprocess.run(["git", "-C", str(artifact_dir), "add", "-A"], check=True, capture_output=True)
        # git commit
        msg = f"Initial DataSphere generation\n\nJob: {job_id}\n{description}"
        env = {**os.environ, "GIT_AUTHOR_NAME": "DataSphere", "GIT_AUTHOR_EMAIL": "datasphere@local",
               "GIT_COMMITTER_NAME": "DataSphere", "GIT_COMMITTER_EMAIL": "datasphere@local"}
        result = subprocess.run(
            ["git", "-C", str(artifact_dir), "-c", "commit.gpgsign=false", "commit", "-m", msg],
            check=True, capture_output=True, text=True, env=env
        )
        # Get commit SHA
        sha = subprocess.run(
            ["git", "-C", str(artifact_dir), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True
        ).stdout.strip()
        return {"initialized": True, "commit": sha, "path": str(artifact_dir)}
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return {"initialized": False, "reason": str(e)}
