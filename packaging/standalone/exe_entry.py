"""Minimal compiled launcher. The application and its bundled Python are separate."""
from pathlib import Path
import subprocess
import sys

def main():
    home = Path(sys.executable).resolve().parent
    app = home / "runtime" / "python" / "python.exe"
    script = home / "portable_start.py"
    if not app.is_file() or not script.is_file():
        raise SystemExit("InHuis-runtime ontbreekt. Pak de volledige ZIP uit.")
    raise SystemExit(subprocess.call([str(app), str(script)], cwd=home))

if __name__ == "__main__":
    main()
