"""Measure the desktop manager's process tree (run with the collector Python)."""
import json
import time

import psutil


def snapshot():
    roots = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        name = (process.info["name"] or "").lower()
        if "python" not in name and name != "goactivity.exe":
            continue
        args = process.info["cmdline"] or []
        if name == "goactivity.exe" or "desktop.app" in args or any("run_module('desktop.app'" in arg for arg in args):
            roots.append(process)
    root_ids = {process.pid for process in roots}
    roots = [process for process in roots if process.ppid() not in root_ids]
    processes = {process.pid: process for root in roots for process in [root, *root.children(recursive=True)]}
    for process in processes.values():
        try:
            process.cpu_percent()
        except psutil.Error:
            pass
    time.sleep(1)
    rows = []
    for process in processes.values():
        try:
            memory = process.memory_info()
            rows.append({"pid": process.pid, "name": process.name(), "rss_mb": round(memory.rss / 2**20, 1),
                         "private_mb": round(getattr(memory, "private", 0) / 2**20, 1),
                         "threads": process.num_threads(), "cpu_percent": process.cpu_percent()})
        except psutil.Error:
            pass
    return {"process_count": len(rows), "rss_mb": round(sum(row["rss_mb"] for row in rows), 1),
            "private_mb": round(sum(row["private_mb"] for row in rows), 1),
            "threads": sum(row["threads"] for row in rows),
            "machine_cpu_percent": round(sum(row["cpu_percent"] for row in rows) / psutil.cpu_count(), 2),
            "processes": rows}


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2))
