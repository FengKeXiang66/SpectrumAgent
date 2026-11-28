"""Reviewed inference drafts; model parsing cannot submit numerical work."""
from copy import deepcopy
import json
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

import numpy as np
from pydantic import ValidationError

from backend.database import connect_database
from spectrumagent import projects
from spectrumagent.data import DataError
from .conversation import PATHS, merge
from .inference import InferenceConfig, InferenceService
from .inference_presentation import change_list, display_groups
from .exclusions import read_exclusions
from .service import read_json

INTENT = re.compile(r'推理|\binfer(?:ence)?\b|(?:用|使用|拿).{0,60}(?:模型|归档).{0,60}预测|(?:预测|判别)(?:这些|这批|下列|该目录)', re.I)
QUERY = re.compile(r'(?:请)?(?:查询|查看|打开|展示)?(?:本次|上次|最近)?推理(?:结果|进度)[。！!\s]*')
CONFIRM = re.compile(r'(?:请)?(?:确认(?:并)?(?:执行)?推理|开始推理|确认执行)[。！!\s]*')
CANCEL = re.compile(r'(?:取消|退出|停止)(?:本次|当前)?推理[。！!\s]*')
UUID = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b')
PROBE = re.compile(r'(?:探查前景|前景探查)(?:[：:\s]+(.+))?[。！!\s]*')
PROBE_ACTIONS = {'采用前景建议','关闭前景筛选'}
INLINE_PREFIX = '应用推理参数 '
NEW = re.compile(r'新建推理方案(?:\s+(\d+)(?:\s+([0-9a-f-]{36}))?)?[。！!\s]*')
READ_ONLY = '该方案已执行或已关闭，如需修改请新建推理方案。'


def probe_requested(content):
    text = content.strip(' 。！!')
    return text.startswith(INLINE_PREFIX) or text in PROBE_ACTIONS or PROBE.fullmatch(text)


def provided(value):
    """Nullable tool fields mean unspecified; saturation=null explicitly disables it."""
    if isinstance(value,dict):
        return {key:provided(item) for key,item in value.items() if item is not None or key=='saturation'}
    if isinstance(value,list):
        return [provided(item) for item in value]
    return value


