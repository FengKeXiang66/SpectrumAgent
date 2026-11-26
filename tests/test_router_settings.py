"""Settings HTTP boundary and independent encrypted router credential slot."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from test_experiments import workspace
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.agent import credential_store, llm, settings_store
from spectrumagent.api import settings as settings_api
from spectrumagent.app import create_app


SETTINGS = '/api/v1/settings/llm'


@pytest.mark.parametrize('address', [
    'file:///tmp', 'https://user:password@route.example.test/v1',
    'https://route.example.test/v1?key=bad', 'https://route.example.test/v1#fragment',
    'https://route.example.test:bad/v1', 123,
])
def test_router_address_uses_main_url_constraints(address):
    with pytest.raises(ValueError):
        llm.LLMSettings(router_base_url=address)


def test_independent_verification_uses_router_endpoint(workspace, monkeypatch):
    monkeypatch.delenv('SPECTRUMAGENT_PERMANENT_ROOT', raising=False)
    monkeypatch.setattr(llm, '_credentials', llm._Credentials())
    llm.set_api_key('main-probe-key')
    identity = EngineIdentity()
    requests = []
    def mock(request):
        requests.append(request)
        if 'authorization' not in request.headers:
            return httpx.Response(401, json={'error':'remote provider response'})
        return httpx.Response(200, json={'choices':[{'message':{'content':'ready'}, 'finish_reason':'stop'}]})

    monkeypatch.setattr(settings_api, 'OpenAICompatibleClient',
                        lambda db, **kw: llm.OpenAICompatibleClient(db, transport=httpx.MockTransport(mock), **kw))
    main_url = 'https://main.example.test/v1'
    route_url = 'https://route.example.test/v1'
    config = {'base_url':main_url, 'model':'main-model', 'router_base_url':route_url, 'router_model':'small-model'}
    with TestClient(create_app(workspace, identity), headers={'Authorization': 'Bearer ' + identity.token}) as client:
        assert client.post(SETTINGS + '/verify-router').json()['status'] == 'unconfigured'
        receipt = client.put(SETTINGS, json=config).json()
        assert receipt['router_base_url'] == route_url and receipt['has_router_key'] is False
        assert client.put(SETTINGS, json={**config, 'router_api_key':'forbidden-body-key'}).status_code == 400
        result = client.post(SETTINGS + '/verify-router')
        assert result.json()['status'] == 'unavailable' and '鉴权失败' in result.json()['detail']
        assert 'authorization' not in requests[-1].headers
        assert str(requests[-1].url) == route_url + '/chat/completions'
        assert 'remote provider response' not in result.text and route_url not in result.text
        llm.set_router_api_key('router-probe-key')
        result = client.post(SETTINGS + '/verify-router')
        assert result.json()['status'] == 'available'
        assert requests[-1].headers['authorization'] == 'Bearer router-probe-key'
        assert json.loads(requests[-1].content)['max_tokens'] == 512
        assert 'router-probe-key' not in result.text and route_url not in result.text
        assert client.post(SETTINGS + '/verify').json()['status'] == 'available'
        assert str(requests[-1].url) == main_url + '/chat/completions'
        assert requests[-1].headers['authorization'] == 'Bearer main-probe-key'
        count = len(requests)
        client.put(SETTINGS, json={**config, 'egress_enabled':False})
        assert client.post(SETTINGS + '/verify-router').json()['status'] == 'disabled'
        assert len(requests) == count


@pytest.mark.skipif(not credential_store.available(), reason='Windows DPAPI required')
def test_router_key_is_encrypted_restored_and_cleared_independently(workspace, tmp_path, monkeypatch):
    root = tmp_path / 'permanent'
    monkeypatch.setenv('SPECTRUMAGENT_PERMANENT_ROOT', str(root))
    monkeypatch.setattr(llm, '_credentials', llm._Credentials())
    main_secret, route_secret = 'primary-fixture-secret', 'router-fixture-secret'
    config = {'base_url':'https://main.example.test/v1', 'model':'main',
              'router_base_url':'https://route.example.test/v1', 'router_model':'small'}
    def start(paths):
        paths.create_directories()
        identity = EngineIdentity()
        return TestClient(create_app(paths, identity), headers={'Authorization': 'Bearer ' + identity.token})

    with start(workspace) as client:
        assert client.put(SETTINGS, json=config).status_code == 200
        assert client.put(SETTINGS + '/key', json={'key':main_secret}).json() == {'has_key':True}
        primary = credential_store.credential_path(root).read_bytes()
        response = client.put(SETTINGS + '/router-key', json={'key':route_secret})
        assert response.json() == {'has_router_key':True}
        for serialized in (response.text, client.get(SETTINGS).text, settings_store.config_path(root).read_text('utf-8')):
            assert main_secret not in serialized and route_secret not in serialized
    slot = root / 'credentials' / 'llm_router_api_key.bin'
    ciphertext = slot.read_bytes()
    assert ciphertext.startswith(credential_store.MAGIC) and route_secret.encode() not in ciphertext
    assert credential_store.load(root, router=True) == route_secret
    assert credential_store.credential_path(root).read_bytes() == primary

    llm.set_api_key('')
    llm.set_router_api_key('')
    with start(AppPaths(tmp_path / 'restart')) as client:
        recovered = client.get(SETTINGS).json()
        assert recovered['has_key'] and recovered['has_router_key']
        assert all(recovered[field] == value for field, value in config.items())
        assert client.put(SETTINGS + '/router-key', json={'key':''}).json() == {'has_router_key':False}
    assert not slot.exists() and not llm.has_router_api_key()
    assert credential_store.credential_path(root).read_bytes() == primary
    llm.set_router_api_key('')
    with start(AppPaths(tmp_path / 'restart-after-clear')) as client:
        assert client.get(SETTINGS).json()['has_router_key'] is False
