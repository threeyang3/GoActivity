"""Prepare both services from tracked source; never overwrite existing config."""
import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path


def run(command, cwd, env=None):
    subprocess.run([str(arg) for arg in command], cwd=cwd, env=env, check=True)


def python_command(name, version):
    command = [name, f"-{version}"] if name == "py" else [name]
    actual = subprocess.check_output([*command, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], text=True).strip()
    if actual != version:
        raise RuntimeError(f"Expected Python {version}, found {actual} via {name}")
    return command


def environment(root, command, uv):
    executable = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.exists():
        if uv:
            native = subprocess.check_output([*command, "-c", "import sys; print(sys.executable)"], text=True).strip()
            run([uv, "venv", "--python", native, root / ".venv"], root)
        else:
            run([*command, "-m", "venv", root / ".venv"], root)
    # Reject an incompatible existing environment instead of replacing it.
    expected = subprocess.check_output([*command, "-c", "import sys; print(sys.version_info[:2])"], text=True)
    actual = subprocess.check_output([executable, "-c", "import sys; print(sys.version_info[:2])"], text=True)
    if actual != expected:
        raise RuntimeError(f"Existing environment has the wrong Python version: {executable}")
    return executable


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go-python", default=sys.executable)
    parser.add_argument("--collector-python", default="py" if os.name == "nt" else "python3.13")
    parser.add_argument("--uv", help="Optional uv executable for cached dependency installation")
    args = parser.parse_args()
    go_command = python_command(args.go_python, "3.11")
    collector_command = python_command(args.collector_python, "3.13")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not shutil.which("git") or not npm:
        parser.error("Install Git and Node.js 24 (including npm) first")
    node_version = subprocess.check_output(["node", "--version"], text=True).strip()
    if int(node_version.lstrip("v").split(".")[0]) < 24:
        parser.error("Node.js 24 or newer is required by this tested setup")
    collector = root / "we-mp-rss"
    if not collector.exists():
        run(["git", "clone", "https://github.com/rachelos/we-mp-rss.git", collector], root)
        base = (root / "patches/collector-base.txt").read_text().strip()
        run(["git", "-C", collector, "checkout", base], root)
    run([*go_command, root / "scripts/apply-collector-patch.py", "--collector", collector], root)
    go_python = environment(root, go_command, args.uv)
    collector_python = environment(collector, collector_command, args.uv)

    def install(python, requirements, cwd):
        command = [args.uv, "pip", "install", "--python", python] if args.uv else [python, "-m", "pip", "install"]
        run([*command, *requirements], cwd)

    install(go_python, ["-r", "requirements.txt", "-r", "requirements-desktop.txt", "-r", "requirements-ocr.txt", "-c", "constraints-runtime.txt"], root)
    install(collector_python, ["-r", "requirements.txt", "-c", root / "constraints-collector.txt"], collector)
    run([collector_python, "-m", "playwright", "install", "chromium"], collector)
    run([npm, "ci"], collector / "web_ui")
    # The backend serves static/, whereas Vite's default output is dist/.
    # Keep legacy static resources; only overlay the newly built frontend.
    run([npm, "run", "build"], collector / "web_ui")
    dist = collector / "web_ui/dist"
    for item in dist.iterdir():
        if item.name == "index.html":
            continue
        if item.is_dir():
            shutil.copytree(item, collector / "static" / item.name, dirs_exist_ok=True)
        else:
            shutil.copyfile(item, collector / "static" / item.name)
    shutil.copyfile(dist / "index.html", collector / "static/index.html")
    if not (root / ".env").exists():
        shutil.copyfile(root / ".env.example", root / ".env")
    config = collector / "config.yaml"
    fresh_config = not config.exists()
    if not config.exists():
        config.write_text(
            "app_name: we-mp-rss\nport: 8001\ndb: sqlite:///./data/db.db\n"
            f"secret: {json.dumps(secrets.token_urlsafe(48))}\n"
            "server:\n  enable_job: true\n  auto_reload: false\n  auth_web: true\n"
            "redis:\n  url: ''\n  server:\n    enabled: false\n"
            "gather:\n  model: web\n  browser_type: chromium\n  content: true\n"
            "  content_auto_check: false\n  content_mode: web\n"
            "logging:\n  sql: false\n",
            encoding="utf-8",
        )
    if fresh_config and not (collector / "data/db.db").exists():
        password = secrets.token_urlsafe(24)
        init_env = os.environ.copy()
        init_env.update(USERNAME="admin", PASSWORD=password, PYTHONUTF8="1")
        run([collector_python, "-c", "import init_sys; init_sys.init(); from core.db import DB; from core.models.user import User; session=DB.get_session(); assert session.query(User).filter(User.username == 'admin').first() is not None, 'Collector administrator initialization failed'"], collector, env=init_env)
        credentials = collector / "data/bootstrap-admin.json"
        credentials.write_text(json.dumps({"username": "admin", "password": password}), encoding="utf-8")
        print("Initial collector login is stored locally in we-mp-rss/data/bootstrap-admin.json")
    run([go_python, "-c", "from app.db import init_db; init_db()"], root)
    print("Both services are installed. Configure external credentials, then start python -m desktop.app.")
    print("Existing configuration was preserved; no account credentials or sessions were copied.")


if __name__ == "__main__":
    main()
