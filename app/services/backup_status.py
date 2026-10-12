import json
import time


def backup_status(settings) -> dict:
    try:
        result = json.loads((settings.storage_dir / "backups/status.json").read_text(encoding="utf-8"))
        if not isinstance(result, dict) or not isinstance(result.get("finished_at"), (int, float)):
            return {"status": "missing"}
        if time.time() - result["finished_at"] > 7 * 3600:
            result["status"] = "stale"
        return result
    except (OSError, ValueError):
        return {"status": "missing"}
