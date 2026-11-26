"""Thinking-model tool replay through the OpenAI-compatible wire adapter."""
import json

import httpx
import pytest

from test_experiment_conversation import application, machine_for
from test_experiments import workspace
from backend.database import connect_database
from spectrumagent.agent import experiment_flow, inference_flow, llm, workflow
from spectrumagent.agent.state import AgentStore


@pytest.mark.parametrize(('flow', 'tool'), [
    (experiment_flow, 'experiments.draft_get'),
    (inference_flow, 'experiments.inference_get'),
    (workflow, 'datasets.list'),
])
def test_reasoning_replays_only_within_current_user_turn(application, monkeypatch, flow, tool):
    database = application.state.experiments.paths.database
    session = AgentStore(database).create_session()['id']
    llm.write_settings(database, llm.LLMSettings(base_url='https://model.example/v1', model='mock'))
    key = 'test-secret-key'
    monkeypatch.setattr(llm._credentials, 'key', key)
    verbatim = '  先查草稿\n再核验必要字段  '
    private = '私有标记：读取 E:\\private\\sample.npz。密钥为 ' + key
    final_reasoning = '最终内部思考'
    requests = []

    def mock(request):
        body = json.loads(request.content)
        requests.append(body['messages'])
        step = len(requests)
        if step <= 2:
            wire_name = next(item['function']['name'] for item in body['tools']
                             if item['function']['name'] in {tool, 'sa_' + tool.replace('.', '__')})
            message = {
                'content': None,
                'reasoning_content': verbatim if step == 1 else private,
                'tool_calls': [{
                    'id': f'call_{step}', 'type': 'function',
                    'function': {'name': wire_name, 'arguments': '{}'},
                }],
            }
        else:
            message = {'content': '已完成查询。'}
            if step == 3:
                message['reasoning_content'] = final_reasoning
        return httpx.Response(200, json={'choices': [{
            'message': message, 'finish_reason': 'tool_calls' if step <= 2 else 'stop',
        }]})

    model = llm.OpenAICompatibleClient(database, transport=httpx.MockTransport(mock), session_id=session)
    machine = machine_for(application, session, model)
    events = list(flow.generate(machine, content='请帮我整理一下当前的信息'))
    events += list(flow.generate(machine, content='请再整理一下有哪些信息'))
    assert all(kind != 'error' for kind, _ in events), events
    assert len(requests) == 4
    assert all('reasoning_content' not in message for message in requests[0])
    assert [(m['tool_calls'][0]['id'], m['reasoning_content']) for m in requests[1] if m.get('tool_calls')] == [
        ('call_1', verbatim),
    ]
    replayed = [m for m in requests[2] if m.get('tool_calls')]
    assert [m['tool_calls'][0]['id'] for m in replayed] == ['call_1', 'call_2']
    assert replayed[0]['reasoning_content'] == verbatim
    assert 'reasoning_content' in replayed[1]
    assert 'private' not in replayed[1]['reasoning_content'] and key not in replayed[1]['reasoning_content']
    assert [m['tool_calls'][0]['id'] for m in requests[3] if m.get('tool_calls')] == ['call_1', 'call_2']
    assert all('reasoning_content' not in message for message in requests[3])
    with connect_database(database) as db:
        persisted = '\n'.join(db.iterdump())
    exposed = persisted + json.dumps(events, ensure_ascii=False)
    assert all(marker not in exposed for marker in (verbatim, '私有标记', final_reasoning, 'reasoning_content', key))
