"""Classify an intent without giving the router any tools or execution authority."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from spectrumagent.experiments import group_split, pairing, pairing_intake, study, wavelength_proposal
from spectrumagent.experiments.conversation import PATHS, CONFIRM, CANCEL, EXPLAIN_RESULT, HISTORY, PARAMETER_EDIT, RETRAIN, START
from spectrumagent.experiments import inference_dialogue as infer
from .experiment_flow import generate as experiment
from .inference_flow import generate as inference
from .llm import ABSOLUTE_FRAGMENT, LLMError, _DENY_TEXT, _egress_blocked, _json


class Route(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    intent: Literal['pairing_intake','pairing_preview','paired_to_training','group_split','study_tune',
                    'experiment_draft_edit','experiment_explain','experiment_history','inference',
                    'annotation_workspace','general_qa']
    explain_result: bool
    confidence: Literal['high','low']


PROMPT = """
只做意图分类，返回恰好一个 JSON 对象，字段 intent、explain_result、confidence。
intent 取值：
pairing_intake 收集或修正 ENVI 和外部标注目录；
pairing_preview 请求检查目录或看配对结果；paired_to_training 用已配对数据新建训练草稿；
group_split 重新按组划分训练测试；study_tune 让程序自动比较或寻找预处理和模型参数；
experiment_draft_edit 手动改实验参数、准备新训练或重训；
experiment_explain 解释已有结果、错分、指标；
experiment_history 查询归档或历史实验；
inference 用训练好的模型预测、配置前景或查推理；annotation_workspace 画布、标注、数据工作台；
general_qa 普通咨询。将“为什么错分而且要改一下方案”分类为 experiment_draft_edit 且 explain_result 为 true。
没有明确授权时只选建议相关的问题，不把讨论解释成执行。确认动作由本机单独处理。
confidence 只能为 high 或 low，信息不够选 low。explain_result 必须为 JSON 布尔值。
不输出额外字段、参数、确认、工具调用或改写后的用户文本。
"""
FILE_NAME = re.compile(r"""(?i)["“‘'][^"”’'\r\n]+\.[a-z][a-z0-9]{0,9}["”’']|"""
                       r"""[^\s，,。；;、：:（）()<>“”"']+\.[a-z][a-z0-9]{0,9}\b""")
SPECTRA = re.compile(r'\[[^\[\]\r\n]*\d[^\[\]\r\n]*\]|'
                     r'(?<!\w)[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'
                     r'(?:\s*[,，;；、\s]\s*[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)+')
NUMBER = re.compile(r'(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?')
JSON_FENCE = re.compile(r'```(?:json)?[ \t]*\r?\n(.*?)\r?\n[ \t]*```', re.IGNORECASE | re.DOTALL)
HAN_SLASH = re.compile(r'(?<=[\u3400-\u4dbf\u4e00-\u9fff])/(?=[\u3400-\u4dbf\u4e00-\u9fff])')
SPECTRAL_TERM = r'(?:SG1|SG2|L2|SNV|PE|PP|PET|EPS)'
SPECTRAL_TERM_LIST = re.compile(
    rf'(?<![A-Za-z0-9_./\\-]){SPECTRAL_TERM}(?:/{SPECTRAL_TERM})+(?![A-Za-z0-9_./\\-])', re.IGNORECASE,
)


