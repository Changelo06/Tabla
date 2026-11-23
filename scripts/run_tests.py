"""Run each unittest module in isolation, including a timeout and failure summary."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        env.pop(key, None)
    env["QT_QPA_PLATFORM"] = "offscreen"
    if os.name == "nt":
        windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        env["PATH"] = os.pathsep.join(map(str, (Path(sys.executable).parent, Path(sys.base_prefix), windows / "System32", windows)))
    failures = []
    suites = sorted((ROOT / "tests").glob("test_*.py"))
    if not suites:
        raise SystemExit("No test modules found")
    for suite in suites:
        print(f"\n=== {suite.name} ===", flush=True)
        try:
            result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", suite.name, "-v"], cwd=ROOT, env=env, timeout=180)
            if result.returncode:
                failures.append(suite.name)
        except subprocess.TimeoutExpired:
            failures.append(suite.name + " (timeout)")
    print(f"\n{len(suites) - len(failures)}/{len(suites)} test modules passed", flush=True)
    if failures:
        print("Failed: " + ", ".join(failures), file=sys.stderr)
    return bool(failures)

if __name__ == "__main__":
    raise SystemExit(main())
