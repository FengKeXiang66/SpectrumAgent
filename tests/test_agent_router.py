"""The classification call is isolated from tools, paths, and numerical inputs."""
import json
from types import SimpleNamespace

import httpx
import pytest

from test_experiment_conversation import application, machine_for, ScriptedModel, tool, workspace
from backend.database import connect_database
from spectrumagent.agent import router, workflow
from spectrumagent.agent.llm import ChatResult, LLMError, LLMSettings, OpenAICompatibleClient, _DENY_TEXT, read_settings, restore_settings, write_settings
from spectrumagent.agent.state import AgentStore


@pytest.mark.parametrize('prior', [[], [{'role':'assistant','content':'你也可以先去设置页登记数据源。'}]])
def test_general_dialogue_prompt_distinguishes_local_experiment_from_canvas(prior):
    machine = SimpleNamespace(_history_messages=lambda version, **kwargs: prior)
    version = {'system_prompt':'已保存的系统提示', 'examples_json':'[]'}
    messages = workflow._messages(machine, version, {'current_datasets': []},
                                  '我有本地高光谱数据，想训练塑料分类模型。', None)
    prompt = next(row['content'] for row in messages if row['role']=='system' and '路线 A' in row['content'])
    assert _DENY_TEXT.search(prompt) is None
    intro, a = prompt.split('2. 通用导入', 1)
    a, b = a.split('3. 路线 B', 1)
    b, consistency = b.split('4. ', 1)
    assert all(text in intro for text in ('source_hdr', '只读配对', '分组划分', '波长对齐', 'Study', '批量推理', '再问用户'))
    assert all(text in a for text in ('外部 ROI 标注 JSON', '训练和测试 NPZ', '无需到设置页登记数据源',
                                      '无需调用 sources.scan 或 datasets.import', '粘贴本地文件或目录路径',
                                      '「选择目录」', '「选择文件」', '脱敏为内部引用'))
    assert all(text in a for text in ('数据接入卡片', '尚未标注或已有标注', '不要求用户重做超像素', '不要在导入或查看数据时强制要求'))
    assert all(text in b for text in ('未标注原图', '不能要求路径导入用户先去设置页', 'sources.scan 和 datasets.import', '超像素画布标注'))
    assert '不能据此要求路线 A 先登记' in consistency
    assert messages[0]['content']==version['system_prompt']
    assert all(row in messages for row in prior)


class RoutingModel(ScriptedModel):
    def __init__(self, response, *replies):
        super().__init__(*replies)
        self.response = response
        self.routing_requests = []

    def route_chat(self, messages, control=None):
        self.routing_requests.append(messages)
        if isinstance(self.response, Exception):
            raise self.response
        return ChatResult(content=self.response,finish_reason='stop')


@pytest.mark.parametrize('intent,text,mode',[
    ('study_tune','针对这一轮实验做预处理和参数调试','study'),
    ('paired_to_training','拿刚才配对好的数据建模','paired_training'),
    ('experiment_draft_edit','PET 为什么全错分了顺便改改方案','explain_with_edit'),
])
def test_router_uses_original_locally_and_only_sends_safe_classification(application, monkeypatch,intent,text,mode):
    base = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(base.database).create_session()['id']
    with connect_database(base.database) as db:
        db.execute("UPDATE agent_session SET title=? WHERE id=?",('仅侧栏显示的会话标题',owner))
    model = RoutingModel(json.dumps({'intent':intent,'explain_result':mode=='explain_with_edit','confidence':'high'}))
    captured = []
    def route_target(machine, raw, **flags):
        captured.append((raw,flags))
        return iter(())
    monkeypatch.setattr(router,'experiment',route_target)
    machine = machine_for(application,owner,model)
    raw = text + r'，D:\my secret folder\private.npz，private-set.csv，private-meta.yaml，X=[[0.12345,0.23456],[0.34567,0.45678]]'
    list(machine.message(content=raw))
    assert len(model.routing_requests)==1 and captured[0][0]==raw
    assert captured[0][1][mode]
    payload = json.loads(model.routing_requests[0][-1]['content'])
    assert text in payload['text']
    assert len(payload['state'])==8
    assert '仅侧栏显示的会话标题' not in json.dumps(model.routing_requests,ensure_ascii=False)
    assert not any(token in payload['text'] for token in ('private','secret','0.12345','0.45678','D:'))


@pytest.mark.parametrize('stage,paired,focus,target,expected', [
    ('imported', False, None, '', {'workspace_training': True}),
    ('cancelled', False, None, '', {'study': True}),
    ('imported', True, None, '', {'paired_training': 'offer'}),
    ('imported', True, ('experiment', 'focused', None), '', {'study': True}),
    ('imported', True, None, '基于 8e8d7bc2-d0dd-44e0-927c-92ad9706942a ', {'study': True}),
])
def test_study_route_respects_existing_sources(monkeypatch, stage, paired, focus, target, expected):
    intake = SimpleNamespace(
        read=lambda owner: {'stage': stage, 'imported_ids': ['cube']},
        generate=lambda *args: {'workspace_training': True},
    )
    machine = SimpleNamespace(session_id='owner', tools=SimpleNamespace(data_intake=intake))
    dialogue = SimpleNamespace(_read=lambda owner: {'document': {}}, focus=lambda owner: focus,
                               has_paired_inputs=lambda owner: paired)
    monkeypatch.setattr(router, 'classify', lambda *args: router.Route(
        intent='study_tune', explain_result=False, confidence='high'))
    monkeypatch.setattr(router, 'experiment', lambda *args, **flags: flags)
    assert router.dispatch(machine, dialogue, target+'发起寻优') == expected


