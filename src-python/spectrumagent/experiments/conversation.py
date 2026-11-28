"""Session-owned drafts and reviewed execution, independent of model prose."""
from copy import deepcopy
from difflib import SequenceMatcher
import json
from pathlib import Path
import re

import numpy as np
from pydantic import ValidationError

from backend.database import connect_database
from spectrumagent.data import DataError
from .schema import grid_hint, ExperimentConfig
from .inputs import archive_files, enforce_split, sha256, split_check_text, split_preflight


# Quote paths containing spaces. Bare paths terminate at Chinese punctuation.
PATHS = re.compile(r'''["“‘'](?P<quoted>(?:[A-Za-z]:[\\/]|/)[^"”’'\r\n]+)["”’']|(?P<bare>[A-Za-z]:[\\/][^\s,，。；;、"“”‘’'<>]+|(?<![\w:/])/(?:[^\s,，。；;、"“”‘’'<>]+))''')
CONFIRM = re.compile(r'(?:请)?(?:确认(?:方案)?(?:并)?(?:开始)?(?:执行|训练|运行)|按(?:此|这个|上述)方案(?:执行|训练)|开始训练)[。！!\s]*')
START = re.compile(r'PLS[-_ ]?DA|训练.*测试|train.*test|训练(?:数据|集)|测试(?:数据|集)|独立测试|数值实验', re.I)
CANCEL = re.compile(r'(?:取消|退出|停止)(?:本次|当前)?(?:数值)?实验[。！!\s]*')
HISTORY = re.compile(r'(?:历史|上次|最近|归档).{0,8}实验|(?:实验|训练测试)(?:结果|报告)|(?:比较|对比).{0,20}实验|实验.{0,8}(?:历史|归档)')
RETRAIN = re.compile(r'重训|重新训练|再训|调整.{0,20}(?:训练|实验)方案')
PARAMETER_EDIT = re.compile(r'(?:把|将|修改|调整|更改|改|换|增加|添加|删除).{0,32}(?:预处理|S\s*G|窗口|潜变量|第\s*\d+\s*步)|(?:预处理|S\s*G|窗口|潜变量).{0,20}(?:改成|设为|改为|调整)', re.I)
EXPLAIN_RESULT = re.compile(r'(?:为什么|为何|解释|分析|怎么会|如何理解|哪些).{0,70}(?:预测|误判|错分|混淆|准确率|召回率|分类结果)|(?:预测|分类|推理|测试)结果.{0,30}(?:原因|解释|怎么看)')


class DraftIssue(ValueError):
    """Controlled explanations, unlike exceptions from local file readers."""


def merge(old, patch):
    result = deepcopy(old)
    for key, value in patch.items():
        if value is None and key == 'saturation':
            result[key] = None
        elif value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict) and value.get('kind') in (None, result[key].get('kind')):
            result[key] = merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def edit_preprocessing(document, edit):
    steps = deepcopy(document.get('preprocessing', []))
    index = edit['index'] - 1
    action = edit['action']
    if index > len(steps) or action != 'insert' and index == len(steps):
        raise DataError('EXPERIMENT_STEP_NOT_FOUND', '预处理步骤序号超出当前清单，请先核对草稿。')
    if action == 'remove':
        steps.pop(index)
    elif action == 'insert':
        steps.insert(index, edit['step'])
    else:
        step = edit['step']
        previous = steps[index] if step['op'] == steps[index]['op'] else {}
        steps[index] = merge(previous, {key:value for key,value in step.items() if value is not None})
    return steps


def draft_changes(previous, current):
    if previous is None:
        return []
    before, after = previous.get('preprocessing', []), current.get('preprocessing', [])
    key = lambda step: json.dumps(step, sort_keys=True, ensure_ascii=False)
    changes = []
    for kind,a,b,c,d in SequenceMatcher(a=list(map(key,before)), b=list(map(key,after)), autojunk=False).get_opcodes():
        if kind == 'equal':
            continue
        if kind == 'replace' and b-a == d-c == 1 and before[a]['op'] == after[c]['op']:
            old, new = before[a], after[c]
            changes.extend(f'预处理第 {c+1} 步 {new["op"]} 的 {field} 从 {old.get(field, "未指定")} 改为 {new.get(field, "未指定")}'
                           for field in sorted(old.keys() | new.keys()) if old.get(field) != new.get(field))
            continue
        changes.extend(f'移除原第 {i+1} 步 {before[i]["op"]}' for i in range(a,b))
        changes.extend(f'加入第 {i+1} 步 {after[i]["op"]}' for i in range(c,d))
    def display(value):
        if value is None:
            return '未设置'
        if isinstance(value,bool):
            return '开启' if value else '关闭'
        return f'{value:g}' if isinstance(value,float) else str(value)

    def fields_changed(old, new, fields, defaults):
        for key,title in fields.items():
            default, missing = defaults.get(key,(None,'未设置'))
            before,after = old.get(key,default),new.get(key,default)
            if before!=after:
                left = missing if before is None else display(before)
                right = missing if after is None else display(after)
                changes.append(f'{title} · {left} → {right}')
        return ({key:value for key,value in old.items() if key not in fields}
                != {key:value for key,value in new.items() if key not in fields})

    for role,title in (('train','训练'),('test','测试')):
        old,new = previous.get(role) or {},current.get(role) or {}
        if old.get('kind')==new.get('kind')=='roi_images':
            fields = {'sampling_stride':f'{title}采样步长','neighborhood':f'{title}空间邻域',
                      'wavelength_unit':f'{title}原图波长单位','mapping_window_nm':f'{title}映射窗口（nm）',
                      'nearest_tolerance_nm':f'{title}最近通道容差（nm）'}
            if role=='train':
                fields.update(max_per_class='每类上限',sampling_seed='抽样种子')
            defaults = {'sampling_stride':(1,'未设置'),'max_per_class':(None,'不限'),'sampling_seed':(42,'未设置')}
            fields_changed(old.get('quality') or {},new.get('quality') or {},
                           {key:title+label for key,label in {'min_mean':'最低均值','min_std':'最低标准差',
                              'max_zero_fraction':'零值比例上限','saturation':'饱和上限'}.items()},
                           {'saturation':(None,'关闭')})
            old = {key:value for key,value in old.items() if key!='quality'}
            new = {key:value for key,value in new.items() if key!='quality'}
            if fields_changed(old,new,fields,defaults):
                changes.append(title+'输入已更新')
        elif old!=new:
            changes.append(title+'输入已更新')

    labels = {'name':'实验名称', 'axis':'波长轴', 'classes':'类别映射', 'model':'模型参数',
              'test_usage':'测试用途', 'additional_metrics':'附加指标'}
    for field, title in labels.items():
        if previous.get(field) != current.get(field):
            changes.append(title + '已更新')
    return changes


