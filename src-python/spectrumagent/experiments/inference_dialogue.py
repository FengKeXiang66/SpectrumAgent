"""Reviewed inference drafts; model parsing cannot submit numerical work."""
from copy import deepcopy
import json
from pathlib import Path
import re
from threading import RLock

import numpy as np
from pydantic import ValidationError

from backend.database import connect_database
from spectrumagent.data import DataError
from .conversation import PATHS, merge
from .inference import InferenceConfig, InferenceService

INTENT = re.compile(r'推理|预测|infer(?:ence)?', re.I)
CONFIRM = re.compile(r'(?:请)?(?:确认(?:并)?(?:执行)?推理|开始推理|确认执行)[。！!\s]*')
CANCEL = re.compile(r'(?:取消|退出|停止)(?:本次|当前)?推理[。！!\s]*')
UUID = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b')


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
                review_json TEXT, run_id TEXT)''')

    def read(self, owner):
        with connect_database(self.database) as db:
            row = db.execute('SELECT revision,document_json,sources_json,active,reviewed_revision,review_turn,review_json,run_id '
                             'FROM inference_draft WHERE session_id=?', (owner,)).fetchone()
        if not row:
            return None
        return dict(zip(('revision','document','sources','active','reviewed_revision','review_turn','review','run_id'),
                        (row[0],json.loads(row[1]),json.loads(row[2]),*row[3:])))

    def handles(self, owner, content):
        row = self.read(owner)
        semantic = PATHS.sub('输入源',content)
        if re.search(r'新建实验|训练.*测试', semantic) and PATHS.search(content) and not INTENT.search(semantic):
            with connect_database(self.database) as db:
                db.execute('UPDATE inference_draft SET active=0 WHERE session_id=?',(owner,))
            return False
        return bool(INTENT.search(semantic) or row and row['active'])

    def capture(self, owner, content):
        with connect_database(self.database) as db:
            db.execute('INSERT OR IGNORE INTO inference_draft(session_id) VALUES (?)', (owner,))
        row = self.read(owner)
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
            db.execute('UPDATE inference_draft SET sources_json=?,document_json=?,revision=?,active=1 WHERE session_id=?',
                       (json.dumps(row['sources'],ensure_ascii=False),json.dumps(row['document'],ensure_ascii=False),row['revision'],owner))
        return self.redact(owner, content)

    def redact(self, owner, text):
        for ref, path in sorted((self.read(owner) or {}).get('sources',{}).items(),key=lambda p:-len(p[1])):
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

    def config(self, owner):
        row = self.read(owner)
        doc = provided(deepcopy(row['document']))
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
            elif spec.get('kind') == 'envi' and train['kind']=='roi_images':
                for key in ('wavelength_unit','mapping_window_nm','nearest_tolerance_nm','quality'):
                    if key=='quality':
                        spec[key]=merge(train[key],spec.get(key,{}))
                    else:
                        spec.setdefault(key,train[key])
        return InferenceConfig.model_validate(doc)

    def view(self, owner):
        row = self.read(owner)
        if not row:
            return {'revision':0,'can_run':False,'plan':'尚未创建推理方案','question':'请提供归档模型与推理数据文件或目录。'}
        config, question = None, ''
        try:
            config = self.config(owner)
        except ValidationError as error:
            fields = [' → '.join(map(str,e['loc'])) for e in error.errors(include_input=False)]
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
            plan='\n'.join(lines)
            plan += '\n复用训练时已拟合预处理：'+json.dumps(model['preprocessing'],ensure_ascii=False)
            plan += '\n只执行推理，不重新训练。无真值标签，不输出准确率；PLS响应不是概率。'
            if config.input.kind=='envi':
                plan += '\n整图推理无训练ROI材质隔离，邻域可能跨材质边界；只输出已知类别，未实现背景或未知类拒识。'
            question = '请核对模型、数据与方案；单独回复“确认推理”后执行。'
        if row['run_id']:
            question = '本方案已经提交，可查看推理任务；更换数据请明确新建推理，不重复提交。'
        summary={'revision':row['revision'],'can_run':config is not None and not row['run_id'],
                 'plan':plan,'question':question,'run_id':row['run_id']}
        if row['document'].get('model_id'):
            try:
                metadata=self.base.service.archive.model_metadata(row['document']['model_id'])
                summary.update(model_id=metadata['model_id'],model_neighborhood=metadata['neighborhood'],
                               model_evaluation_unit=metadata['evaluation_unit'])
            except (DataError,OSError,ValueError,KeyError):
                pass
        return summary

    def update(self, owner, args):
        with self.lock:
            row = self.read(owner)
            if not row or args.expected_revision != row['revision']:
                raise DataError('INFERENCE_DRAFT_CONFLICT','推理草稿已更新，请读取最新修订')
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
            doc = merge(previous,patch)
            if doc != row['document'] or reset:
                with connect_database(self.database) as db:
                    db.execute('UPDATE inference_draft SET document_json=?,revision=revision+1,reviewed_revision=NULL,review_json=NULL,run_id=NULL,active=1 WHERE session_id=?',
                               (json.dumps(doc,ensure_ascii=False),owner))
        return self.view(owner)

    def presented(self, owner, turn):
        view = self.view(owner)
        if view['can_run']:
            try:
                reviewed = self.service.inspect(self.config(owner))
            except (DataError,OSError,ValueError,KeyError) as error:
                with connect_database(self.database) as db:
                    db.execute('UPDATE inference_draft SET reviewed_revision=NULL,review_json=NULL WHERE session_id=?',(owner,))
                view.update(can_run=False,question=self.redact(owner,error.payload.detail) if isinstance(error,DataError) else '无法按声明读取输入，请核对格式、字段和波长。')
                return view
            view['plan'] += f"\n已核验 {len(reviewed['files'])} 个输入文件；模型SHA-256：{reviewed['model_sha256']}。"
            with connect_database(self.database) as db:
                db.execute('UPDATE inference_draft SET reviewed_revision=?,review_turn=?,review_json=? WHERE session_id=? AND revision=?',
                           (view['revision'],turn,json.dumps(reviewed),owner,view['revision']))
        return view

    def confirm(self, owner, content, turn):
        with self.lock:
            row = self.read(owner)
            if not row or not CONFIRM.fullmatch(content.strip()) or row['reviewed_revision']!=row['revision'] or row['review_turn']==turn or not row['review']:
                raise DataError('INFERENCE_CONFIRMATION_REQUIRED','请先核对完整推理方案，再单独回复“确认推理”')
            if row['run_id']:
                return {'inference_run_id':row['run_id'],'model_id':row['document']['model_id'],'status':self.service.status(row['document']['model_id'],row['run_id'])['status']}
            result = self.service.submit(owner,self.config(owner),json.loads(row['review']))
            with connect_database(self.database) as db:
                db.execute('UPDATE inference_draft SET run_id=? WHERE session_id=?',(result['inference_run_id'],owner))
            return result

    def cancel(self, owner):
        row = self.read(owner)
        if row and row['run_id']:
            self.service.cancel(owner,row['document']['model_id'],row['run_id'])
        with connect_database(self.database) as db:
            db.execute('UPDATE inference_draft SET active=0 WHERE session_id=?',(owner,))
