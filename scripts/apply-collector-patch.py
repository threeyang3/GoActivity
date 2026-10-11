"""Apply the project's collector source patch without changing local credentials."""
import argparse
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collector", type=Path, default=root / "we-mp-rss")
    parser.add_argument("--check", action="store_true", help="Validate without writing files")
    args = parser.parse_args()
    patch = root / "patches" / "we-mp-rss-runtime.patch"
    target = args.collector.resolve()
    if not (target / "main.py").is_file():
        parser.error("Collector checkout not found; clone it at the documented revision first")
    command = ["git", "-C", str(target), "apply", "--ignore-space-change", "--whitespace=nowarn"]
    reverse = subprocess.run([*command, "--reverse", "--check", str(patch)], capture_output=True)
    if reverse.returncode == 0:
        print("Collector patch is already applied")
        return
    subprocess.run([*command, "--check", str(patch)], check=True)
    if args.check:
        print("Collector patch can be applied")
    else:
        subprocess.run([*command, str(patch)], check=True)
        print("Collector source patched; rebuild web_ui and restart the collector")


if __name__ == "__main__":
    main()
