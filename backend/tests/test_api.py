from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Config
from test_domain import event


def test_api_lifecycle_security_history_config(tmp_path):
    app = create_app(Config(data_dir=str(tmp_path)))
    with TestClient(app) as c:
        assert len(c.get('/api/snapshot').json()['tables']) == 24
        assert c.post('/api/sim/action', json={'action': 'burst'}, headers={'Origin': 'https://evil.example'}).status_code == 403
        r = c.post('/api/sim/event', json=event().model_dump()).json()['request']
        def action(kind, **extras):
            nonlocal r
            response = c.post(f'/api/requests/{r["id"]}/{kind}', json=dict(expected_version=r['version'], idempotency_key=str(uuid4()), **extras))
            assert response.status_code == 200, response.text
            r = response.json()
        action('ack')
        action('assign', staff_id=1)
        assert len(c.get('/api/staff/1/inbox').json()) == 1
        action('accept', staff_id=1, revision=1)
        assert c.post(f'/api/requests/{r["id"]}/done', json={}).status_code == 404
        assert c.post('/api/sim/event', json=event('DONE').model_dump()).json()['request']['state'] == 'COMPLETED'
        assert c.get('/api/history?state=COMPLETED&table_id=1').json()['total'] == 1
        assert c.get('/api/history?staff_id=2').json()['total'] == 0
        assert c.post('/api/config/tables', json={'id': 1, 'node_id': 1, 'name': '=SUM(A1)'}).status_code == 200
        assert "'=SUM(A1)" in c.get('/api/export.csv').text
        assert c.get('/api/health').json()['status'] == 'ok'
        assert c.post('/api/sim/action', json={'action': 'reset'}).status_code == 422
        assert c.post('/api/sim/action', json={'action': 'reset', 'confirm': 'RESET DEMO'}).status_code == 200
        assert c.get('/api/history').json()['total'] == 0


def test_hardware_no_sim_isolation_and_staff_identity(tmp_path):
    demo = create_app(Config(data_dir=str(tmp_path)))
    with TestClient(demo) as c:
        c.post('/api/sim/event', json=event().model_dump())
    app = create_app(Config(mode='hardware', data_dir=str(tmp_path), staff_token='test-secret'))
    with TestClient(app) as c:
        assert c.get('/api/snapshot').json()['tables'] == []
        assert c.get('/api/snapshot').json()['requests'] == []
        assert c.post('/api/sim/event', json=event().model_dump()).status_code == 404
        assert c.post('/api/sim/action', json={'action': 'burst'}).status_code == 404
        assert c.get('/api/staff/1/inbox').status_code == 403
        assert c.get('/api/staff/2/inbox', headers={'x-staff-token': 'test-secret'}).status_code == 403
        assert c.get('/api/staff/1/inbox', headers={'x-staff-token': 'test-secret'}).status_code == 200
        assert c.get('/api/health', headers={'Host': 'example.com'}).status_code == 403
