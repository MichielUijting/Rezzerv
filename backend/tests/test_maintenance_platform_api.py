"""TD-08: route-level permission and information-exposure boundaries.

The canonical role/session authority is separately covered by the repository
matrix. These tests prove maintenance never performs DML before that authority
has granted the exact technical permission.
"""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import unittest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

class MaintenancePlatformApiTests(unittest.TestCase):
    def setUp(self):
        self.engine=MagicMock(); self.engine.dialect.name='postgresql'
        self.permission=Mock(return_value=types.SimpleNamespace(user_id='canonical-test-actor'))
        self.session=Mock(return_value=types.SimpleNamespace(user_id='canonical-test-user'))
        db=types.ModuleType('app.db'); db.engine=self.engine
        sessions=types.ModuleType('app.services.session_request_context')
        sessions.require_platform_permission_from_session=self.permission
        sessions.resolve_current_server_session=self.session
        path=Path(__file__).resolve().parents[1]/'app/api/server_maintenance_routes.py'
        spec=importlib.util.spec_from_file_location('maintenance_api_test',path)
        self.routes=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'app.db':db,'app.services.session_request_context':sessions,'maintenance_api_test':self.routes}):
            spec.loader.exec_module(self.routes)
        app=FastAPI(); app.include_router(self.routes.router)
        self.client=TestClient(app)
    def test_unauthenticated_and_unprivileged_calls_never_reach_database(self):
        for code in (401,403):
            for method in ('get','post'):
                with self.subTest(code=code,method=method):
                    self.permission.side_effect=HTTPException(code,'canonical session denial')
                    args={'json':{'action':'drain','expected_generation':0}} if method=='post' else {}
                    response=getattr(self.client,method)('/api/platform/maintenance',**args)
                    self.assertEqual(response.status_code,code)
                    self.permission.assert_called_with('platform.recovery.manage')
                    self.engine.begin.assert_not_called(); self.engine.connect.assert_not_called()
    def test_authorized_action_uses_canonical_actor_and_exact_generation(self):
        with patch.object(self.routes,'transition',return_value={'state':'announced'}) as transition:
            response=self.client.post('/api/platform/maintenance',json={'action':'announce','expected_generation':7,'announcement':'Test maintenance'})
        self.assertEqual(response.status_code,200)
        self.permission.assert_called_once_with('platform.recovery.manage')
        self.assertEqual(transition.call_args.kwargs['actor_user_id'],'canonical-test-actor')
        self.assertEqual(transition.call_args.kwargs['expected_generation'],7)
    def test_public_authenticated_status_exposes_no_admin_or_household_details(self):
        self.engine.connect.return_value.__enter__=Mock(return_value=Mock())
        self.engine.connect.return_value.__exit__=Mock(return_value=False)
        with patch.object(self.routes,'state',return_value={'state':'announced','announcement':'Test maintenance','active_operations':99,'cycle_id':'private-test-cycle','restart_allowed':True}):
            response=self.client.get('/api/maintenance/status')
        self.assertEqual(response.json(),{'state':'announced','announcement':'Test maintenance'})
        self.permission.assert_not_called(); self.session.assert_called_once()