class InferenceDialogue:
    def __init__(self, experiments):
        self.base, self.database = experiments, experiments.database
        self.service = InferenceService(experiments.service)
        self.lock = RLock()
        with connect_database(self.database) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS inference_draft (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id), revision INTEGER NOT NULL DEFAULT 0,
                document_json TEXT NOT NULL DEFAULT '{}', sources_json TEXT NOT NULL DEFAULT '{}',
                active INTEGER NOT NULL DEFAULT 1, reviewed_revision INTEGER, review_turn TEXT,
                review_json TEXT, run_id TEXT, previous_document_json TEXT)''')
            if 'previous_document_json' not in {row[1] for row in db.execute('PRAGMA table_info(inference_draft)')}:
                db.execute('ALTER TABLE inference_draft ADD COLUMN previous_document_json TEXT')
            db.execute('''CREATE TABLE IF NOT EXISTS inference_foreground_probe (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id), revision INTEGER NOT NULL, payload TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS inference_restart_request (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id), revision INTEGER NOT NULL,
                token TEXT NOT NULL, content TEXT NOT NULL)''')

    def read(self, owner):
        with connect_database(self.database) as db:
            row = db.execute('SELECT revision,document_json,sources_json,active,reviewed_revision,review_turn,review_json,run_id,previous_document_json '
                             'FROM inference_draft WHERE session_id=?', (owner,)).fetchone()
        if not row:
            return None
        return dict(zip(('revision','document','sources','active','reviewed_revision','review_turn','review','run_id','previous_document_json'),
                        (row[0],json.loads(row[1]),json.loads(row[2]),*row[3:])))

    def handles(self, owner, content):
        row = self.read(owner)
        semantic = PATHS.sub('输入源', content)
        return bool(CANCEL.fullmatch(content.strip()) or QUERY.fullmatch(content.strip())
                    or INTENT.search(semantic) or row and row['active'] and not row['run_id'])

    def capture(self, owner, content):
        with connect_database(self.database) as db:
            db.execute('INSERT OR IGNORE INTO inference_draft(session_id) VALUES (?)', (owner,))
        row = self.read(owner)
        if row['run_id'] or not row['active']:
            raise DataError('INFERENCE_DRAFT_READ_ONLY', READ_ONLY)
        for match in PATHS.finditer(content):
            value = match['quoted'] or match['bare']
            if value not in row['sources'].values():
                row['sources']['I'+str(len(row['sources'])+1)] = value
        # Explicit model UUIDs are extracted after paths have been removed.
        ids = UUID.findall(PATHS.sub('输入源', content))
        model_id = ids[0] if len(set(ids)) == 1 else None
        if not model_id and re.search(r'上次|刚才|最近|已选|当前模型|这个模型', content):
            model_id = self.base.selected(owner) if re.search(r'刚才|已选|当前模型|这个模型',content) else None
            candidates = self.base.service.archive.list(limit=50)['items']
            model_id = model_id or next((r['model_id'] for r in candidates if r.get('model_id')), None)
        if model_id and model_id != row['document'].get('model_id') and not row['run_id']:
            row['document']['model_id'] = model_id
            row['revision'] += 1
        with connect_database(self.database) as db:
            db.execute('UPDATE inference_draft SET sources_json=?,document_json=?,revision=?,active=(run_id IS NULL), '
                       'previous_document_json=CASE WHEN revision<>? THEN document_json ELSE previous_document_json END WHERE session_id=?',
                       (json.dumps(row['sources'],ensure_ascii=False),json.dumps(row['document'],ensure_ascii=False),
                        row['revision'],row['revision'],owner))
            if row['revision'] != row['reviewed_revision']:
                self.base.clear_confirmation(db, owner, 'inference')
        return self.redact(owner, content)

    def request_restart(self, owner, content):
        """Keep a new request separate from the submitted draft until chosen."""
        with self.lock, connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            projects.require(db, 'session', owner)
            row = self.read(owner)
            if not row or row['active'] and not row['run_id']:
                raise DataError('INFERENCE_DRAFT_CONFLICT', '推理草稿已更新，请重新打开当前方案')
            db.execute('INSERT OR REPLACE INTO inference_restart_request VALUES (?,?,?,?)',
                       (owner, row['revision'], str(uuid4()), content))

    def restart(self, owner, revision=None, token=None):
        """Create a new draft; never edit or remove the previous run's files."""
        with self.lock, connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            projects.require(db, 'session', owner)
            row = self.read(owner)
            if (not row or row['active'] and not row['run_id']
                    or revision is not None and revision != row['revision']):
                raise DataError('INFERENCE_DRAFT_CONFLICT', '推理草稿已更新，请重新打开当前方案')
            pending = db.execute('SELECT revision,token,content FROM inference_restart_request WHERE session_id=?', (owner,)).fetchone()
            if token and (not pending or pending[:2] != (row['revision'], token)):
                raise DataError('INFERENCE_DRAFT_CONFLICT', '新建请求已更新，请使用最新方案卡')
            content = pending[2] if pending and pending[0] == row['revision'] else None
            # A new supplied request must not silently reuse the old input.
            document = {'model_id':row['document'].get('model_id')} if content else deepcopy(row['document'])
            sources = {} if content else row['sources']
            db.execute('UPDATE inference_draft SET document_json=?,sources_json=?,revision=revision+1,active=1,'
                       'run_id=NULL,reviewed_revision=NULL,review_turn=NULL,review_json=NULL,previous_document_json=NULL WHERE session_id=?',
                       (json.dumps(document,ensure_ascii=False),json.dumps(sources,ensure_ascii=False),owner))
            db.execute('DELETE FROM inference_restart_request WHERE session_id=?', (owner,))
            db.execute('DELETE FROM inference_foreground_probe WHERE session_id=?', (owner,))
            self.base.clear_confirmation(db, owner, 'inference')
            return content

    def redact(self, owner, text, *, sources=None):
        if sources is None:
            sources = (self.read(owner) or {}).get('sources',{})
        for ref, path in sorted(sources.items(),key=lambda p:-len(p[1])):
            text = text.replace(json.dumps(path,ensure_ascii=False)[1:-1],ref).replace(path,ref)
        return PATHS.sub('本地输入源',text)

    def inspect(self, owner, ref):
        row = self.read(owner)
        path = Path(row['sources'].get(ref,''))
        if not path.is_absolute() or not path.exists():
            raise DataError('INFERENCE_INPUT_INVALID','输入源引用不存在或不可读')
        npzs = sorted(path.rglob('*.npz')) if path.is_dir() else ([path] if path.suffix.lower()=='.npz' else [])
        headers = sorted(path.rglob('*.hdr')) if path.is_dir() else ([path] if path.suffix.lower()=='.hdr' else [])
        result = {'source_ref':ref,'npz_files':len(npzs),'envi_files':len(headers)}
        if npzs:
            with np.load(npzs[0],allow_pickle=False) as data:
                for i,key in enumerate(data.files[:12],1):
                    result[f'field_{i}_name'] = self.redact(owner,key)
                    result[f'field_{i}_shape'] = ' × '.join(map(str,data[key].shape))
        return result

    def preset(self, model):
        for state in self.service.history(model):
            if state['status'] == 'succeeded' and state['kind'] == 'envi':
                data = read_json(self.service.artifact(model,state['run_id'],'config.json'))['input']
                return state['run_id'], {key:data[key] for key in
                                         ('wavelength_unit','mapping_window_nm','nearest_tolerance_nm','quality','foreground')}
        return None, {}

    def config(self, owner, *, for_probe=False, document=None):
        row = self.read(owner)
        doc = provided(deepcopy(row['document'] if document is None else document))
        spec = doc.get('input',{})
        refs = spec.pop('source_refs',[])
        spec['paths'] = [row['sources'][ref] for ref in refs]
        doc['input'] = spec
        if doc.get('model_id'):
            model = self.base.service.archive.model_metadata(doc['model_id'])
            train = self.base.service.get(doc['model_id'])['config']['train']
            if spec.get('kind') == 'npz':
                spec.setdefault('neighborhood',model['neighborhood'])
                spec.setdefault('evaluation_unit',model['evaluation_unit'])
            elif spec.get('kind') == 'envi':
                source = spec.pop('exclusions_ref',None)
                if source:
                    rules = read_exclusions(row['sources'][source]).model_dump()
                    supplied = spec.get('exclusions',{})
                    spec['exclusions'] = {
                        'prefixes':rules['prefixes']+supplied.get('prefixes',[]),
                        'name_fragments':rules['name_fragments']+supplied.get('name_fragments',[]),
                        'codes':{**rules['codes'],**supplied.get('codes',{})},
                    }
                _, previous = self.preset(doc['model_id'])
                defaults = ({key:train[key] for key in ('wavelength_unit','mapping_window_nm','nearest_tolerance_nm','quality')}
                            if train['kind']=='roi_images' else {})
                defaults.update(previous)
                spec = merge(defaults,spec)
                if spec.get('foreground',{}).get('mode')=='none':
                    spec['foreground'] = {'mode':'none'}
                if for_probe:
                    spec['foreground'] = {'mode':'none'}
                doc['input'] = spec
        return InferenceConfig.model_validate(doc)

    @staticmethod
    def _shown_config(config, document):
        shown = config.model_dump(mode='json')
        shown['input'].pop('paths')
        raw = document.get('input', {})
        shown['input']['source_refs'] = raw.get('source_refs',[])
        if 'exclusions_ref' in raw:
            shown['input']['exclusions_ref'] = raw['exclusions_ref']
        return shown

    def _presentation(self, owner, row, config, model, preset, question, previous_document):
        document = provided(row['document'])
        shown = self._shown_config(config, document) if config else document
        waiting = config is not None and config.input.kind=='envi' and not document['input'].get('foreground') and not preset
        groups = display_groups(shown,model,waiting)
        previous = previous_document
        if previous is None and row['previous_document_json']:
            previous = json.loads(row['previous_document_json'])
        changes = []
        if previous and provided(previous)!=document:
            previous = provided(previous)
            prior_model = model if previous.get('model_id') == document.get('model_id') else {}
            try:
                if previous.get('model_id') and not prior_model:
                    prior_model = self.base.service.archive.model_metadata(previous['model_id'])
                prior = self.config(owner,document=previous)
                prior_shown = self._shown_config(prior,previous)
                was_waiting = (prior.input.kind=='envi' and not previous['input'].get('foreground')
                               and not (preset if prior.model_id==document.get('model_id') else self.preset(prior.model_id)[0]))
            except (DataError,OSError,ValueError,KeyError):
                prior_shown,was_waiting = previous,False
            changes = change_list(display_groups(prior_shown,prior_model,was_waiting),groups)
        details = {'配置':shown}
        if model:
            details['模型 SHA-256'] = model['sha256']
            details['复用的模型参数'] = {key:model[key] for key in ('preprocessing','parameters','wavelengths_nm')}
        science = '复用已拟合模型。无真值标签时不输出准确率，PLS 响应不是概率。'
        if shown.get('input',{}).get('kind')=='envi':
            science += ' 整图邻域可能跨材质边界，前景筛除与闭集分类均不能识别未知类别。'
        def display(label, value):
            if label == '输入源':
                return '、'.join(f'{ref} · {Path(row["sources"][ref]).name}' if ref in row['sources'] else ref
                                for ref in value.split('、') if ref)
            return self.redact(owner,value,sources=row['sources'])
        return {
            'revision':row['revision'], 'ready':False, 'envi':shown.get('input',{}).get('kind')=='envi',
            'editable':bool(row['active'] and not row['run_id']),
            'state':'submitted' if row['run_id'] else 'draft' if row['active'] else 'closed',
            'run_id':row['run_id'],
            'foreground_enabled':shown.get('input',{}).get('foreground',{}).get('mode')=='brightness_edges',
            'todo':question,
            'groups': [{'title':title,'fields':[{'label':label,'value':display(label,pair[1])}
                        for label,pair in fields.items()]} for title,fields in groups.items()],
            'changes': [{**change, 'before':display(change['label'],change['before']),
                         'after':display(change['label'],change['after'])}
                        for change in changes],
            'raw':self.redact(owner,json.dumps(details,ensure_ascii=False,indent=2),sources=row['sources']),
            'science':science,
        }

    def view(self, owner, *, structured=False, previous_document=None):
        row = self.read(owner)
        if not row:
            return {'revision':0,'can_run':False,'plan':'尚未创建推理方案','question':'请提供归档模型与推理数据文件或目录。'}
        config, model, seed, question = None, {}, None, ''
        missing = []
        try:
            config = self.config(owner)
        except ValidationError as error:
            locations = [e['loc'] for e in error.errors(include_input=False)]
            fields = [' → '.join(map(str,location)) for location in locations]
            missing = [location[-1] for location in locations if location]
            question = '请补充或明确：'+'；'.join(fields)+ '。NPZ须确认数据字段、波长字段与已完成的输入阶段；ENVI缺少的映射/质量参数需要明确。'
        except (KeyError, ValueError, OSError, DataError):
            question = '模型或输入源尚未明确或不可读，请选择归档模型并提供有效数据来源。'
        plan = self.redact(owner,json.dumps(provided(row['document']),ensure_ascii=False,indent=2))
        if config:
            model = self.base.service.archive.model_metadata(config.model_id)
            shown = config.model_dump(mode='json')
            shown['input']['paths'] = [next((ref for ref,p in row['sources'].items() if p==value),'输入源') for value in config.input.paths]
            units={'center_pixel':'中心像元','spectrum':'光谱样本'}
            neighborhood=config.input.neighborhood if config.input.kind=='npz' else model['neighborhood']
            unit=config.input.evaluation_unit if config.input.kind=='npz' else model['evaluation_unit']
            lines=['模型：'+model['name']+'（'+config.model_id+'）',
                   '输入格式：'+('NPZ光谱矩阵' if config.input.kind=='npz' else 'ENVI原图'),
                   '输入源：'+'、'.join(shown['input']['paths']),
                   '空间邻域：'+str(neighborhood)+'×'+str(neighborhood)+'（模型要求'+str(model['neighborhood'])+'×'+str(model['neighborhood'])+'）',
                   '评价单位：'+units[unit]+('（沿用归档模型）' if unit==model['evaluation_unit'] else '（与归档模型要求的'+units[model['evaluation_unit']]+'不同）')]
            if config.input.kind=='npz':
                lines += ['光谱字段：'+config.input.spectra_key+'；波长字段：'+config.input.wavelengths_key,
                          '输入阶段：'+{'spectra':'未做空间平均的光谱矩阵','neighborhood_mean':'已完成邻域均值的光谱矩阵'}[config.input.input_stage]]
            else:
                lines += ['波长单位：'+config.input.wavelength_unit+'；映射窗口：'+str(config.input.mapping_window_nm)+' nm；最近通道容差：'+str(config.input.nearest_tolerance_nm)+' nm',
                          '质量筛选：'+json.dumps(config.input.quality.model_dump(),ensure_ascii=False)]
                fg=config.input.foreground
                lines.append('亮度与边缘前景筛选：未启用，仅按质量条件筛除。' if fg.mode=='none' else
                             '亮度与边缘前景筛选：'+json.dumps(fg.model_dump(),ensure_ascii=False))
                seed, _ = self.preset(config.model_id)
                if seed:
                    lines.append(f'可继承上次已核验的 ENVI 预设（推理 {seed[:8]}）。以上显示本次实际生效值。')
            plan='\n'.join(lines)
            plan += '\n复用训练时已拟合预处理：'+json.dumps(model['preprocessing'],ensure_ascii=False)
            plan += '\n只执行推理，不重新训练。无真值标签，不输出准确率；PLS响应不是概率。'
            if config.input.kind=='envi':
                plan += '\n整图推理无训练ROI材质隔离，邻域可能跨材质边界；只输出已知类别，未实现背景或未知类拒识。'
            question = '请核对模型、数据与方案；单独回复“确认推理”后执行。'
        if row['run_id']:
            question = '该方案已执行，当前为只读记录。如需修改请选择“新建推理方案”，或“查看上次推理结果”。'
        elif not row['active']:
            question = '该方案已关闭，当前为只读记录。如需修改请新建推理方案。'
        editable = bool(row['active'] and not row['run_id'])
        summary={'revision':row['revision'],'can_run':config is not None and editable,
                 'editable':editable,
                 'plan':plan,'question':question,'run_id':row['run_id']}
        try:
            probe = self.probe_result(owner)
            if probe['current']:
                summary['foreground_suggestion_json'] = json.dumps(probe['suggestion'],ensure_ascii=False)
        except DataError:
            pass
        if row['document'].get('model_id'):
            try:
                model = model or self.base.service.archive.model_metadata(row['document']['model_id'])
                summary.update(model_id=model['model_id'],model_neighborhood=model['neighborhood'],
                               model_evaluation_unit=model['evaluation_unit'])
            except (DataError,OSError,ValueError,KeyError):
                pass
        if structured:
            labels = {'model_id':'归档模型','input':'推理数据及格式','paths':'输入文件或目录','spectra_key':'光谱字段',
                      'wavelengths_key':'波长字段','input_stage':'光谱输入阶段','evaluation_unit':'评价单位','neighborhood':'空间邻域',
                      'wavelength_unit':'波长单位','mapping_window_nm':'映射窗口','nearest_tolerance_nm':'最近通道容差',
                      'quality':'质量筛选','min_mean':'最低均值','min_std':'最低标准差','max_zero_fraction':'零值比例上限',
                      'saturation':'饱和上限','foreground':'前景筛选','threshold':'亮度阈值','wavelengths_nm':'亮度探测波段',
                      'left_min':'左侧最少屏蔽列数','right_min':'右侧最少屏蔽列数','edge_search_columns':'边缘探查列数',
                      'edge_low':'边缘亮度下限','edge_high':'边缘亮度上限','edge_bad_fraction':'边缘异常比例'}
            todo = ('请补充或核对 '+ '、'.join(dict.fromkeys(labels.get(field,'输入设置') for field in missing))+'。'
                    if missing and not row['run_id'] else question)
            summary['presentation'] = self._presentation(owner,row,config,model,seed,todo,previous_document)
            if not editable:
                with connect_database(self.database) as db:
                    pending = db.execute('SELECT revision,token FROM inference_restart_request WHERE session_id=?', (owner,)).fetchone()
                command = f'新建推理方案 {row["revision"]}'
                if pending and pending[0] == row['revision']:
                    command += ' '+pending[1]
                    summary['presentation']['todo'] += ' 已暂存本次请求；选择新建后会使用本次提供的模型和数据。'
                summary['presentation']['restart_command'] = command
        return summary

    def apply_inline(self, owner, payload):
        from spectrumagent.agent.tools.inference import InlineInferenceAdjustment, InferenceUpdate
        from spectrumagent.data.validation import validation_error

        with self.lock:
            row = self.read(owner)
            if row and (row['run_id'] or not row['active']):
                raise DataError('INFERENCE_DRAFT_READ_ONLY', READ_ONLY)
            if not row or row['document'].get('input',{}).get('kind')!='envi':
                raise DataError('INFERENCE_PROBE_REQUIRED','请打开当前 ENVI 推理方案后再微调')
            try:
                adjustment = InlineInferenceAdjustment.model_validate_json(payload)
                patch = provided(adjustment.model_dump(mode='json',exclude_unset=True))
                revision = patch.pop('expected_revision')
                if revision!=row['revision']:
                    raise DataError('INFERENCE_DRAFT_CONFLICT','推理草稿已更新，请按当前方案重新填写')
                patch = {key:value for key,value in patch.items() if value}
                if not patch:
                    raise DataError('INFERENCE_ADJUSTMENT_EMPTY','请填写至少一个要修改的参数')
                # When the card already has effective foreground settings,
                # keep them as the base even if a newer probe is available.
                if patch.get('foreground',{}).get('mode')=='brightness_edges':
                    try:
                        current = self.config(owner)
                    except (ValidationError,KeyError):
                        current = None
                    if current and current.input.foreground.mode=='brightness_edges':
                        patch['foreground'] = merge(current.input.foreground.model_dump(mode='json'),patch['foreground'])
                update = InferenceUpdate(expected_revision=revision,input={'kind':'envi',**patch})
                return self.update(owner,update,validate_inline=True)
            except ValidationError as error:
                raise validation_error('TOOL_ARGS_INVALID',error) from None

    def update(self, owner, args, *, validate_inline=False):
        with self.lock:
            row = self.read(owner)
            if not row or args.expected_revision != row['revision']:
                raise DataError('INFERENCE_DRAFT_CONFLICT','推理草稿已更新，请读取最新修订')
            if (row['run_id'] or not row['active']) and not args.reset:
                raise DataError('INFERENCE_DRAFT_READ_ONLY', READ_ONLY)
            if row['run_id'] and self.service.status(row['document']['model_id'],row['run_id'])['status'] in {'queued','running'}:
                raise DataError('EXPERIMENT_BUSY','推理正在运行，不能修改其方案')
            patch = provided(args.model_dump(mode='json',exclude_unset=True))
            patch.pop('expected_revision');reset = patch.pop('reset',False)
            previous={} if reset else provided(row['document'])
            if reset and 'model_id' not in patch and row['document'].get('model_id'):
                previous['model_id']=row['document']['model_id']
            fg=patch.get('input',{}).get('foreground')
            if fg and fg.get('mode')!=previous.get('input',{}).get('foreground',{}).get('mode'):
                previous.get('input',{}).pop('foreground',None)
                if not reset and fg.get('mode')=='brightness_edges':
                    try:
                        probe = self.probe_result(owner)
                        if probe['current'] and probe['suggestion']['mode']==fg['mode']:
                            patch['input']['foreground'] = merge(probe['suggestion'],fg)
                    except DataError:
                        pass
            doc = merge(previous,patch)
            if validate_inline:
                if doc==row['document']:
                    raise DataError('INFERENCE_ADJUSTMENT_EMPTY','填写的值与当前草稿相同，没有生成新修订')
                try:
                    self.config(owner,document=doc)
                except ValidationError as error:
                    # A partial draft may still need more inputs. Invalid
                    # submitted values must not replace the previous revision.
                    errors = error.errors(include_input=False)
                    if any(item['type']!='missing' for item in errors):
                        raise
                    prior_mode = row['document'].get('input',{}).get('foreground',{}).get('mode')
                    if (fg and fg.get('mode')=='brightness_edges' and prior_mode!='brightness_edges'
                            and any('foreground' in item['loc'] for item in errors)):
                        raise DataError('INFERENCE_PROBE_REQUIRED','启用前景筛选缺少必要参数，请先点“重新探查前景”'
                                        '后再微调，或补全前景字段。') from None
            if doc != row['document'] or reset:
                with connect_database(self.database) as db:
                    db.execute('UPDATE inference_draft SET previous_document_json=document_json,document_json=?,revision=revision+1,'
                               'reviewed_revision=NULL,review_json=NULL,run_id=NULL,active=1 WHERE session_id=?',
                               (json.dumps(doc,ensure_ascii=False),owner))
                    self.base.clear_confirmation(db, owner)
                    db.execute('DELETE FROM inference_restart_request WHERE session_id=?', (owner,))
        return self.view(owner)

    def presented(self, owner, turn, *, check=None, previous_document=None):
        view = self.view(owner,structured=True,previous_document=previous_document)
        if view.get('editable') is False:
            return view
        if view['can_run']:
            try:
                config = self.config(owner)
                row = self.read(owner)
                if config.input.kind=='envi' and not row['document']['input'].get('foreground') and not self.preset(config.model_id)[0]:
                    probe = self.probe(owner)
                    view.update(can_run=False,probe=True,question=self.probe_text(probe),
                                plan=view['plan'].replace('未启用，仅按质量条件筛除。','等待用户选择前景建议。'))
                    view['presentation']['todo'] = '请选择采用前景建议、微调或关闭前景筛选。'
                    return view
                reviewed = self.service.inspect(config, check=check)
            except (DataError,OSError,ValueError,KeyError) as error:
                with connect_database(self.database) as db:
                    db.execute('UPDATE inference_draft SET reviewed_revision=NULL,review_json=NULL WHERE session_id=?',(owner,))
                    self.base.clear_confirmation(db, owner)
                view.update(can_run=False,question=self.redact(owner,error.payload.detail) if isinstance(error,DataError) else '无法按声明读取输入，请核对格式、字段和波长。')
                view['presentation']['todo'] = view['question']
                return view
            view['plan'] += f"\n已核验 {len(reviewed['files'])} 个输入文件；模型SHA-256：{reviewed['model_sha256']}。"
            excluded = reviewed['excluded_files']
            if excluded:
                view['plan'] += f'\n按范围排除 {len(excluded)} 幅。' + '\n' + '\n'.join(
                    f"• {item['file']} · {item['reason']}" for item in excluded[:12])
            with connect_database(self.database) as db:
                updated = db.execute('UPDATE inference_draft SET reviewed_revision=?,review_turn=?,review_json=? WHERE session_id=? AND revision=? AND run_id IS NULL',
                                     (view['revision'],turn,json.dumps(reviewed),owner,view['revision']))
                if updated.rowcount:
                    self.base.set_confirmation(db, owner, 'inference', view['revision'], turn)
            view['can_run'] = bool(updated.rowcount)
            view['presentation'].update(ready=view['can_run'], checked_files=len(reviewed['files']),
                                        excluded_files=len(excluded),
                                        todo='请核对方案，确认后开始推理。' if view['can_run'] else '草稿已变更，请重新审阅。')
        else:
            with connect_database(self.database) as db:
                self.base.clear_confirmation(db, owner)
        return view

    def probe(self, owner, sample=None):
        from .foreground_probe import suggest
        row = self.read(owner)
        if not row or row['run_id']:
            raise DataError('INFERENCE_PROBE_REQUIRED','请先配置本次 ENVI 推理数据与模型')
        config = self.config(owner,for_probe=True)
        if config.input.kind != 'envi':
            raise DataError('INFERENCE_PROBE_REQUIRED','前景探查只用于 ENVI 整图输入')
        metadata = self.base.service.archive.model_metadata(config.model_id)
        probe = suggest(config.input,metadata['wavelengths_nm'],sample)
        with connect_database(self.database) as db:
            db.execute('INSERT OR REPLACE INTO inference_foreground_probe VALUES (?,?,?)',
                       (owner,row['revision'],json.dumps(probe,ensure_ascii=False)))
            db.execute('UPDATE inference_draft SET reviewed_revision=NULL,review_json=NULL WHERE session_id=?',(owner,))
            self.base.clear_confirmation(db,owner)
        return probe

    def probe_result(self, owner):
        with connect_database(self.database) as db:
            record = db.execute('SELECT revision,payload FROM inference_foreground_probe WHERE session_id=?',(owner,)).fetchone()
        if not record:
            raise DataError('INFERENCE_PROBE_REQUIRED','当前会话没有前景探查记录')
        row = self.read(owner)
        return {**json.loads(record[1]), 'current':record[0] == row['revision'] and not row['run_id']}

    @staticmethod
    def probe_text(probe):
        return (f"前景探查使用 {probe['sample']} 的 {probe['rows']} 个采样行。{probe['note']}\n"
                f"建议参数 {json.dumps(probe['suggestion'],ensure_ascii=False)}。\n"
                '可回复“采用前景建议”、说明要微调的参数，或回复“关闭前景筛选”。审阅最终方案后再回复“确认推理”。')

    def apply_probe(self, owner, enabled):
        from spectrumagent.agent.tools.inference import InferenceUpdate
        row = self.read(owner)
        if not row or row['run_id'] or row['document'].get('input',{}).get('kind')!='envi':
            raise DataError('INFERENCE_PROBE_REQUIRED','请先配置待审阅的 ENVI 推理')
        if enabled:
            probe = self.probe_result(owner)
            if not probe['current']:
                raise DataError('INFERENCE_PROBE_REQUIRED','推理草稿已修改，请重新探查')
            foreground = probe['suggestion']
        else:
            foreground = {'mode':'none'}
        return self.update(owner,InferenceUpdate(expected_revision=row['revision'],
                                                 input={'kind':'envi','foreground':foreground}))

    def confirm(self, owner, content, turn, *, confirmation=None):
        with self.lock:
            row = self.read(owner)
            if (not row or row['run_id'] or not CONFIRM.fullmatch(content.strip())
                    or row['reviewed_revision']!=row['revision'] or row['review_turn']==turn or not row['review']):
                raise DataError('INFERENCE_CONFIRMATION_REQUIRED','当前没有待确认推理方案。请先展示并审阅新的推理方案。')
            target = ('inference', row['revision'], row['review_turn'])
            with connect_database(self.database) as db:
                db.execute('BEGIN IMMEDIATE')
                if self.base.confirmation(owner, db) != target or confirmation is not None and confirmation != target:
                    raise DataError('INFERENCE_CONFIRMATION_REQUIRED', '当前推理方案没有等待确认，请重新审阅。')
                self.base.clear_confirmation(db, owner, 'inference')
            config = self.config(owner)
            reviewed = json.loads(row['review'])
            from hashlib import sha256
            if reviewed.get('config_sha256') != sha256(config.model_dump_json().encode()).hexdigest():
                raise DataError('INFERENCE_SOURCE_CHANGED','推理配置或预设已变化，请重新审阅')
            result = self.service.submit(owner,config,reviewed)
            with connect_database(self.database) as db:
                db.execute('UPDATE inference_draft SET run_id=?,active=0 WHERE session_id=?',(result['inference_run_id'],owner))
                self.base.set_focus(db, owner, 'inference', result['model_id'], result['inference_run_id'])
            return result

    def cancel(self, owner):
        row = self.read(owner)
        if row and row['run_id']:
            self.service.cancel(owner,row['document']['model_id'],row['run_id'])
        with connect_database(self.database) as db:
            db.execute('UPDATE inference_draft SET active=0 WHERE session_id=?',(owner,))
            db.execute('DELETE FROM inference_restart_request WHERE session_id=?', (owner,))
            self.base.clear_confirmation(db, owner, 'inference')

    def focus_run(self, owner, model_id, run_id):
        state = self.service.status(model_id, run_id, owner=owner)
        with connect_database(self.database) as db:
            self.base.set_focus(db, owner, 'inference', model_id, run_id)
        return state
