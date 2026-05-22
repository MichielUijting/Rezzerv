from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from app.api.route_governance import build_route_governance_manifest
from app.db import get_runtime_datastore_info

router = APIRouter()

VERSION_FILE_PATH = Path(__file__).resolve().parents[2] / 'VERSION.txt'
VERSION_TAG = VERSION_FILE_PATH.read_text(encoding='utf-8').strip() if VERSION_FILE_PATH.exists() else 'dev'


@router.get('/api/health')
def health():
    datastore_info = get_runtime_datastore_info()
    payload = {'status': 'ok', 'datastore': datastore_info.get('datastore', 'onbekend')}
    if datastore_info.get('database'):
        payload['database'] = datastore_info['database']
    if datastore_info.get('storage'):
        payload['storage'] = datastore_info['storage']
    return payload


@router.get('/api/version')
def api_version():
    return {
        'version': VERSION_TAG,
        'source': 'VERSION.txt',
    }


@router.get('/api/admin/route-governance')
def route_governance_manifest():
    from app.main import app
    return build_route_governance_manifest(app)