def test_confirm_buttons_bypass_router_and_invalid_router_falls_back(application,monkeypatch):
    owner = AgentStore(application.state.experiments.paths.database).create_session()['id']
    selected = []
    def route_target(machine, raw, **flags):
        selected.append((raw,flags))
        return iter(())
    monkeypatch.setattr(router,'experiment',route_target)
    monkeypatch.setattr(router,'inference',route_target)
    model = RoutingModel('unparseable provider output')
    machine = machine_for(application,owner,model)
    for command in ('确认执行','确认寻优','确认探索性寻优','确认推理','取消推理','取消寻优','采用波长建议 3','查看当前实验方案',
                    '用本次配对结果新建训练方案','采用候选 2新建正式训练','配对明细 第1页'):
        list(machine.message(content=command))
    assert not model.routing_requests and len(selected)==11
    for invalid in (model, RoutingModel('{"intent":"study_tune","explain_result":false,"confidence":"low"}'),
                    RoutingModel(LLMError('LLM_TRANSPORT','transport_error'))):
        list(machine_for(application,owner,invalid).message(content='帮我寻优'))
        assert selected[-1][1]=={'study':True}
    offline = ScriptedModel()
    list(machine_for(application,owner,offline).message(content='帮我寻优'))
    assert selected[-1][1]=={'study':True}