def describe(document):
    """Human-readable plan; references replace local file locations."""
    lines = ['实验名称：' + document.get('name', '待补充')]
    if document.get('split_id'):
        lines.append('已保存划分：' + document['split_id'] + '，沿用原来的逐图用途与分组。')
        lines.append('ROI 取谱：只在标注区域内选中心，整个邻域须位于同一 ROI 且通过质量筛选。')
        uncovered = document.get('split_test_uncovered', [])
        if uncovered:
            lines.append('划分清单的测试侧未覆盖：' + '、'.join(uncovered) + '。')
    unit_names = {'spectrum': '光谱样本', 'center_pixel': '中心像元'}
    for role, title in (('train', '训练数据'), ('test', '测试数据')):
        spec = document.get(role)
        if not spec:
            lines.append(title + '：待补充')
            continue
        if spec.get('kind') == 'npz':
            lines.append(title + '：NPZ输入源 ' + '、'.join(spec.get('source_refs', [])))
            lines.append('  光谱字段 ' + spec.get('spectra_key', '待补充') + '，标签字段 ' + spec.get('labels_key', '待补充')
                         + '，波长字段 ' + spec.get('wavelengths_key', '待补充'))
            if spec.get('groups_key'):
                lines.append('  分组字段 ' + spec['groups_key'])
            stages = {'spectra': '未做空间平均的光谱矩阵', 'neighborhood_mean': '已完成邻域均值的光谱矩阵'}
            lines.append('  输入阶段：' + stages.get(spec.get('input_stage'), '待补充'))
        else:
            members = spec.get('members', [])
            count = document.get('split_counts', {}).get('训练' if role == 'train' else '测试', len(members))
            lines.append(title + '：原图与ROI，共 ' + str(count) + ' 个显式配对')
            for member in members:
                lines.append('  ' + member['sample_id'] + '：HDR ' + member['header_ref'] + '，ROI ' + member['roi_ref']
                             + ('，数据 ' + member['data_ref'] if member.get('data_ref') else '')
                             + ('，中心列表 ' + member['centers_ref'] if member.get('centers_ref') else ''))
            lines.append('  波长单位 ' + spec.get('wavelength_unit', '待补充') + '；映射窗口 ' + str(spec.get('mapping_window_nm', '待补充'))
                         + ' nm；最近通道容差 ' + str(spec.get('nearest_tolerance_nm', '待补充')) + ' nm')
            quality = spec.get('quality', {})
            lines.append('  质量筛选：' + '，'.join(key + '=' + str(value) for key, value in quality.items()))
            if not any(member.get('centers_ref') for member in members):
                lines.append(f"  采样步长：{spec.get('sampling_stride', 1)} 像元，行列从图像左上角起按等间距取候选中心")
            if spec.get('max_per_class') is not None:
                lines.append(f"  每类最多抽样 {spec['max_per_class']} 个合格中心，种子 {spec.get('sampling_seed',42)}。实际数量取谱后统计。")
        lines.append('  空间邻域：' + str(spec.get('neighborhood', '待补充')) + '；评价单位：'
                     + unit_names.get(spec.get('evaluation_unit'), '待补充'))
    classes = document.get('classes', [])
    lines.append('类别编号与名称：' + ('、'.join(str(item['label']) + '=' + item['name'] for item in classes) or '待补充'))
    operations = {'savgol': 'SG', 'l2': 'L2归一化', 'center': '训练集均值中心化', 'standard_scale': '训练集标准化', 'snv': 'SNV', 'pca': 'PCA'}
    if 'preprocessing' not in document:
        lines.append('预处理：待补充（可明确选择不加步骤）')
    elif not document['preprocessing']:
        lines.append('预处理：不附加步骤')
    for index, step in enumerate(document.get('preprocessing', []), 1):
        parameters = '，'.join(key + '=' + str(value) for key, value in step.items() if key != 'op')
        lines.append(f"预处理第{index}步：" + operations[step['op']] + ('，' + parameters if parameters else ''))
    model = document.get('model', {})
    lines.append('PLS-DA：潜变量 ' + str(model.get('n_components', '待补充')) + '，内部缩放 ' + str(model.get('scale', '待补充'))
                 + '，最大迭代 ' + str(model.get('max_iter', '待补充')) + '，收敛容差 ' + str(model.get('tol', 1e-6)))
    axis = document.get('axis', {})
    if axis.get('kind') == 'grid':
        lines.append(f"目标波长：{axis['start_nm']:g}至{axis['stop_nm']:g} nm，间隔{axis['step_nm']:g} nm")
    elif axis.get('kind') == 'saved_native':
        scope = '训练原图' if axis.get('train_only') else '原图'
        lines.append(f"目标波长：沿用{scope}共享的 {len(axis['wavelengths'])} 个波段")
        hint = grid_hint(np.asarray(axis['wavelengths']) * (1000 if axis.get('declared_unit')=='um' else 1))
        if hint:
            lines.append(hint)
        if axis.get('train_only'):
            lines.append('训练与测试 HDR 波长轴不同。训练侧原生通道可用于探索，正式评价前须指定共同目标网格及映射窗口／容差。')
    elif axis.get('kind') == 'archived_axis':
        lines.append(f"目标波长：沿用归档中的 {len(axis['wavelengths_nm'])} 个波段")
    else:
        lines.append('目标波长：' + ('读取' + ('训练' if axis['role'] == 'train' else '测试') + 'NPZ波长字段（单位nm）' if axis else '待补充'))
    lines.append('额外指标：' + '、'.join(document.get('additional_metrics', [])))
    lines.append('测试用途：' + {'independent_test': '新的独立测试', 'development_regression': '既有数据开发复现核验'}.get(document.get('test_usage'), '待补充'))
    return '\n'.join(lines)


def field_name(location):
    names = {'name': '实验名称', 'train': '训练数据', 'test': '测试数据', 'paths': '输入源',
             'preprocessing': '预处理步骤', 'model': 'PLS-DA参数', 'classes': '类别编号与名称',
             'wavelengths_nm': '目标波长（nm）', 'test_usage': '测试用途', 'spectra_key': '光谱字段',
             'labels_key': '标签字段', 'wavelengths_key': '波长字段', 'input_stage': '输入已完成的处理阶段',
             'neighborhood': '空间邻域大小', 'evaluation_unit': '评价单位', 'n_components': '潜变量或PCA分量数',
             'scale': '模型内部缩放', 'max_iter': '最大迭代次数', 'window': '窗口长度',
             'polyorder': '多项式阶数', 'derivative': '导数阶数', 'delta_nm': '波长步长（nm）',
             'quality': '质量筛选', 'min_mean': '最小均值', 'min_std': '最小标准差',
             'max_zero_fraction': '最大零值比例', 'saturation': '饱和值或明确不筛选',
             'members': '原图与ROI配对', 'mapping_window_nm': '波长映射窗口（nm）',
             'nearest_tolerance_nm': '最近波长通道容差（nm）', 'wavelength_unit': '原始波长单位'}
    return ' → '.join('第' + str(part + 1) + '项' if isinstance(part, int) else names.get(part, str(part))
                      for part in location if part not in {'npz', 'roi_images', 'savgol'}) or '配置'


