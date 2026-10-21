"""TD-05: signed, fresh Windows host evidence, independent of browser claims.

Only a read-only proof directory is mounted. Private signing material stays in
Windows DPAPI storage and is never passed to the backend/container. Deployment
pins the public-key SHA256 and machine identity separately from that directory.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .maintenance_runtime_preflight import MaintenancePreflightError


def _read_envelope(filename):
    try:
        proof_path = Path(os.environ['INHUIS_MAINTENANCE_PROOF_FILE']).with_name(filename)
        key_path = Path(os.environ['INHUIS_MAINTENANCE_PUBLIC_KEY_FILE'])
        expected_key = os.environ['INHUIS_MAINTENANCE_PUBLIC_KEY_SHA256'].lower()
        expected_host = os.environ['INHUIS_MAINTENANCE_HOST_ID']
        key_bytes = key_path.read_bytes()
        if hashlib.sha256(key_bytes).hexdigest() != expected_key:
            raise ValueError('Unpinned host key')
        envelope = json.loads(proof_path.read_text(encoding='utf-8-sig'))
        raw = base64.b64decode(envelope['payload'], validate=True)
        signature = base64.b64decode(envelope['signature'], validate=True)
        if len(raw) > 65536:
            raise ValueError('Oversized host proof')
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
        key = serialization.load_pem_public_key(key_bytes)
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 3072:
            raise ValueError('Host key type or size')
        key.verify(signature, raw, padding.PKCS1v15(), hashes.SHA256())
        proof = json.loads(raw)
        now = datetime.now(timezone.utc)
        issued = datetime.fromisoformat(proof['issued_at'].replace('Z','+00:00'))
        if issued.tzinfo is None or not -5 <= (now-issued).total_seconds() <= 90:
            raise ValueError('Stale host proof')
        if proof['host_id'] != expected_host:
            raise ValueError('Wrong Windows host')
        container = os.environ.get('HOSTNAME', '')
        if not container or not proof['backend_container_id'].startswith(container):
            raise ValueError('Wrong runtime container')
        return proof
    except Exception as exc:
        raise MaintenancePreflightError('Onderhoudsagent ontbreekt, is niet vertrouwd of het bewijs is verlopen.') from exc


def read_agent_availability():
    proof = _read_envelope('availability.json')
    if proof.get('kind') != 'availability':
        raise MaintenancePreflightError('Geen geldig agentbeschikbaarheidsbewijs')
    return proof


def read_host_proof(*, cycle_id, runtime, previous=None):
    try:
        proof = _read_envelope('proof.json')
        now = datetime.now(timezone.utc)
        if proof['cycle_id'] != cycle_id:
            raise ValueError('Host/cycle mismatch')
        if not proof['compose_project'] or not proof['volume_identity'] or not proof['cluster_identity']:
            raise ValueError('Physical storage identity missing')
        if not proof['windows_boot'] or not proof['frontend_ready'] or not proof['external_ready']:
            raise ValueError('Host/frontend/external health missing')
        for key in ('database', 'database_oid', 'server_started_at', 'server_address', 'alembic_heads'):
            if proof['database_runtime'][key] != runtime[key]:
                raise ValueError('Independent host/database evidence differs')
        backup = proof['backup']
        if not backup['restored_and_compared'] or backup['cycle_id'] != cycle_id:
            raise ValueError('No tested backup for current maintenance')
        if len(backup['sha256']) != 64 or backup['domain_fingerprint'] != proof['domain_fingerprint']:
            raise ValueError('Backup/live domain fingerprint differs')
        restored = datetime.fromisoformat(backup['restored_at'].replace('Z','+00:00'))
        if restored.tzinfo is None or not 0 <= (now-restored).total_seconds() <= 86400:
            raise ValueError('Backup proof too old')
        if previous:
            for key in ('host_id','compose_project','volume_identity','cluster_identity','domain_fingerprint'):
                if proof[key] != previous[key]:
                    raise ValueError('Host/storage/data changed after restart')
            if proof['windows_boot'] == previous['windows_boot']:
                raise ValueError('Windows has not restarted')
            if proof['backup']['sha256'] != previous['backup']['sha256']:
                raise ValueError('Backup artifact changed')
        return proof
    except Exception as exc:
        raise MaintenancePreflightError('Host-, opslag-, back-up- of herstartbewijs ontbreekt, is verlopen of wijkt af. Laat de onderhoudsagent controleren; Inhuis blijft geblokkeerd.') from exc
