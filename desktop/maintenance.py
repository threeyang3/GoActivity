"""Online SQLite snapshots, run in the service Python rather than the GUI."""
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path


def backup_database(source: Path, directory: Path, name: str, keep: int = 28) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{name}-{time.time_ns()}.db"
    temporary = destination.with_suffix(".tmp")
    deadline = time.monotonic() + 120

    def progress(*_):
        if time.monotonic() > deadline:
            raise TimeoutError("SQLite snapshot timed out")

    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as src:
            with closing(sqlite3.connect(temporary)) as dst:
                src.backup(dst, pages=128, progress=progress, sleep=0.05)
                if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Snapshot integrity check failed")
        os.replace(temporary, destination)
        # Only snapshots owned by this function are eligible for retention.
        for old in sorted(directory.glob(f"{name}-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)[max(1, keep):]:
            old.unlink()
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def run_backups(root: Path) -> dict:
    import re
    import yaml
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url
    from app.config import get_settings

    settings = get_settings()
    directory = settings.storage_dir / "backups"
    if not directory.is_absolute():
        directory = root / directory
    collector = root / "we-mp-rss"
    config = yaml.safe_load((collector / "config.yaml").read_text(encoding="utf-8")) or {}
    values = {**dotenv_values(collector / ".env"), **os.environ}
    collector_url = re.sub(r"\$\{([^}:]+)(?::-([^}]*))?\}", lambda m: values.get(m[1]) or m[2] or "", str(config.get("db", "sqlite:///./data/db.db")))
    result = {"finished_at": time.time(), "status": "completed", "databases": {}}
    for name, url, base in [("goactivity", settings.database_url, root), ("collector", collector_url, collector)]:
        try:
            parsed = make_url(url)
            if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
                raise ValueError("Only file-backed SQLite databases support local snapshots")
            source = Path(parsed.database)
            if not source.is_absolute():
                source = base / source
            snapshot = backup_database(source, directory, name)
            result["databases"][name] = {"status": "ok", "snapshot": str(snapshot), "bytes": snapshot.stat().st_size}
        except Exception as exc:
            result["status"] = "failed"
            # Error class only: configuration/SQL errors can contain credentials.
            result["databases"][name] = {"status": "error", "error": type(exc).__name__}
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / "status.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, directory / "status.json")
    return result


if __name__ == "__main__":
    from desktop.paths import project_root
    import sys
    outcome = run_backups(project_root())
    print(json.dumps(outcome, ensure_ascii=False))
    sys.exit(0 if outcome["status"] == "completed" else 1)
