"""Offline standalone PostgreSQL bootstrap with random SCRAM credentials.

The same dedicated local role performs schema migrations and runtime operations.
It is limited to a loopback-only PostgreSQL instance in the extracted package.
No other PostgreSQL service, database or Windows configuration is touched.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote

def credentials(data: Path) -> tuple[str, str]:
    path = data / "database-credentials.json"
    if path.exists():
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj["user"], obj["password"]
    if (data / "postgres" / "PG_VERSION").exists():
        raise RuntimeError("Database bestaat maar lokaal credentialbestand ontbreekt; herstel eerst de gegevens.")
    obj = {"user": "inhuis_local", "password": secrets.token_urlsafe(40)}
    path.write_text(json.dumps(obj), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return obj["user"], obj["password"]

def initialize(initdb: Path, db: Path, data: Path, env: dict) -> tuple[str, str]:
    user, password = credentials(data)
    if not (db / "PG_VERSION").exists():
        password_file = data / ".pg-init-password"
        password_file.write_text(password + "\n", encoding="utf-8")
        try:
            subprocess.run([str(initdb), "-D", str(db), "-U", user, "-A", "scram-sha-256",
                            "--pwfile", str(password_file), "--encoding=UTF8", "--no-instructions"],
                           env=env, check=True)
        finally:
            password_file.unlink(missing_ok=True)
        # HBA is a local/private server only, password authentication on TCP as well.
        hba = db / "pg_hba.conf"
        hba.write_text(
            "local all all scram-sha-256\n"
            "host all all 127.0.0.1/32 scram-sha-256\n"
            "host all all ::1/128 scram-sha-256\n", encoding="utf-8")
    return user, password

def database_url(user: str, password: str) -> str:
    return f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@127.0.0.1:15432/postgres"
