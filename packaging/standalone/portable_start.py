"""Portable Windows runner; deliberately requires bundled runtimes, never installs dependencies."""
from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen

BASE = Path(__file__).resolve().parent
RUNTIME = BASE / "runtime"
DATA = BASE / "data"
BIN = RUNTIME / "postgres" / "bin"
PYTHON = RUNTIME / "python" / "python.exe"
PY_BIN = BIN / "postgres.exe"
INITDB = BIN / "initdb.exe"
PG_CTL = BIN / "pg_ctl.exe"
DB = DATA / "postgres"
LOG = DATA / "logs"
PORT = 5174


def run(args, *, env=None, capture=False, cwd=None):
    return subprocess.run([str(a) for a in args], check=True, env=env, cwd=cwd, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None)


def available(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def begin():
    if os.name != "nt":
        raise RuntimeError("Deze portable runtime is uitsluitend voor Windows.")
    for item in (PYTHON, PY_BIN, INITDB, PG_CTL, BASE / "www" / "index.html",
                 BASE / "backend" / "app", BASE / "backend" / "alembic.ini"):
        if not item.exists():
            raise RuntimeError(f"Vereist onderdeel ontbreekt: {item}")
    if any(available(port) for port in (PORT, 18001, 15432)):
        raise RuntimeError("Een benodigde localhost-poort is al in gebruik (5174/18001/15432).")
    LOG.mkdir(parents=True, exist_ok=True)
    DB.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PGPORT"] = "15432"
    env["PGHOST"] = "127.0.0.1"
    if not (DB / "PG_VERSION").exists():
        # Local-only, temporary database. The server never listens on a non-loopback address.
        run([INITDB, "-D", DB, "-U", "inhuis", "-A", "trust", "--encoding=UTF8"], env=env)
    run([PG_CTL, "-D", DB, "-l", LOG / "postgres.log", "-o",
         "-h 127.0.0.1 -p 15432", "-w", "start"], env=env)
    env.update({
        "DATABASE_URL": "postgresql://inhuis@127.0.0.1:15432/postgres",
        "MIGRATION_DATABASE_URL": "postgresql://inhuis@127.0.0.1:15432/postgres",
        "REZZERV_DATASTORE_POLICY": "postgresql-only",
        "REZZERV_EMAIL_ENABLED": "false",
        "REZZERV_RESEND_API_KEY": "",
        "REZZERV_GS1_MPM_SHARE_API_KEY": "",
        "REZZERV_RETAILER_ACCOUNT_KEY": "",
        "REZZERV_IN_HUIS_DEMO_SCANNER_BASE_URL": "",
        "REZZERV_IN_HUIS_DEMO_SCANNER_API_KEY": "",
        "REZZERV_SESSION_COOKIE_SECURE": "false",
        "REZZERV_APP_BASE_URL": "http://localhost:5174",
        "REZZERV_PROVISION_TEST_HOUSEHOLD_ZERO": "true",
        "REZZERV_RECEIPT_STARTUP_REMBG_WARMUP": "false",
        "REZZERV_RECEIPT_STARTUP_PADDLE_WARMUP": "false",
        "REZZERV_RECEIPT_STARTUP_OCR_WARMUP": "false",
    })
    secret_file = DATA / ".local-password"
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(24), encoding="ascii")
    env["REZZERV_SUPERGEBRUIKER_PASSWORD"] = secret_file.read_text(encoding="ascii")
    # Preflight intentionally retained: do not skip real schema migration.
    backend_env = env | {"PYTHONPATH": str(BASE / "backend")}
    with (LOG / "preflight.log").open("a", encoding="utf-8") as logfile:
        run([PYTHON, "-m", "app.runtime_preflight"], env=backend_env, cwd=BASE / "backend")
    backend_log = (LOG / "backend.log").open("a", encoding="utf-8")
    backend = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app.session_entrypoint:app",
         "--host", "127.0.0.1", "--port", "18001"],
        cwd=BASE / "backend", env=backend_env, stdout=backend_log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
    frontend_log = (LOG / "frontend.log").open("a", encoding="utf-8")
    frontend = subprocess.Popen(
        [str(PYTHON), str(BASE / "portable_server.py")],
        cwd=BASE, env=env, stdout=frontend_log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for _ in range(90):
            if backend.poll() is not None or frontend.poll() is not None:
                raise RuntimeError("Een InHuis-proces is voortijdig gestopt; zie data/logs.")
            try:
                with urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1):
                    break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("Backend werd niet binnen de opstartcontrole beschikbaar.")
        webbrowser.open(f"http://127.0.0.1:{PORT}")
        print("InHuis draait lokaal. Sluit dit venster om te stoppen.")
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(1)
    finally:
        frontend.terminate()
        backend.terminate()
        for proc in (frontend, backend):
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: proc.kill()
        run([PG_CTL, "-D", DB, "-m", "fast", "-w", "stop"], env=env)


if __name__ == "__main__":
    try:
        begin()
    except Exception as exc:
        print(f"InHuis start niet: {exc}", file=sys.stderr)
        raise SystemExit(1)
