from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import venv

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
REQUIREMENTS_FILE = PROJECT_ROOT / 'requirements.txt'
DEFAULT_VENV_DIR = PROJECT_ROOT / '.venv'
REQUIRED_IMPORTS = ('fastapi', 'sqlalchemy', 'uvicorn', 'pydantic')
INVALID_VENV_MARKERS = (
    'No Python at',
    'Fatal error in launcher',
    'Unable to create process',
)


def venv_python_path(venv_dir: pathlib.Path) -> pathlib.Path:
    if os.name == 'nt':
        return venv_dir / 'Scripts' / 'python.exe'
    return venv_dir / 'bin' / 'python'


def _venv_is_usable(python_path: pathlib.Path) -> tuple[bool, str]:
    if not python_path.exists():
        return False, 'Python-uitvoerbaar bestand ontbreekt in de virtuele omgeving.'
    try:
        result = subprocess.run(
            [str(python_path), '--version'],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        return False, str(exc)

    combined = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode != 0:
        return False, combined or f'Venv-python gaf foutcode {result.returncode}.'
    for marker in INVALID_VENV_MARKERS:
        if marker.lower() in combined.lower():
            return False, combined
    return True, combined


def ensure_venv(venv_dir: pathlib.Path) -> pathlib.Path:
    python_path = venv_python_path(venv_dir)
    if python_path.exists():
        usable, details = _venv_is_usable(python_path)
        if usable:
            return python_path
        print('[BOOTSTRAP] Bestaande lokale virtuele omgeving is ongeldig voor deze computer.')
        if details:
            print('[BOOTSTRAP] Reden:', details)
        print(f'[BOOTSTRAP] Verwijder ongeldige omgeving en bouw opnieuw op: {venv_dir}')
        shutil.rmtree(venv_dir, ignore_errors=True)

    print(f'[BOOTSTRAP] Maak lokale virtuele omgeving aan in {venv_dir}')
    builder = venv.EnvBuilder(with_pip=True, clear=False, upgrade=False)
    builder.create(str(venv_dir))
    if not python_path.exists():
        raise RuntimeError(f'Virtuele omgeving aangemaakt, maar Python niet gevonden op {python_path}')

    usable, details = _venv_is_usable(python_path)
    if not usable:
        raise RuntimeError(f'Nieuwe virtuele omgeving is niet bruikbaar: {details}')
    return python_path


def imports_ready(python_executable: pathlib.Path) -> bool:
    probe = '; '.join(f'import {name}' for name in REQUIRED_IMPORTS)
    result = subprocess.run(
        [str(python_executable), '-c', probe],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.returncode == 0


def install_requirements(python_executable: pathlib.Path) -> None:
    if not REQUIREMENTS_FILE.exists():
        raise FileNotFoundError(f'Requirementsbestand ontbreekt: {REQUIREMENTS_FILE}')
    print('[BOOTSTRAP] Vereiste Python-pakketten ontbreken. Installatie vanuit requirements.txt wordt gestart...')
    subprocess.run([str(python_executable), '-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'wheel'], cwd=str(PROJECT_ROOT), check=True)
    subprocess.run([str(python_executable), '-m', 'pip', 'install', '-r', str(REQUIREMENTS_FILE)], cwd=str(PROJECT_ROOT), check=True)


def run_check_only(python_executable: pathlib.Path) -> int:
    ready = imports_ready(python_executable)
    if not ready:
        install_requirements(python_executable)
        ready = imports_ready(python_executable)
    if ready:
        print('[OK] Backend dependency-basis is beschikbaar in de lokale virtuele omgeving.')
        print(f'[OK] Gebruik voor lokale backend-start: {python_executable} -m uvicorn app.main:app --host 127.0.0.1 --port 8000')
        return 0
    print('[ERROR] Vereiste backend dependencies konden niet worden bevestigd.')
    return 1


def run_server(python_executable: pathlib.Path, host: str, port: int) -> int:
    if not imports_ready(python_executable):
        install_requirements(python_executable)
        if not imports_ready(python_executable):
            print('[ERROR] Backend dependencies zijn na installatie nog steeds niet compleet.')
            return 1
    cmd = [str(python_executable), '-m', 'uvicorn', 'app.main:app', '--host', host, '--port', str(port)]
    print('[BOOTSTRAP] Start backend via lokale virtuele omgeving...')
    print('[BOOTSTRAP] Commando:', ' '.join(cmd))
    process = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
    return process.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Bootstrap en start de Rezzerv-backend lokaal zonder handmatige pip-stappen.')
    parser.add_argument('--check-only', action='store_true', help='Controleer alleen de lokale dependency-basis en start geen server.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--venv-dir', default=str(DEFAULT_VENV_DIR))
    args = parser.parse_args()

    try:
        venv_dir = pathlib.Path(args.venv_dir)
        python_executable = ensure_venv(venv_dir)

        if args.check_only:
            raise SystemExit(run_check_only(python_executable))
        raise SystemExit(run_server(python_executable, args.host, args.port))
    except Exception as exc:
        print('[ERROR] Lokale backend-bootstrap is gestopt.')
        print('[ERROR]', exc)
        raise SystemExit(1)
