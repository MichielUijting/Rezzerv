"""TD-08: real RSA signatures, pinning, expiry, backup and Windows-boot proof."""
import base64
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from backend.app.services.maintenance_host_proof import read_host_proof
from backend.app.services.maintenance_runtime_preflight import MaintenancePreflightError

class HostProofTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    def setUp(self):
        self.temp=TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.proof_path=root/'proof.json'; key_path=root/'public.pem'
        public=self.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        key_path.write_bytes(public)
        self.runtime={'database':'maintenance_test','database_oid':'123','server_started_at':'test-start','server_address':'127.0.0.1','alembic_heads':['test-head']}
        stamp=datetime.now(timezone.utc).isoformat()
        self.proof={'cycle_id':'test-cycle','issued_at':stamp,'host_id':'test-host','windows_boot':'boot-a','backend_container_id':'test-container-full-id','compose_project':'isolated-test','volume_identity':'volume-hash','cluster_identity':'cluster-id','frontend_ready':True,'external_ready':True,'database_runtime':self.runtime,'domain_fingerprint':'domain-hash','backup':{'cycle_id':'test-cycle','restored_and_compared':True,'restored_at':stamp,'sha256':'a'*64,'domain_fingerprint':'domain-hash'}}
        self.env=patch.dict(os.environ,{'INHUIS_MAINTENANCE_PROOF_FILE':str(self.proof_path),'INHUIS_MAINTENANCE_PUBLIC_KEY_FILE':str(key_path),'INHUIS_MAINTENANCE_PUBLIC_KEY_SHA256':hashlib.sha256(public).hexdigest(),'INHUIS_MAINTENANCE_HOST_ID':'test-host','HOSTNAME':'test-container'})
        self.env.start(); self.addCleanup(self.env.stop)
    def write(self):
        raw=json.dumps(self.proof).encode()
        signature=self.key.sign(raw,padding.PKCS1v15(),hashes.SHA256())
        self.proof_path.write_text(json.dumps({'payload':base64.b64encode(raw).decode(),'signature':base64.b64encode(signature).decode()}))
    def read(self,**kwargs): return read_host_proof(cycle_id='test-cycle',runtime=self.runtime,**kwargs)
    def test_valid_signed_backup_proof(self):
        self.write(); self.assertEqual(self.read()['host_id'],'test-host')
    def test_real_windows_boot_change_required(self):
        self.write()
        with self.assertRaises(MaintenancePreflightError): self.read(previous=self.proof)
        previous=json.loads(json.dumps(self.proof)); self.proof['windows_boot']='boot-b'; self.write()
        self.assertEqual(self.read(previous=previous)['windows_boot'],'boot-b')
    def test_reject_stale_wrong_host_cycle_storage_backup_and_unready_routes(self):
        for key,value in [('issued_at',(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()),('host_id','other-host'),('cycle_id','old-cycle'),('backend_container_id','other-container'),('volume_identity',''),('frontend_ready',False),('external_ready',False),('domain_fingerprint','changed')]:
            with self.subTest(key=key):
                original=self.proof[key]; self.proof[key]=value; self.write()
                with self.assertRaises(MaintenancePreflightError): self.read()
                self.proof[key]=original
    def test_signature_cannot_be_replaced_by_browser_claim(self):
        self.write(); data=json.loads(self.proof_path.read_text()); data['payload']=base64.b64encode(b'{"restart_allowed":true}').decode(); self.proof_path.write_text(json.dumps(data))
        with self.assertRaises(MaintenancePreflightError): self.read()
    def test_changed_cluster_after_restart_is_rejected(self):
        previous=json.loads(json.dumps(self.proof)); self.proof.update(windows_boot='boot-b',cluster_identity='wrong-cluster'); self.write()
        with self.assertRaises(MaintenancePreflightError): self.read(previous=previous)