def classify(machine, dialogue, content, workspace):
    route_chat = getattr(machine.llm,'route_chat',None)
    if not callable(route_chat):
        return None
    owner = machine.session_id
    # The oversized-message fallback also avoids sending pasted arrays to the router.
    if len(content)>3000:
        return None
    safe = ABSOLUTE_FRAGMENT.sub(' 本地输入源 ', content)
    safe = FILE_NAME.sub(' 本地文件 ', safe)
    # Only normalize known prose separators before the path guard.
    safe = HAN_SLASH.sub('、', safe)
    safe = SPECTRAL_TERM_LIST.sub(lambda match: match[0].replace('/', '、'), safe)
    safe = SPECTRA.sub(' 数值数据 ', safe)
    # The classifier only needs verbs and domain nouns. Remove remaining numerical values.
    safe = NUMBER.sub('数值', dialogue.redact(owner,safe)).strip()
    if not safe or _DENY_TEXT.search(safe) or _egress_blocked(safe):
        return None
    record = dialogue._read(owner) or {}
    confirmation = dialogue.confirmation(owner)
    scope = {
        'has_pairing_preview':bool(dialogue.pairing_preview_id(owner)),
        'has_pairing_intake_draft':bool(pairing_intake.draft(dialogue.database,owner).get('listening')),
        'has_experiment_draft':bool(record.get('document')),
        'draft_run_status':record.get('run_status'),
        'pending_confirmation_flow':confirmation[0] if confirmation else None,
        'has_archived_experiments':bool(dialogue.service.archive.folders()),
        'has_inference_draft':bool((dialogue.inference.read(owner) or {}).get('active')),
        'selected_cube_present':bool((workspace or {}).get('cube_id')),
    }
    messages = [{'role':'system','content':PROMPT},{'role':'user','content':_json({'text':safe,'state':scope})}]
    control = getattr(machine,'control',None)
    if control is not None:
        control.begin('model')
    try:
        result = route_chat(messages,control=control)
        if result is None or result.tool_calls or result.finish_reason in {'length','max_tokens'}:
            return None
        response = (result.content or '').strip()
        fence = JSON_FENCE.fullmatch(response)
        route = Route.model_validate_json(fence[1] if fence else response)
        return route if route.confidence == 'high' else None
    except (LLMError, ValidationError, AttributeError, TypeError):
        return None


def direct(machine, dialogue, content):
    text = content.strip()
    bare = text.strip(' 。！!')
    owner = machine.session_id
    if (wavelength_proposal.ADOPT.fullmatch(text) or bare == '查看当前实验方案'
            or wavelength_proposal.CROP.fullmatch(text) and dialogue.can_crop_wavelength(owner)):
        return experiment(machine,content,wavelength_action=True)
    if (wavelength_proposal.AUTO_STUDY.fullmatch(text) or study.ADOPT.fullmatch(text)
            or study.QUERY.fullmatch(text) or study.CONFIRM.fullmatch(text) or bare == '取消寻优'):
        return experiment(machine,content,study=True)
    if bare == pairing.TRAIN_COMMAND:
        return experiment(machine,content,paired_training='load')
    train_confirmation, infer_confirmation = CONFIRM.fullmatch(text), infer.CONFIRM.fullmatch(text)
    if train_confirmation and infer_confirmation:
        target = dialogue.confirmation(owner)
        if target and target[0] == 'inference':
            return inference(machine,content,confirmation=target)
        if target and target[0] == 'study':
            return experiment(machine,content,study=True)
        return experiment(machine,content,confirmation=target,missing_confirmation=target is None)
    if infer_confirmation or infer.QUERY.fullmatch(text) or infer.CANCEL.fullmatch(text) or infer.probe_requested(text):
        return inference(machine,content)
    if train_confirmation or CANCEL.fullmatch(text):
        return experiment(machine,content)
    if pairing.PAGE.fullmatch(text) or pairing.REPLAY.match(text) or bare == pairing.PREPARE_REPLAY:
        return experiment(machine,content,pairing=True)
    if bare.startswith('配对预览') and PATHS.search(text):
        pairing_intake.save(dialogue.database,owner,{})
        return experiment(machine,content,pairing=True)
    semantic = PATHS.sub(' ',text)
    if (group_split.BASELINE.fullmatch(bare) or group_split.PAGE.fullmatch(semantic.strip())
            or bare in {group_split.CONFIRM,'查看划分方案'}):
        return experiment(machine,content,group_split=True)
    if bare in {pairing.APPROVE,pairing.EDIT}:
        action = pairing_intake.route(dialogue,owner,content)
        if action:
            return experiment(machine,content,pairing_intake_action=action)
    if re.fullmatch(r'基于此数据寻优\s+[0-9a-f-]{36}',bare):
        return experiment(machine,content,study=True)
    if bare == '查询实验结果':
        return experiment(machine,content)
    if bare == '解释测试混淆情况' or re.fullmatch(r'解释实验 [0-9a-f-]{36} 的测试混淆情况',bare):
        return experiment(machine,content,explain=True)
    return None


