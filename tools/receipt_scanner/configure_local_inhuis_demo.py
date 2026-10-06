from __future__ import annotations

import secrets
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"

REQUIRED = {
    "REZZERV_IN_HUIS_DEMO_SCANNER_BASE_URL": "http://host.docker.internal:8003",
    "REZZERV_IN_HUIS_DEMO_SCANNER_API_KEY_HEADER": "X-API-Key",
    "REZZERV_IN_HUIS_DEMO_SCANNER_SUBMIT_PATH": "/scan",
    "REZZERV_IN_HUIS_DEMO_SCANNER_POLL_PATH": "/scan/{job_id}",
    "REZZERV_IN_HUIS_DEMO_SCANNER_REQUEST_TIMEOUT_SECONDS": "90",
}


def read_lines() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def current_value(lines: list[str], key: str) -> str | None:
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def upsert(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{key}={value}"
            return lines
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(f"{key}={value}")
    return lines


def main() -> None:
    lines = read_lines()
    api_key = current_value(lines, "REZZERV_IN_HUIS_DEMO_SCANNER_API_KEY")
    if not api_key:
        api_key = secrets.token_urlsafe(32)
    for key, value in REQUIRED.items():
        lines = upsert(lines, key, value)
    lines = upsert(lines, "REZZERV_IN_HUIS_DEMO_SCANNER_API_KEY", api_key)
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print("Lokale Inhuis-configuratie voor de alternatieve scanner is gereed.")
    print("De servicekey is lokaal opgeslagen en wordt niet getoond.")


if __name__ == "__main__":
    main()