def test_router_model_override_and_audit(application, monkeypatch):
    from spectrumagent.agent import llm
    from spectrumagent.agent.execution import RequestControl

    monkeypatch.setattr(llm, '_credentials', llm._Credentials())
    llm.set_api_key('primary-test-key')
    database = application.state.experiments.paths.database
    requests = []
    def mock(request):
        requests.append(request)
        return httpx.Response(200, json={'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]})
    client = OpenAICompatibleClient(database,transport=httpx.MockTransport(mock))
    main = 'https://main.example.test/v1'
    separate = 'https://route.example.test/v1'
    cases = (
        ('', '', '', 'main-model', main, 'primary-test-key'),
        ('router-small', '', '', 'router-small', main, 'primary-test-key'),
        ('router-small', '', 'router-test-key', 'router-small', main, 'primary-test-key'),
        ('', main + '/', '', 'main-model', main, 'primary-test-key'),
        ('router-small', main, 'router-test-key', 'router-small', main, 'router-test-key'),
        ('router-small', separate, 'router-test-key', 'router-small', separate, 'router-test-key'),
        ('router-small', separate, '', 'router-small', separate, None),
        ('router-small', main + '/other', '', 'router-small', main + '/other', None),
    )
    for model, address, key, expected_model, expected_address, expected_key in cases:
        llm.set_router_api_key(key)
        write_settings(database, LLMSettings(base_url=main, model='main-model', router_model=model,
                                             router_base_url=address, temperature='0.7',
                                             max_tokens='2048', timeout_ms='12000'))
        messages = [{'role':'user','content':'自动比较参数'}]
        for control in (None, RequestControl('test-route')):
            client.route_chat(messages, control=control)
            request = requests[-1]
            payload = json.loads(request.content)
            assert str(request.url) == expected_address + '/chat/completions'
            assert request.headers.get('authorization') == ('Bearer ' + expected_key if expected_key else None)
            assert payload['model'] == expected_model and payload['temperature'] == 0 and payload['max_tokens'] == 512
            assert not payload.get('tools') and set(request.extensions['timeout'].values()) == {8.0}
    llm.set_router_api_key('router-test-key')
    write_settings(database, LLMSettings(base_url=main, model='main-model', router_base_url=separate))
    client.chat(messages, [])
    assert str(requests[-1].url) == main + '/chat/completions'
    assert requests[-1].headers['authorization'] == 'Bearer primary-test-key'
    client.chat(messages, [], base_url=separate)
    assert 'authorization' not in requests[-1].headers
    with connect_database(database) as db:
        assert {row[0] for row in db.execute('SELECT model FROM llm_call')}=={'main-model','router-small'}
        assert all('primary-test-key' not in line and 'router-test-key' not in line for line in db.iterdump())
    write_settings(database, LLMSettings(router_base_url=separate, router_model='router-small'))
    client.route_chat(messages)
    assert str(requests[-1].url) == separate + '/chat/completions'
    count = len(requests)
    write_settings(database,LLMSettings(egress_enabled=False))
    assert client.route_chat([{'role':'user','content':'训练'}]) is None
    assert len(requests) == count


@pytest.mark.parametrize('legacy_model', ['', 'older-router'])
def test_pre_router_settings_snapshot_restores_without_migration_loss(application,tmp_path,legacy_model):
    from spectrumagent.agent.migrations import migrate
    from spectrumagent.agent.settings_store import config_path
    database = application.state.experiments.paths.database
    path = config_path(tmp_path)
    path.parent.mkdir(parents=True)
    legacy = LLMSettings(base_url='https://example.test/v1', model='main-model', router_model=legacy_model,
                         temperature='0.3', max_tokens='2048', timeout_ms='9000',
                         egress_enabled=False).model_dump(exclude={'router_base_url'})
    if not legacy_model:
        legacy.pop('router_model')
    path.write_text(json.dumps(legacy),'utf8')
    with connect_database(database) as db:
        db.execute("DELETE FROM llm_settings WHERE key='router_base_url'")
        migrate(db)
        migrate(db)
    assert restore_settings(database,tmp_path)
    assert read_settings(database).model_dump() == {**legacy, 'router_model':legacy_model, 'router_base_url':''}


def test_crop_text_reaches_normal_npz_edit(application):
    base = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(base.database).create_session()['id']
    from spectrumagent.agent.tools.experiments import DraftUpdate
    base.capture(owner,'训练数据和测试数据')
    base.update(owner,DraftUpdate.model_validate({'expected_revision':base._read(owner)['revision'],'name':'NPZ 草稿',
                                                 'train':{'kind':'npz'}}))
    model=ScriptedModel(ChatResult(content='请先确认是否重新映射 NPZ 的波长轴',finish_reason='stop'))
    events=list(machine_for(application,owner,model).message(content='把目标波长改为 1105–1115 nm'))
    assert model.requests and '已过期' not in str(events)


def test_router_history_opens_recent_report_and_uses_compare_tool(application, tmp_path):
    from test_experiments import config_for
    from spectrumagent.experiments.schema import ExperimentConfig

    service = application.state.experiments
    owner = AgentStore(service.paths.database).create_session()['id']
    config = config_for(tmp_path)
    earlier = service.run(ExperimentConfig.model_validate(config))['experiment_id']
    config['name'] = '最近实验'
    latest = service.run(ExperimentConfig.model_validate(config))['experiment_id']
    response = '{"intent":"experiment_history","explain_result":false,"confidence":"high"}'
    model = RoutingModel(response, tool('experiments.history_compare', {'first_id':latest,'second_id':earlier}))
    machine = machine_for(application, owner, model)

    events = list(machine.message(content='打开最近一次实验报告'))
    assert events[-1][1]['task_result'] == 'succeeded'
    assert any(kind=='step' and data['tool']=='experiments.history_select'
               and data['result_summary']['archived_experiment_id']==latest for kind,data in events)
    assert len(model.routing_requests)==1 and not model.requests

    events = list(machine.message(content='对比上次和上上次实验'))
    assert any(kind=='step' and data['tool']=='experiments.history_compare' and data['status']=='ok' for kind,data in events)
    assert events[-1][1]['task_result']=='succeeded' and '测试准确率' in events[-1][1]['content']
    assert len(model.routing_requests)==2 and len(model.requests)==1


def test_router_accepts_only_a_single_json_fence(application):
    dialogue = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(dialogue.database).create_session()['id']
    payload = '{"intent":"study_tune","explain_result":false,"confidence":"high"}'
    for tag in ('json',''):
        model = RoutingModel(f'  ```{tag}\n{payload}\n```  ')
        route = router.classify(machine_for(application,owner,model),dialogue,'帮我寻优',None)
        assert route is not None and route.intent=='study_tune'

    for response in (f'说明\n```json\n{payload}\n```', f'```json\n{payload}\n```\n说明',
                     f'```json\n{payload}\n```\n```json\n{payload}\n```',
                     '```json\n{"intent":invalid}\n```'):
        model = RoutingModel(response)
        assert router.classify(machine_for(application,owner,model),dialogue,'帮我寻优',None) is None


def test_router_normalizes_spectral_and_chinese_slashes_but_blocks_relative_paths(application):
    dialogue = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(dialogue.database).create_session()['id']
    model = RoutingModel('{"intent":"study_tune","explain_result":false,"confidence":"high"}')
    machine = machine_for(application,owner,model)
    route = router.classify(machine,dialogue,'用训练/测试方案比较SG1/SG2、L2/SNV和PE/PP/PET/EPS',None)
    assert route is not None and route.intent=='study_tune'
    payload = json.loads(model.routing_requests[0][-1]['content'])
    assert payload['text'] == '用训练、测试方案比较SG1、SG2、L2、SNV和PE、PP、PET、EPS'

    for path in ('secret/folder','PE/PET/secret','secret/训练/测试'):
        route = router.classify(machine,dialogue,f'用训练/测试方案比较SG1/SG2，来源 {path}',None)
        assert route is None
    assert len(model.routing_requests)==1