def dispatch(machine, dialogue, content, workspace=None):
    from spectrumagent.experiments.workspace_training import SPLIT
    record = dialogue._read(machine.session_id)
    if record and record['document'].get('workspace_selection') and SPLIT.fullmatch(content.strip()):
        return experiment(machine, content, workspace_split=True)
    local = direct(machine,dialogue,content)
    if local is not None:
        return local
    route = classify(machine,dialogue,content,workspace)
    if route is None:
        return fallback(machine,dialogue,content)
    owner = machine.session_id
    match route.intent:
        case 'pairing_intake' | 'pairing_preview':
            action = pairing_intake.route(dialogue,owner,content)
            return experiment(machine,content,pairing_intake_action=action or (
                'collect' if route.intent=='pairing_intake' else 'inspect'))
        case 'paired_to_training':
            return experiment(machine,content,paired_training='load')
        case 'group_split':
            return experiment(machine,content,group_split=True)
        case 'study_tune':
            if dialogue.has_paired_inputs(owner) and not (dialogue._read(owner) or {}).get('document') and not dialogue.focus(owner):
                return experiment(machine,content,paired_training='offer')
            return experiment(machine,content,study=True)
        case 'experiment_draft_edit':
            source_supplied = bool(PATHS.search(content))
            return experiment(machine,content,retrain=not source_supplied and bool(
                (dialogue._read(owner) or {}).get('document') or dialogue.focus(owner)),
                explain_with_edit=route.explain_result)
        case 'experiment_explain':
            return experiment(machine,content,explain=True)
        case 'experiment_history':
            return experiment(machine,content)
        case 'inference':
            return inference(machine,content)
        case _:
            return None


def fallback(machine, dialogue, content):
    """Local compatibility for offline sessions and unavailable classifiers."""
    owner = machine.session_id
    text = content.strip()
    semantic = PATHS.sub('输入源',text)
    has_paths = bool(PATHS.search(text))
    if group_split.requested(content,PATHS):
        pairing_intake.save(dialogue.database,owner,{})
        return experiment(machine,content,group_split=True)
    if action := pairing_intake.route(dialogue,owner,content):
        return experiment(machine,content,pairing_intake_action=action)
    if pairing.requested(content,PATHS):
        pairing_intake.save(dialogue.database,owner,{})
        return experiment(machine,content,pairing=True)
    if re.fullmatch(r'(?:请|帮我)?(?:用|根据|基于)(?:这批|这次|本次)(?:配对|配对结果|配对数据)(?:来)?(?:建模|训练|新建训练方案)',text.strip(' 。！!')):
        return experiment(machine,content,paired_training='load')
    if not has_paths and re.search(r'建模|训练|预处理|改参|调参|寻优|Study',text,re.I) and not re.search(r'归档|历史|[0-9a-f]{8}-',text,re.I):
        prior = machine.store.rounds(owner,limit=1)
        after_preview = prior and (prior[-1]['assistant_content'] or '').startswith('ENVI 原图与标注配对预览')
        if (after_preview or not (dialogue._read(owner) or {}).get('document')) and dialogue.has_paired_inputs(owner):
            return experiment(machine,content,paired_training='offer')
    if study.requested(semantic):
        return experiment(machine,content,study=True)
    edit = RETRAIN.search(semantic) and not re.search(r'不(?:要|用)?重(?:新训|训)|不(?:要|用)?再训',semantic)
    explain = bool(EXPLAIN_RESULT.search(semantic))
    if edit or PARAMETER_EDIT.search(semantic) and (explain or has_paths or dialogue._read(owner) or dialogue.focus(owner)):
        return experiment(machine,content,retrain=not has_paths,explain_with_edit=explain)
    if explain and not has_paths:
        return experiment(machine,content,explain=True)
    if infer.INTENT.search(semantic) or dialogue.inference.handles(owner,content):
        return inference(machine,content)
    if HISTORY.search(semantic) or START.search(semantic) and has_paths or dialogue.handles(owner,content):
        return experiment(machine,content,explain_with_edit=explain and has_paths)
    return None