class ExperimentDialogue:
    def __init__(self, service):
        self.service, self.database = service, service.paths.database
        with connect_database(self.database) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS experiment_group_split (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id), document TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS experiment_pairing_intake (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id), document TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS experiment_pairing (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id), report_json TEXT NOT NULL)''')
            if 'replay_id' not in {r[1] for r in db.execute('PRAGMA table_info(experiment_pairing)')}:
                db.execute('ALTER TABLE experiment_pairing ADD COLUMN replay_id TEXT')
            db.execute('''CREATE TABLE IF NOT EXISTS experiment_selection (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id), experiment_id TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS experiment_confirmation (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id),
                flow TEXT NOT NULL, revision INTEGER NOT NULL, plan_id TEXT NOT NULL)''')
            db.execute("""CREATE TABLE IF NOT EXISTS experiment_wavelength_proposal (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id), revision INTEGER NOT NULL,
                document TEXT NOT NULL)""")
            db.execute('''CREATE TABLE IF NOT EXISTS experiment_result_focus (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id),
                flow TEXT NOT NULL, model_id TEXT NOT NULL, run_id TEXT)''')
            db.execute('''CREATE TABLE IF NOT EXISTS experiment_dialogue (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id),
                revision INTEGER NOT NULL DEFAULT 0,
                document_json TEXT NOT NULL DEFAULT '{}',
                sources_json TEXT NOT NULL DEFAULT '{}',
                active INTEGER NOT NULL DEFAULT 1,
                reviewed_revision INTEGER,
                review_turn TEXT,
                review_sources_json TEXT,
                run_status TEXT NOT NULL DEFAULT 'idle',
                experiment_id TEXT)''')
            if 'review_sources_json' not in {row[1] for row in db.execute('PRAGMA table_info(experiment_dialogue)')}:
                db.execute('ALTER TABLE experiment_dialogue ADD COLUMN review_sources_json TEXT')
            columns = {row[1] for row in db.execute('PRAGMA table_info(experiment_dialogue)')}
            for column in ('previous_document_json', 'base_experiment_id'):
                if column not in columns:
                    db.execute(f'ALTER TABLE experiment_dialogue ADD COLUMN {column} TEXT')
        from .tasks import ExperimentTasks
        self.tasks = ExperimentTasks(self)
        from .inference_dialogue import InferenceDialogue
        self.inference = InferenceDialogue(self)
        from .study import StudyService
        self.study = StudyService(self)

    @staticmethod
    def set_confirmation(db, session_id, flow, revision, plan_id):
        db.execute('INSERT OR REPLACE INTO experiment_confirmation VALUES (?,?,?,?)',
                   (session_id, flow, revision, plan_id))

    @staticmethod
    def clear_confirmation(db, session_id, flow=None):
        if flow is None:
            db.execute('DELETE FROM experiment_confirmation WHERE session_id=?', (session_id,))
        else:
            db.execute('DELETE FROM experiment_confirmation WHERE session_id=? AND flow=?', (session_id, flow))

    def confirmation(self, session_id, db=None):
        if db is None:
            with connect_database(self.database) as connection:
                return self.confirmation(session_id, connection)
        row = db.execute('SELECT flow, revision, plan_id FROM experiment_confirmation WHERE session_id=?',
                         (session_id,)).fetchone()
        return tuple(row) if row else None

    @staticmethod
    def set_focus(db, session_id, flow, model_id, run_id=None):
        db.execute('INSERT OR REPLACE INTO experiment_result_focus VALUES (?,?,?,?)',
                   (session_id, flow, model_id, run_id))

    def focus(self, session_id):
        with connect_database(self.database) as db:
            row = db.execute('SELECT flow,model_id,run_id FROM experiment_result_focus WHERE session_id=?',
                             (session_id,)).fetchone()
        return tuple(row) if row else None

    def _read(self, session_id, db=None):
        if db is None:
            with connect_database(self.database) as connection:
                return self._read(session_id, connection)
        row = db.execute('SELECT revision,document_json,sources_json,active,reviewed_revision,review_turn,run_status,experiment_id,review_sources_json,previous_document_json,base_experiment_id '
                         'FROM experiment_dialogue WHERE session_id=?', (session_id,)).fetchone()
        if row is None:
            return None
        return dict(zip(('revision', 'document', 'sources', 'active', 'reviewed_revision', 'review_turn', 'run_status', 'experiment_id', 'review_sources_json',
                         'previous_document_json', 'base_experiment_id'),
                        (row[0], json.loads(row[1]), json.loads(row[2]), *row[3:])))

    def pairing_answer(self, session_id, content, check=lambda: None, *, fields=None):
        from .pairing import PAGE, PREPARE_REPLAY, REPLAY, details, directories, inventory, overview
        page = PAGE.fullmatch(content.strip())
        if page or REPLAY.match(content):
            with connect_database(self.database) as db:
                row = db.execute('SELECT report_json FROM experiment_pairing WHERE session_id=?', (session_id,)).fetchone()
            if row is None:
                return '当前会话还没有配对预览。'
            report = json.loads(row[0])
            if page:
                return details(report, page[1], int(page[2] or 1))
            from .center_replay import replay
            tail = content[REPLAY.match(content).end():].strip(' ，,：:；;。！!\n\t')
            location = PATHS.fullmatch(tail)
            if tail and not location:
                return '请发送“核验中心取谱”，或在其后加一个用双引号括起的发布目录。'
            if not location and not report.get('manifest_path'):
                return '请在“核验中心取谱”后提供发布目录，或附来源清单重新进行配对预览。'
            release = Path(location['quoted'] or location['bare']) if location else Path(report['manifest_path']).parent
            if not self.service.lock.acquire(blocking=False):
                return '已有数值任务运行，请在结束后再核验中心取谱。'
            try:
                with connect_database(self.database) as db:
                    db.execute('UPDATE experiment_pairing SET replay_id=NULL WHERE session_id=?', (session_id,))
                run,stats = replay(report,release,self.service.paths.exports/'center-replays',check)
                with connect_database(self.database) as db:
                    changed = db.execute('UPDATE experiment_pairing SET replay_id=? WHERE session_id=? AND report_json=?',
                                         (run.name, session_id, row[0])).rowcount
                return ('中心取谱核验通过。\n' + '\n'.join(
                    f"{role}：{s['images']} 幅，{s['exact']}/{s['centers']} 条 X3 逐值一致，标签、波长轴一致。"
                    for role,s in stats.items()) + f'\n新光谱与核验记录：{run}\n' +
                    (f'如需按归档参数拟合，可发送“{PREPARE_REPLAY}”，审阅后确认执行。' if changed else '会话配对清单已更新。'))
            except (OSError, KeyError, ValueError, DataError) as error:
                detail = error.payload.detail if isinstance(error, DataError) else str(error)
                return '中心取谱核验未完成：' + detail
            finally:
                self.service.lock.release()
        try:
            from .pairing import validate_directories
            report = inventory(validate_directories(fields) if fields is not None else directories(content, PATHS))
        except (OSError, ValueError) as error:
            return '未生成新的配对预览。' + str(error)
        from uuid import uuid4
        report['preview_id'] = str(uuid4())
        with connect_database(self.database) as db:
            db.execute('INSERT INTO experiment_pairing(session_id,report_json) VALUES (?,?) ON CONFLICT(session_id) DO UPDATE '
                       'SET report_json=excluded.report_json,replay_id=NULL', (session_id, json.dumps(report, ensure_ascii=False)))
        return overview(report)

    def pairing_report(self, session_id):
        from uuid import NAMESPACE_OID, uuid5
        with connect_database(self.database) as db:
            saved = db.execute('SELECT report_json FROM experiment_pairing WHERE session_id=?',
                               (session_id,)).fetchone()
        if not saved:
            return None
        report = json.loads(saved[0])
        if 'preview_id' not in report:
            snapshot = {key:report[key] for key in ('roots','pairs','issues','unused')}
            report['preview_id'] = str(uuid5(NAMESPACE_OID, json.dumps(snapshot,sort_keys=True)))
        return report

    def pairing_preview_id(self, session_id):
        report = self.pairing_report(session_id)
        return report['preview_id'] if report else None

    def prepare_replay(self, session_id):
        from .center_replay import CLASSES
        from spectrumagent.agent.tools.experiments import DraftUpdate
        with connect_database(self.database) as db:
            row = db.execute('SELECT replay_id FROM experiment_pairing WHERE session_id=?',(session_id,)).fetchone()
        if not row or not row[0]:
            raise DataError('CENTER_REPLAY_REQUIRED','请先在本会话完成中心取谱核验')
        run = self.service.paths.exports/'center-replays'/row[0]
        summary = json.loads((run/'核验.json').read_text('utf-8'))
        specs = {}
        for role,title,filename in [('train','训练','训练光谱.npz'),('test','测试','测试V2光谱.npz')]:
            path = run/filename
            if sha256(path) != summary['splits'][title]['output_sha256']:
                raise DataError('CENTER_REPLAY_CHANGED','重新生成的光谱文件发生变化，请重新核验')
            self.capture(session_id, f'"{path}"')
            record = self._read(session_id)
            reference = next(ref for ref,value in record['sources'].items() if value == str(path))
            specs[role] = dict(kind='npz',source_refs=[reference],spectra_key='X3',labels_key='y',
                               wavelengths_key='wavelengths_nm',input_stage='neighborhood_mean',
                               neighborhood=3,evaluation_unit='center_pixel')
        self.update(session_id,DraftUpdate(expected_revision=record['revision'],reset=True,
            name='五分类中心取谱复现 '+run.name[:8], **specs, axis=dict(kind='archive',role='train'),
            classes=[dict(label=k,name=v) for k,v in CLASSES.items()], test_usage='development_regression',
            preprocessing=[dict(op='savgol',window=15,polyorder=2,derivative=2,delta_nm=5.,mode='interp'),
                           dict(op='l2'),dict(op='center')],model=dict(n_components=12,scale=False,max_iter=1000),
            additional_metrics=['kappa']))
        # A separate confirmation now belongs to the new training draft.
        with connect_database(self.database) as db:
            db.execute('UPDATE inference_draft SET active=0 WHERE session_id=?', (session_id,))
            self.clear_confirmation(db, session_id)

    def handles(self, session_id, content):
        if HISTORY.search(content):
            return True
        record = self._read(session_id)
        if record and record['run_status'] == 'succeeded' and CONFIRM.fullmatch(content.strip()):
            return True
        if record and (CANCEL.fullmatch(content.strip()) or re.search(r'继续(?:数值)?实验|(?:实验|训练测试)(?:结果|报告)', content)):
            return True
        if record and record['active']:
            # The existing annotation and application-management routes keep working.
            return not re.search(r'标注|超像素|分割|删除数据|查看数据列表|模型设置', content)
        return bool(START.search(content) and (PATHS.search(content) or '数值实验' in content))

    def capture(self, session_id, content, *, pairing=False):
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO experiment_dialogue(session_id,active) VALUES (?,?)', (session_id,int(not pairing)))
            record = self._read(session_id, db)
            for match in PATHS.finditer(content):
                value = match['quoted'] or match['bare']
                if value not in record['sources'].values():
                    record['sources']['S' + str(len(record['sources']) + 1)] = value
            active = record['active'] or not pairing and bool(START.search(content) or re.search(r'继续(?:数值)?实验', content))
            db.execute('UPDATE experiment_dialogue SET sources_json=?,active=? WHERE session_id=?',
                       (json.dumps(record['sources'], ensure_ascii=False), int(active), session_id))
        return self.redact(session_id, content)

    def redact(self, session_id, content):
        record = self._read(session_id)
        for reference, value in sorted((record or {}).get('sources', {}).items(), key=lambda pair: -len(pair[1])):
            content = content.replace(json.dumps(value, ensure_ascii=False)[1:-1], reference).replace(value, reference)
        return PATHS.sub('本地输入源', content)

    def _source(self, record, reference):
        value = record['sources'].get(reference)
        if not value:
            raise DraftIssue('输入源引用不存在，请重新提供或明确选择数据')
        path = Path(value).expanduser()
        if not path.is_absolute() or not path.exists():
            raise DraftIssue('输入源不可读，请核对本机文件或目录')
        return path.resolve()

    @staticmethod
    def _archives(path):
        files = archive_files(path)
        if not files or any(p.suffix.lower() != '.npz' for p in files):
            raise ValueError('需要NPZ文件或包含NPZ文件的目录；原图请显式配对HDR与ROI')
        return files

    def inspect(self, session_id, source_ref):
        record = self._read(session_id)
        try:
            path = self._source(record, source_ref)
            result = {'source_ref': source_ref, 'available': True, 'kind': 'directory' if path.is_dir() else path.suffix.lower().lstrip('.')}
            if path.is_dir() or path.suffix.lower() == '.npz':
                files = self._archives(path)
                result.update(file_count=len(files), inspected_files=min(3, len(files)), truncated=len(files) > 3)
                for index, file in enumerate(files[:3], 1):
                    with np.load(file, allow_pickle=False) as archive:
                        result[f'file_{index}_keys'] = self.redact(session_id, '、'.join(archive.files))
                        for number, key in enumerate(archive.files[:12], 1):
                            array = archive[key]
                            prefix = f'file_{index}_field_{number}'
                            result[prefix + '_name'] = self.redact(session_id, key)
                            result[prefix + '_shape'] = ' × '.join(map(str, array.shape))
                            result[prefix + '_dtype'] = str(array.dtype)
            return result
        except (ValueError, OSError, KeyError, TypeError):
            return {'source_ref': source_ref, 'available': False, 'detail': '输入不可读或不是受支持的NPZ；请核对文件、目录及输入类型'}

    def source_summary(self, session_id):
        record = self._read(session_id)
        result = {}
        for ref in record['sources']:
            # Capture itself does not read matrices or recursively scan directories.
            try:
                path = self._source(record, ref)
                result[ref] = '目录' if path.is_dir() else path.suffix.lower().lstrip('.')
            except ValueError:
                result[ref] = '不可读'
        return result

    def _config(self, record, *, training_only=False, train_manifest_rows=None, normalize_evaluation=True):
        from spectrumagent import projects
        with connect_database(self.database) as db:
            projects.check_document(db, record.get('document') or {})
        document = deepcopy(record['document'])
        selection = document.pop('workspace_selection', None)
        roles = ('train',) if training_only else ('train', 'test')
        if selection:
            used = {member['roi_ref'] for role in roles for member in document.get(role, {}).get('members', [])}
            for item in selection:
                if item['roi_ref'] in used and sha256(self._source(record, item['roi_ref'])) != item['roi_sha256']:
                    raise DraftIssue('已保存的训练区域副本发生变化，请从当前标注重新建立方案。')
        axis = document.pop('axis', None)
        if training_only:
            document.pop('test', None)
            document.update(name=document.get('name') or '训练集寻优', preprocessing=[],
                            model=dict(n_components=1, scale=False, max_iter=1000, **{
                                key:value for key,value in (document.get('model') or {}).items()
                                if key not in {'n_components','scale','max_iter'}}),
                            test_usage='development_regression')
            document['model'].update({key:value for key,value in (record['document'].get('model') or {}).items()
                                      if key in {'scale','max_iter'} and value is not None})
            if axis and axis.get('role') == 'test':
                raise DraftIssue('寻优波长轴须来自训练输入或显式网格')
        split_id = document.pop('split_id', None)
        if split_id:
            from .group_split import load_saved_plan, manifest_path
            path = manifest_path(self.service.paths.exports, split_id)
            digest = document.pop('split_sha256')
            document.pop('split_counts')
            document.pop('split_test_uncovered')
            metadata = {}
            try:
                sides = load_saved_plan(path, digest, verify_test=not training_only, metadata=metadata)
            except (OSError, KeyError, TypeError):
                raise DraftIssue('已保存划分或其输入无法读取，请重新检查划分清单') from None
            except ValueError as error:
                raise DraftIssue(str(error)) from None
            if train_manifest_rows is not None:
                train_manifest_rows.extend(sides['训练'])
            expected_labels = {label for rows in sides.values() for row in rows for label in row['labels']}
            if {item['name'] for item in document.get('classes', [])} != expected_labels:
                raise DraftIssue('类别名称须与已保存划分的标注一致')
            document['split_manifest'] = dict(split_id=split_id, sha256=digest, **metadata)
            for role, title in (('train', '训练'), ('test', '测试')):
                if role not in roles:
                    continue
                document[role]['members'] = [
                    dict(header_path=row['hdr'], roi_path=row['annotation'], data_path=row['img'],
                         sample_id=row['sample_id'] or row['hdr'], batch=row['batch']) for row in sides[title]]
        for role in roles:
            spec = document.get(role)
            if not isinstance(spec, dict):
                continue
            if spec.get('kind') == 'npz':
                refs = spec.pop('source_refs', [])
                spec['paths'] = [str(self._source(record, ref)) for ref in refs]
            elif spec.get('kind') == 'roi_images':
                for member in spec.get('members', []):
                    if selection:
                        member['sample_id'] = str(self._source(record, member['header_ref']))
                    for key in ('header', 'roi', 'data', 'centers'):
                        ref = member.pop(key + '_ref', None)
                        if ref is not None:
                            member[key + '_path'] = str(self._source(record, ref))
        if training_only and document.get('train'):
            train = document['train']
            if train.get('kind') == 'npz':
                declared = [Path(value) for value in train.get('paths',[])]
                sources = [file.resolve() for value in declared for file in archive_files(value)]
                train['paths'] = [str(file) for file in sources]
            else:
                declared = []
                sources = [Path(member['header_path']) for member in train.get('members',[]) if member.get('header_path')]
            if any(part.casefold()=='7t' for path in sources+declared for part in path.parts):
                raise DraftIssue('训练寻优不能使用 7t 推理目录')
            test = record['document'].get('test') or {}
            if split_id:
                test_paths = [Path(row['hdr']) for row in sides['测试']]
            else:
                refs = (test.get('source_refs',[]) if test.get('kind')=='npz' else
                        [member.get('header_ref') for member in test.get('members',[])])
                test_paths = [Path(record['sources'][ref]) for ref in refs if ref in record['sources']]
            if any(path.is_relative_to(other) or other.is_relative_to(path)
                   for path in declared+sources for other in test_paths):
                raise DraftIssue('训练来源与已声明留出集路径交叉，无法在训练集内独立寻优')
        if 'classes' in document:
            entries = document['classes']
            if len({item['label'] for item in entries}) != len(entries):
                raise DraftIssue('类别编号重复')
            document['classes'] = {item['label']: item['name'] for item in entries}
        if axis and axis['kind'] == 'grid':
            intervals = (axis['stop_nm'] - axis['start_nm']) / axis['step_nm']
            if not 1 <= intervals <= 9999 or not np.isclose(intervals, round(intervals), rtol=0, atol=1e-8):
                raise DraftIssue('波长网格须递增、端点对齐，且为2至10000个波段')
            document['wavelengths_nm'] = (axis['start_nm'] + np.arange(round(intervals) + 1) * axis['step_nm']).tolist()
        elif axis and axis['kind'] == 'saved_native':
            if axis.get('train_only') and not training_only:
                raise DraftIssue('训练与测试原图波长轴不同，请设置共同目标波长网格、映射窗口和最近波长容差。')
            unit = document['train'].get('wavelength_unit')
            if unit:
                if axis['declared_unit'] and unit != axis['declared_unit']:
                    raise DraftIssue('原图波长单位与 HDR 声明冲突')
                waves = np.asarray(axis['wavelengths']) * (1000 if unit == 'um' else 1)
                document['wavelengths_nm'] = waves.tolist()
                for role in ('train', 'test'):
                    if role not in roles:
                        continue
                    document[role].setdefault('mapping_window_nm', float(np.diff(waves).min()))
                    document[role].setdefault('nearest_tolerance_nm', 0.)
            else:
                raise DraftIssue('部分 HDR 缺少波长单位，请确认原图波长使用 nm 还是 μm')
        elif axis and axis['kind'] == 'archived_axis':
            document['wavelengths_nm'] = axis['wavelengths_nm']
        elif axis:
            spec = document.get(axis['role'], {})
            if spec.get('kind') != 'npz' or not spec.get('paths') or not spec.get('wavelengths_key'):
                raise DraftIssue('从NPZ读取波长轴需要先明确该角色的数据源与波长字段')
            waves = None
            for path in spec['paths']:
                for file in self._archives(Path(path)):
                    with np.load(file, allow_pickle=False) as archive:
                        current = archive[spec['wavelengths_key']]
                        if current.ndim != 1 or not np.issubdtype(current.dtype, np.number) or not np.isfinite(current).all():
                            raise ValueError('NPZ波长轴须为有限的一维数值')
                        if waves is not None and not np.array_equal(current, waves):
                            raise ValueError('所选输入源的波长轴不一致')
                        waves = current.copy()
            document['wavelengths_nm'] = waves.astype(float).tolist()
        # Required scientific choices remain missing; solver tolerances retain the numerical contract defaults.
        for role in roles:
            if document.get(role, {}).get('kind') == 'npz':
                for key in ('labels_key', 'wavelengths_key'):
                    if not document[role].get(key):
                        raise DraftIssue(f'{role}.{key}：请明确NPZ标签与波长字段，或先检查输入源')
        if training_only and 'train' in document:
            document['test'] = deepcopy(document['train'])
            document['test'].pop('max_per_class', None)
        from .evaluation_definition import normalize_config
        config=ExperimentConfig.model_validate(document)
        return normalize_config(config, training_only=training_only) if normalize_evaluation else config

    def has_paired_inputs(self, session_id):
        from .pairing import can_train
        with connect_database(self.database) as db:
            row = db.execute('SELECT report_json FROM experiment_pairing WHERE session_id=?',(session_id,)).fetchone()
        return bool(row and can_train(json.loads(row[0])))

    def prepare_paired_baseline(self, session_id, check=None):
        from uuid import uuid4
        from spectrumagent.storage import guard
        from .group_split import manifest_path
        from .pairing import can_train, inventory
        from .service import write_json

        with connect_database(self.database) as db:
            saved = db.execute('SELECT report_json FROM experiment_pairing WHERE session_id=?',(session_id,)).fetchone()
        if not saved:
            raise DraftIssue('请先核对训练、测试原图与外部标注目录。')
        report = json.loads(saved[0])
        if not can_train(report):
            raise DraftIssue('需要训练和测试均有成功配对且无异常的预览，请先核对配对异常。')
        identifier = report.get('training_split_id')
        if identifier:
            current = self._read(session_id)
            if current and current['run_status']=='idle' and current['document'].get('split_id')==identifier:
                return
            path = manifest_path(self.service.paths.exports, identifier)
            if sha256(path) != report['training_split_sha256']:
                raise DraftIssue('已保存的配对来源清单发生变化，请重新配对。')
        else:
            pairs = report['pairs']
            if any('annotation_sha256' not in row for row in pairs):
                # Previous releases saved filenames and labels only. Verify them again before binding a draft.
                fields = {}
                for role, roots in report['roots'].items():
                    fields[role+'原图'] = list(map(Path, roots))
                    fields[role+'标注'] = sorted({Path(row['annotation']).parent for row in pairs if row['role']==role})
                if report.get('manifest_path'):
                    fields['清单'] = [Path(report['manifest_path'])]
                fresh = inventory(fields)
                def identities(rows):
                    return sorted((r['role'],r['hdr'],r['annotation'],r['labels'],r['regions']) for r in rows)
                if not can_train(fresh) or identities(fresh['pairs']) != identities(pairs):
                    raise DraftIssue('重新核验旧预览时发现来源或标注已变化，请重新预览。')
                pairs = fresh['pairs']
            rows = []
            for pair in pairs:
                img = Path(pair['img'])
                stat = img.stat()
                if (stat.st_size != pair['img_bytes'] or stat.st_mtime_ns != pair['img_mtime_ns']
                        or sha256(pair['hdr']) != pair['hdr_sha256'] or sha256(pair['annotation']) != pair['annotation_sha256']):
                    raise DraftIssue('原图或标注自配对后已变化，请重新预览。')
                img_hash = sha256(img,check)
                after = img.stat()
                if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                    raise DraftIssue('生成来源清单期间 IMG 有变化，请重新配对。')
                rows.append(dict(pair,split=pair['role'],group=pair['sample_id'] or pair['hdr'],img_sha256=img_hash))
            identifier = str(uuid4())
            path = manifest_path(self.service.paths.exports, identifier)
            guard.mkdir(path.parent,parents=True,exist_ok=True)
            write_json(path,dict(schema_version=1,split_id=identifier,source_kind='explicit_pairs',
                                 group_by='sample',one_image_one_sample=False,rows=rows))
            report.update(training_split_id=identifier,training_split_sha256=sha256(path))
            with connect_database(self.database) as db:
                if not db.execute('UPDATE experiment_pairing SET report_json=? WHERE session_id=? AND report_json=?',
                                  (json.dumps(report,ensure_ascii=False),session_id,saved[0])).rowcount:
                    raise DraftIssue('配对预览已更新，请重新查看当前配对。')
        self.prepare_split_baseline(session_id, f'"{path}"', paired=True)

    def prepare_split_baseline(self, session_id, location, *, paired=False):
        from .group_split import baseline_draft
        document = baseline_draft(self, session_id, location, PATHS)
        if paired:
            document['name'] = '显式配对 PLS-DA 基线 ' + document['split_id'][:8]
        if self.tasks.active(session_id):
            raise DataError('EXPERIMENT_BUSY', '实验已提交，暂不能新建基线方案')
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO experiment_dialogue(session_id) VALUES (?)', (session_id,))
            if self._read(session_id, db)['run_status'] == 'running':
                raise DataError('EXPERIMENT_BUSY', '本次实验正在运行，暂不能新建基线方案')
            db.execute("UPDATE experiment_dialogue SET document_json=?,revision=revision+1,reviewed_revision=NULL,"
                       "review_turn=NULL,review_sources_json=NULL,run_status='idle',experiment_id=NULL,active=1,"
                       "previous_document_json=NULL,base_experiment_id=NULL WHERE session_id=?",
                       (json.dumps(document, ensure_ascii=False, allow_nan=False), session_id))
            db.execute('UPDATE inference_draft SET active=0 WHERE session_id=?', (session_id,))
            self.clear_confirmation(db, session_id)

    def resume_training(self, session_id, *, archive_id=None, study_only=False):
        if self.tasks.active(session_id):
            raise DataError('EXPERIMENT_BUSY', '实验已提交，请在当前训练结束后修改方案。')
        focus = self.focus(session_id)
        prior_inference = self.inference.read(session_id)
        model_id = (archive_id or (focus or (None, None))[1] or self.selected(session_id) or
                    (prior_inference or {}).get('document', {}).get('model_id'))
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._read(session_id, db)
            self.clear_confirmation(db, session_id, 'inference')
            db.execute('UPDATE inference_draft SET active=0 WHERE session_id=?', (session_id,))
            if not archive_id and record and record['document'] and (record['run_status'] == 'idle' or
                                                   not model_id or model_id == record['experiment_id']):
                base = record['base_experiment_id'] if record['run_status'] == 'idle' else record['experiment_id']
                db.execute('UPDATE experiment_dialogue SET active=1,base_experiment_id=? WHERE session_id=?', (base, session_id))
                return base
        if not model_id:
            raise DataError('EXPERIMENT_DRAFT_REQUIRED', '请先提供训练和测试数据，或选择一项已有实验作为起点。')
        from .service import read_json
        document = (read_json(self.service.folder(model_id)/'config.json') if study_only
                    else deepcopy(self.service.get(model_id)['config']))
        document.pop('training_sampling',None)
        declared = self.service.sample_evaluations.declared(model_id)
        if declared is not None:
            document['sample_evaluation'] = declared
        stored_split = document.pop('split_manifest', None)
        waves = document.pop('wavelengths_nm')
        document.update(axis={'kind':'archived_axis', 'wavelengths_nm':waves},
                        classes=[{'label':int(key), 'name':name} for key,name in document['classes'].items()])
        if stored_split:
            from .group_split import load_saved_plan, manifest_path
            sides = load_saved_plan(manifest_path(self.service.paths.exports, stored_split['split_id']), stored_split['sha256'],
                                    verify_test=not study_only)
            document.update(split_id=stored_split['split_id'], split_sha256=stored_split['sha256'],
                            split_counts={title:len(rows) for title,rows in sides.items()},
                            split_test_uncovered=sorted({item['name'] for item in document['classes']} -
                                                        {label for row in sides['测试'] for label in row['labels']}))
        sources = {}
        def reference(path):
            if path not in sources:
                sources[path] = 'S'+str(len(sources)+1)
            return sources[path]
        for role in ('train', 'test'):
            spec = document[role]
            if spec['kind'] == 'npz':
                spec['source_refs'] = [reference(path) for path in spec.pop('paths')]
            elif stored_split:
                spec.pop('members')
            else:
                for member in spec['members']:
                    for field in ('header','data','roi','centers'):
                        value = member.pop(field+'_path', None)
                        if value:
                            member[field+'_ref'] = reference(value)
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO experiment_dialogue(session_id) VALUES (?)', (session_id,))
            updated = db.execute("UPDATE experiment_dialogue SET document_json=?,sources_json=?,revision=revision+1,active=1,"
                                 "reviewed_revision=NULL,review_turn=NULL,review_sources_json=NULL,run_status='idle',"
                                 "experiment_id=NULL,previous_document_json=NULL,base_experiment_id=? WHERE session_id=? AND revision=?",
                                 (json.dumps(document, ensure_ascii=False), json.dumps({v:k for k,v in sources.items()}, ensure_ascii=False),
                                  model_id, session_id, record['revision'] if record else 0))
            if not updated.rowcount:
                raise DataError('EXPERIMENT_DRAFT_CONFLICT', '草稿已更新，请重新选择要修改的实验。')
            self.clear_confirmation(db, session_id)
        return model_id

    def view(self, session_id):
        record = self._read(session_id)
        if record is None:
            raise DataError('EXPERIMENT_DRAFT_REQUIRED', '请先提供本次训练测试的输入或发起数值实验')
        issues, config = [], None
        try:
            config = self._config(record)
        except ValidationError as error:
            issues = [field_name(item['loc']) + '：' + ('尚未提供' if item['type'] == 'missing' else item['msg'].removeprefix('Value error, '))
                      for item in error.errors(include_input=False, include_url=False)]
        except DraftIssue as error:
            issues = [str(error)]
        except (ValueError, OSError, KeyError, TypeError):
            # Never include exception strings from file readers in model context.
            issues = ['数据源、类别映射或波长轴尚未明确或不合法；请检查输入字段、波长网格和源引用']
        can_study = False
        try:
            self._config(record, training_only=True)
            can_study = record['run_status'] == 'idle'
        except (ValidationError, DraftIssue, ValueError, OSError, KeyError, TypeError):
            pass
        shown = deepcopy(record['document'])
        if config is not None:
            shown['preprocessing'] = [step.model_dump() for step in config.preprocessing]
            shown['model'] = config.model.model_dump()
            for role in ('train', 'test'):
                shown[role]['evaluation_unit'] = getattr(config, role).evaluation_unit
                if shown.get('split_id'):
                    spec = getattr(config, role)
                    shown[role].update(mapping_window_nm=spec.mapping_window_nm, nearest_tolerance_nm=spec.nearest_tolerance_nm)
        plan = describe(shown)
        if record['base_experiment_id']:
            plan = '基于归档实验 ' + record['base_experiment_id'] + ' 修改。\n' + plan
        previous = record['previous_document_json']
        changes = draft_changes(json.loads(previous) if previous else None, record['document'])
        if changes:
            plan += '\n本轮变更\n' + '\n'.join('• '+change for change in changes)
        if config is not None:
            waves = config.wavelengths_nm
            if config.sample_evaluation:
                plan += f'\n实物评价定义：{config.sample_evaluation.mode}；有效观测阈值 {config.sample_evaluation.minimum_valid}；真值唯一，合并观测投票，平票排除。'
            if config.split_manifest and config.split_manifest.one_image_one_sample:
                plan += '\n实物口径：用户声明每幅图对应独立实物。'
            plan += f'\n已核验目标波长：{len(waves)}个，{waves[0]:g}至{waves[-1]:g} nm。'
            plan += '\n默认输出准确率、宏平均precision/recall/F1、各类指标、混淆矩阵、分类均值与标准差曲线。'
            plan += '\nPLS响应不作为校准概率；中心化、标准化和PCA仅在训练集拟合。'
        if issues:
            question = '请补充或修正：\n' + '\n'.join('• ' + item for item in issues[:16])
            if can_study and shown.get('workspace_selection') and not shown.get('test'):
                question = ('尚未指定测试集，不能执行正式训练测试。可以先发起“训练集内自动寻优”；'
                            '正式训练前可按下方编号指定，例如“将第2、4张设为测试，其余用于训练”。')
            if shown.get('split_id') and not shown.get('axis'):
                question += '\n原图没有可直接共用的已确认波长轴。请给出原图波长单位及目标波长网格（起止 nm、步长、映射窗口及最近通道容差）。'
        else:
            question = '请核对以上方案；回复“确认执行”启动本次训练测试，或直接说明要修改的内容。'
        if record['run_status'] != 'idle':
            question = {'succeeded': '本方案已经完成，可查询实验结果；如需重新实验，请明确新建实验。',
                        'running': '本方案已提交，尚无已核验终态；不会自动重复训练。',
                        'cancelled': '本方案已取消，已完成产物保留；请修改方案或明确新建实验后重新确认。',
                        'failed': '上次提交失败。可查询实验结果、修改参数，或明确新建实验后重新核对方案。'}[record['run_status']]
        return {'revision': record['revision'], 'status': 'needs_input' if issues else 'needs_confirmation',
                'plan': self.redact(session_id, plan), 'question': self.redact(session_id, question),
                'missing_count': len(issues), 'can_run': config is not None and record['run_status'] == 'idle',
                'run_status': record['run_status'], 'experiment_id': record['experiment_id'], 'can_study': can_study}

    def _saved_sides(self, document, session_id):
        if document.get('workspace_selection'):
            from .workspace_training import sides
            record = self._read(session_id)
            if not record or record['document'] != document:
                raise DraftIssue('当前工作台训练来源已更新，请重新查看方案。')
            return sides(document, record['sources'])
        from .group_split import load_saved_plan, manifest_path
        path = manifest_path(self.service.paths.exports, document['split_id'])
        return load_saved_plan(path, document['split_sha256'])

    def draft_presentation(self, session_id, view, check=None):
        from . import wavelength_proposal as wavelength
        from .study import group_kind, roi_group_support
        record = self._read(session_id)
        document = record['document']
        axis = document.get('axis') or {}
        counts = document.get('split_counts')
        summary = []
        if document.get('workspace_selection'):
            summary.append('已保存区域标注已接入统一训练流程；无需先运行旧配方预处理。')
            summary.append(document['notes'])
            summary.extend(f"第 {item['number']} 张 · {item['name']} · " + '、'.join(
                f'{name} {count} 像元' for name, count in item['counts'].items()) for item in document['workspace_selection'])
        if counts:
            summary.append(f"训练 {counts['训练']} 幅 · 测试 {counts['测试']} 幅 · {len(document.get('classes', []))} 类 · 按中心像元评价")
        else:
            sizes = []
            for key, title in (('train','训练'), ('test','测试')):
                spec = document.get(key) or {}
                if spec.get('kind') == 'roi_images' and spec.get('members'):
                    sizes.append(f"{title} {len(spec['members'])} 幅")
                elif spec.get('kind') == 'npz' and spec.get('source_refs'):
                    sizes.append(f"{title} {len(spec['source_refs'])} 个 NPZ 来源")
            if sizes:
                summary.append(' · '.join(sizes))
        usage = document.get('test_usage')
        if usage:
            summary.append('测试用途：开发复现核验' if usage == 'development_regression' else '测试用途：独立测试')
        checks = view.get('split_checks')
        if checks and checks['conflicts']:
            summary.append(f"划分核验发现 {len(checks['conflicts'])} 项交叉，请展开核对。")
        if checks and checks['physical_sample_independence'] == 'unknown':
            summary.append('实物独立性未知。')
        todo = '方案已就绪。可确认训练，或修改当前方案。' if view['can_run'] else view['question']
        if todo.startswith('请补充或修正：\n'):
            lines = todo.splitlines()
            todo = '\n'.join(lines[:3])
            if len(lines)>3:
                todo += '\n其余待补项见完整配置。'
        previous = record['previous_document_json']
        changes = draft_changes(json.loads(previous) if previous else None, document)
        result = dict(draft_revision=view['revision'], draft_summary='\n'.join(summary), draft_ready=view['can_run'],
                      draft_changes='\n'.join(self.redact(session_id,change) for change in changes))
        if (not counts and not document.get('workspace_selection')) or record['revision'] != view['revision'] or record['run_status'] != 'idle':
            return dict(result, draft_todo=todo)

        unit = document.get('train', {}).get('wavelength_unit')
        needs_grid = not axis or (axis.get('kind') == 'saved_native' and (
            axis.get('train_only') or grid_hint(axis['wavelengths'])))
        if needs_grid and unit:
            try:
                proposal = wavelength.recommend(self._saved_sides(document, session_id), unit, check)
                if 'problem' in proposal:
                    todo = proposal['problem']
                else:
                    todo = '建议先把原图统一到等间距的共同波段。'
                    if proposal['bands'] >= 4:
                        step = proposal['step']
                        low, high = proposal['start']+step, proposal['stop']-step
                        todo += f'如需裁掉首尾噪声，可回复范围，例如“改为 {low:g}–{high:g} nm”。'
                    result['wavelength_label'] = wavelength.grid_label(proposal)
                payload = json.dumps(proposal, ensure_ascii=False, allow_nan=False)
                with connect_database(self.database) as db:
                    db.execute('BEGIN IMMEDIATE')
                    current = self._read(session_id, db)
                    if (current['revision'], current['run_status']) == (record['revision'], 'idle'):
                        db.execute('INSERT OR REPLACE INTO experiment_wavelength_proposal VALUES (?,?,?)',
                                   (session_id, record['revision'], payload))
                        result['wavelength_details'] = payload
            except (OSError, ValueError, DataError):
                todo = '原图波长核验未完成，请检查草稿里的 HDR 和波长单位。'
        elif (view['can_run'] or view.get('can_study')) and not document.get('preprocessing') and document.get('model', {}).get('n_components') == 1:
            try:
                rows = []
                config = self._config(record, training_only=True, train_manifest_rows=rows)
                kind = group_kind(config, {'grouping':'auto'})
                support = roi_group_support(config, rows, kind)
                if support and (folds := min(3, min(support.values()))) >= 2:
                    grouping = {'image':'按原图分组', 'sample':'按实物分组', 'batch':'按批次分组'}[kind]
                    sg = '' if grid_hint(config.wavelengths_nm) or len(config.wavelengths_nm)<3 else ' · 含 SG1/SG2'
                    result.update(study_folds=folds, study_label=f'{folds} 折 · {grouping}{sg}')
                    todo = '波长已对齐。可先在训练集内比较预处理和潜变量；正式训练测试前须明确测试集。'
                elif support:
                    todo = '波长已对齐。至少一个类别的训练分组不足两组。可调整方案，或先运行当前基线。'
            except (OSError, ValueError, KeyError, DataError):
                pass
        return dict(result, draft_todo=todo)

    def can_crop_wavelength(self, session_id):
        record = self._read(session_id)
        if not record or record['run_status'] != 'idle' or not (record['document'].get('split_id') or record['document'].get('workspace_selection')):
            return False
        if (record['document'].get('axis') or {}).get('kind') == 'grid':
            return True
        with connect_database(self.database) as db:
            return bool(db.execute('SELECT 1 FROM experiment_wavelength_proposal WHERE session_id=? AND revision=?',
                                   (session_id,record['revision'])).fetchone())

    def apply_wavelength(self, session_id, revision=None, bounds=None, *, check=None):
        from spectrumagent.agent.tools.experiments import DraftUpdate
        from .wavelength_proposal import recommend
        with connect_database(self.database) as db:
            record = self._read(session_id, db)
            saved = db.execute('SELECT revision,document FROM experiment_wavelength_proposal WHERE session_id=?',
                               (session_id,)).fetchone()
        if (not record or not (record['document'].get('split_id') or record['document'].get('workspace_selection')) or record['run_status'] != 'idle'
                or revision is not None and revision != record['revision']):
            raise DraftIssue('这份波长建议已过期，请先查看当前实验方案。')
        proposal = json.loads(saved[1]) if saved and saved[0] == record['revision'] else None
        document = record['document']
        axis = document.get('axis') or {}
        if bounds and axis.get('kind') == 'grid':
            spec = document['train']
            required = ('mapping_window_nm','nearest_tolerance_nm','wavelength_unit')
            if any(spec.get(field) is None for field in required):
                raise DraftIssue('请先补充波长单位、映射窗口与最近通道容差。')
            grid = (axis['step_nm'],spec['mapping_window_nm'],spec['nearest_tolerance_nm'],axis['start_nm'],bounds)
        elif bounds and proposal and 'problem' not in proposal:
            grid = (proposal['step'],proposal['window'],proposal['tolerance'],proposal['start'],bounds)
        elif not proposal:
            raise DraftIssue('这份波长建议已过期，请先查看当前实验方案。')
        sides = self._saved_sides(document, session_id)
        if bounds and (axis.get('kind') == 'grid' or 'problem' not in proposal):
            proposal = recommend(sides, document['train']['wavelength_unit'], check, grid=grid)
        if 'problem' in proposal:
            raise DraftIssue(proposal['problem'])
        self.update(session_id, DraftUpdate(expected_revision=record['revision'],
                    axis=dict(kind='grid',start_nm=proposal['start'],stop_nm=proposal['stop'],step_nm=proposal['step']),
                    train=dict(kind='roi_images',mapping_window_nm=proposal['window'],
                               nearest_tolerance_nm=proposal['tolerance'])))

    def update(self, session_id, arguments):
        if self.tasks.active(session_id):
            raise DataError('EXPERIMENT_BUSY', '实验已提交，不能修改正在运行的方案')
        patch = arguments.model_dump(mode='json', exclude_unset=True)
        revision = patch.pop('expected_revision')
        reset = patch.pop('reset', False)
        edit = patch.pop('preprocessing_edit', None)
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._read(session_id, db)
            if record is None or revision != record['revision']:
                raise DataError('EXPERIMENT_DRAFT_CONFLICT', '实验草稿已更新，请读取最新修订后合并')
            if record['run_status'] == 'running':
                raise DataError('EXPERIMENT_BUSY', '本次实验正在运行，不能修改其配置')
            if (record['document'].get('split_id') or record['document'].get('workspace_selection')) and not reset:
                extraction = {}
                sampling = {}
                for role in ('train', 'test'):
                    if role not in patch:
                        continue
                    spec = patch[role]
                    if not spec or spec.get('kind') != 'roi_images' or 'members' in spec:
                        raise DataError('SPLIT_MEMBERS_FIXED', '已保存划分决定训练和测试的图像，可修改共用取谱参数')
                    for field in ('max_per_class', 'sampling_seed'):
                        if field in spec:
                            if role != 'train':
                                raise DataError('EXPERIMENT_SAMPLING_INVALID', '类别抽样只用于训练侧')
                            sampling[field] = spec.pop(field)
                    if set(spec) == {'kind'}:
                        continue
                    extraction[role] = spec
                if len(extraction) == 2:
                    merged = [merge({key:value for key,value in record['document'][role].items()
                                     if key not in ('members', 'max_per_class', 'sampling_seed')}, spec)
                              for role, spec in extraction.items()]
                    if merged[0] != merged[1]:
                        raise DataError('SPLIT_EXTRACTION_CONFLICT', '训练和测试须共用同一套取谱与采样规则')
                elif extraction:
                    shared = next(iter(extraction.values()))
                    patch.update({role: deepcopy(shared) for role in ('train', 'test') if record['document'].get(role)})
                if sampling:
                    patch['train'] = {**patch.get('train',{}), **sampling}
            if edit:
                patch['preprocessing'] = edit_preprocessing(record['document'], edit)
            base = deepcopy({} if reset else record['document'])
            if 'sample_evaluation' in patch:
                base.pop('sample_evaluation', None)
            document = merge(base, patch)
            if document != record['document'] or reset:
                db.execute("UPDATE experiment_dialogue SET document_json=?,revision=revision+1,reviewed_revision=NULL,"
                           "review_turn=NULL,review_sources_json=NULL,run_status='idle',experiment_id=NULL,active=1,"
                           "previous_document_json=?,base_experiment_id=? WHERE session_id=?",
                           (json.dumps(document, ensure_ascii=False, allow_nan=False),
                            json.dumps(record['document'], ensure_ascii=False) if record['document'] else None,
                            None if reset else record['base_experiment_id'], session_id))
                self.clear_confirmation(db, session_id)
        return self.view(session_id)

    def presented(self, session_id, turn, *, check=None):
        view = self.view(session_id)
        if view['can_run']:
            config = self._config(self._read(session_id))
            try:
                sources, checks = self.review_sources(config, check=check)
                view.update(split_checks=checks, plan=view['plan']+'\n'+self.redact(session_id, split_check_text(checks)))
                enforce_split(config.test_usage, checks)
            except (DataError, OSError, ValueError) as error:
                detail = ('请修正训练／测试划分，或改作开发复现核验。' if isinstance(error, DataError)
                          and error.code == 'EXPERIMENT_SPLIT_OVERLAP' else '无法读取方案中的文件，请核对文件清单。')
                view.update(can_run=False, status='needs_input', question=detail)
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._read(session_id, db)
            if current['revision'] != view['revision'] or current['run_status'] != 'idle':
                view.update(can_run=False)
            else:
                db.execute('UPDATE inference_draft SET active=0 WHERE session_id=?', (session_id,))
                if view['can_run']:
                    db.execute('UPDATE experiment_dialogue SET reviewed_revision=?,review_turn=?,review_sources_json=? WHERE session_id=?',
                               (view['revision'], turn, json.dumps(sources, ensure_ascii=False), session_id))
                    self.set_confirmation(db, session_id, 'experiment', view['revision'], turn)
                else:
                    db.execute('UPDATE experiment_dialogue SET reviewed_revision=NULL,review_turn=NULL,review_sources_json=NULL WHERE session_id=?', (session_id,))
                    self.clear_confirmation(db, session_id)
        return view

    def review_sources(self, config, *, check=None):
        if check:
            check()
        reference = config.split_manifest
        if not reference:
            return split_preflight(config, check=check)
        from .group_split import load_saved_plan, manifest_path
        path = manifest_path(self.service.paths.exports, reference.split_id)
        sides = load_saved_plan(path, reference.sha256)
        rows = sides['训练'] + sides['测试']
        fingerprints = None
        if all(row.get('img_sha256') for row in rows):
            fingerprints = {str(Path(row[key]).resolve()): {'sha256':row[key+'_sha256']}
                            for row in rows for key in ('hdr','img','annotation')}
        sources, checks = split_preflight(config, fingerprints, check=check)
        sources[str(path.resolve())] = reference.sha256
        return sources, checks

    def cancel(self, session_id):
        with connect_database(self.database) as db:
            db.execute('UPDATE experiment_dialogue SET active=0,reviewed_revision=NULL,review_turn=NULL WHERE session_id=?', (session_id,))
            self.clear_confirmation(db, session_id, 'experiment')

    def invalidate_review(self, session_id):
        with connect_database(self.database) as db:
            db.execute('UPDATE experiment_dialogue SET reviewed_revision=NULL,review_turn=NULL,review_sources_json=NULL WHERE session_id=?', (session_id,))
            self.clear_confirmation(db, session_id, 'experiment')

    def run_confirmed(self, session_id, content, turn, *, progress=None, on_detail=None, expected_revision=None, accepted_plan=None):
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._read(session_id, db)
            if (not record or not CONFIRM.fullmatch(content.strip()) or record['reviewed_revision'] != record['revision']
                    or record['review_turn'] == turn or not record['review_sources_json']
                    or expected_revision is not None and expected_revision != record['revision']):
                raise DataError('EXPERIMENT_CONFIRMATION_REQUIRED', '请先核对完整实验方案，再单独回复“确认执行”')
            if record['run_status'] == 'succeeded':
                return self.service.get(record['experiment_id'])
            if record['run_status'] != 'idle':
                raise DataError('EXPERIMENT_ALREADY_SUBMITTED', '本方案已提交，先查询已记录结果；不会自动重复训练')
            target = ('experiment', record['revision'], record['review_turn'])
            if accepted_plan != target:
                if self.confirmation(session_id, db) != target:
                    raise DataError('EXPERIMENT_CONFIRMATION_REQUIRED', '当前训练方案没有等待确认，请重新审阅。')
                self.clear_confirmation(db, session_id, 'experiment')
            try:
                config = self._config(record)
            except DraftIssue as error:
                raise DataError('EXPERIMENT_INPUT_CHANGED', str(error)) from error
            db.execute("UPDATE experiment_dialogue SET run_status='running' WHERE session_id=?", (session_id,))
            db.execute('DELETE FROM experiment_selection WHERE session_id=?', (session_id,))
        try:
            options = {'expected_sources': json.loads(record['review_sources_json'])}
            if progress is not None:
                options['progress'] = progress
            if on_detail is not None:
                options['on_detail'] = on_detail
            result = self.service.run(config, **options)
        except Exception as error:
            identifier = error.payload.context.get('experiment_id') if isinstance(error, DataError) else None
            with connect_database(self.database) as db:
                status = 'cancelled' if isinstance(error, DataError) and error.code == 'EXPERIMENT_CANCELLED' else 'failed'
                db.execute('UPDATE experiment_dialogue SET run_status=?,experiment_id=? WHERE session_id=?', (status, identifier, session_id))
            raise
        with connect_database(self.database) as db:
            db.execute("UPDATE experiment_dialogue SET run_status='succeeded',experiment_id=?,active=0 WHERE session_id=?",
                       (result['experiment_id'], session_id))
        self.select(session_id, result['experiment_id'])
        return result

    def result(self, session_id):
        selected = self.selected(session_id)
        if selected:
            return self.service.get(selected)
        record = self._read(session_id)
        if record and record['experiment_id']:
            return self.service.get(record['experiment_id'])
        return None

    def selected(self, session_id):
        with connect_database(self.database) as db:
            row = db.execute('SELECT experiment_id FROM experiment_selection WHERE session_id=?', (session_id,)).fetchone()
        return row[0] if row else None

    def select(self, session_id, identifier):
        item = self.service.archive.item(identifier)
        with connect_database(self.database) as db:
            db.execute('INSERT INTO experiment_selection VALUES (?,?) ON CONFLICT(session_id) '
                       'DO UPDATE SET experiment_id=excluded.experiment_id', (session_id, identifier))
            self.set_focus(db, session_id, 'experiment', identifier)
        return {'archived_experiment_id': identifier, **{key: value for key, value in item.items() if key != 'experiment_id'}}

    def history_list(self, offset=0, limit=10):
        page = self.service.archive.list(offset=offset, limit=limit)
        summary = {'total': page['total'], 'offset': offset, 'count': len(page['items'])}
        for index, row in enumerate(page['items'], 1):
            for key, value in row.items():
                summary[f'item_{index}_{key}'] = value
        return summary

    def compare(self, first, second):
        comparison = self.service.archive.compare(first, second)
        summary = {key: comparison[key] for key in ('first', 'second', 'comparable', 'note')}
        summary.update({'same_' + key: value for key, value in comparison['checks'].items()})
        for prefix, scores in zip(('first', 'second'), comparison['metrics']):
            for role in ('train', 'test'):
                for key in ('n', 'correct', 'accuracy', 'macro_f1', 'kappa', 'evaluation_unit', 'purpose'):
                    if key in scores[role]:
                        summary[f'{prefix}_{role}_{key}'] = scores[role][key]
        return summary
