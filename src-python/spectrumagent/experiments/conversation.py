"""Session-owned drafts and reviewed execution, independent of model prose."""
from copy import deepcopy
import json
from pathlib import Path
import re

import numpy as np
from pydantic import ValidationError

from backend.database import connect_database
from spectrumagent.data import DataError
from .schema import ExperimentConfig
from .inputs import sha256


# Quote paths containing spaces. Bare paths terminate at Chinese punctuation.
PATHS = re.compile(r'''["“‘'](?P<quoted>(?:[A-Za-z]:[\\/]|/)[^"”’'\r\n]+)["”’']|(?P<bare>[A-Za-z]:[\\/][^\s,，。；;、"“”‘’'<>]+|(?<![\w:/])/(?:[^\s,，。；;、"“”‘’'<>]+))''')
CONFIRM = re.compile(r'(?:请)?(?:确认(?:方案)?(?:并)?(?:开始)?(?:执行|训练|运行)|按(?:此|这个|上述)方案(?:执行|训练)|开始训练)[。！!\s]*')
START = re.compile(r'PLS[-_ ]?DA|训练.*测试|train.*test|训练(?:数据|集)|测试(?:数据|集)|独立测试|数值实验', re.I)
CANCEL = re.compile(r'(?:取消|退出|停止)(?:本次|当前)?(?:数值)?实验[。！!\s]*')
HISTORY = re.compile(r'(?:历史|上次|最近|归档).{0,8}实验|(?:实验|训练测试)(?:结果|报告)|(?:比较|对比).{0,20}实验|实验.{0,8}(?:历史|归档)')


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


def describe(document):
    """Human-readable plan; references replace local file locations."""
    lines = ['实验名称：' + document.get('name', '待补充')]
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
            stages = {'spectra': '未做空间平均的光谱矩阵', 'neighborhood_mean': '已完成邻域均值的光谱矩阵'}
            lines.append('  输入阶段：' + stages.get(spec.get('input_stage'), '待补充'))
        else:
            members = spec.get('members', [])
            lines.append(title + '：原图与ROI，共 ' + str(len(members)) + ' 个显式配对')
            for member in members:
                lines.append('  ' + member['sample_id'] + '：HDR ' + member['header_ref'] + '，ROI ' + member['roi_ref']
                             + ('，数据 ' + member['data_ref'] if member.get('data_ref') else '')
                             + ('，中心列表 ' + member['centers_ref'] if member.get('centers_ref') else ''))
            lines.append('  波长单位 ' + spec.get('wavelength_unit', '待补充') + '；映射窗口 ' + str(spec.get('mapping_window_nm', '待补充'))
                         + ' nm；最近通道容差 ' + str(spec.get('nearest_tolerance_nm', '待补充')) + ' nm')
            quality = spec.get('quality', {})
            lines.append('  质量筛选：' + '，'.join(key + '=' + str(value) for key, value in quality.items()))
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
            db.execute('''CREATE TABLE IF NOT EXISTS experiment_pairing (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id), report_json TEXT NOT NULL)''')
            if 'replay_id' not in {r[1] for r in db.execute('PRAGMA table_info(experiment_pairing)')}:
                db.execute('ALTER TABLE experiment_pairing ADD COLUMN replay_id TEXT')
            db.execute('''CREATE TABLE IF NOT EXISTS experiment_selection (
                session_id TEXT PRIMARY KEY REFERENCES agent_session(id), experiment_id TEXT NOT NULL)''')
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
        from .tasks import ExperimentTasks
        self.tasks = ExperimentTasks(self)
        from .inference_dialogue import InferenceDialogue
        self.inference = InferenceDialogue(self)

    def _read(self, session_id, db=None):
        if db is None:
            with connect_database(self.database) as connection:
                return self._read(session_id, connection)
        row = db.execute('SELECT revision,document_json,sources_json,active,reviewed_revision,review_turn,run_status,experiment_id,review_sources_json '
                         'FROM experiment_dialogue WHERE session_id=?', (session_id,)).fetchone()
        if row is None:
            return None
        return dict(zip(('revision', 'document', 'sources', 'active', 'reviewed_revision', 'review_turn', 'run_status', 'experiment_id', 'review_sources_json'),
                        (row[0], json.loads(row[1]), json.loads(row[2]), *row[3:])))

    def pairing_answer(self, session_id, content, check=lambda: None):
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
            report = inventory(directories(content, PATHS))
        except (OSError, ValueError) as error:
            return '未生成新的配对预览。' + str(error)
        with connect_database(self.database) as db:
            db.execute('INSERT INTO experiment_pairing(session_id,report_json) VALUES (?,?) ON CONFLICT(session_id) DO UPDATE '
                       'SET report_json=excluded.report_json,replay_id=NULL', (session_id, json.dumps(report, ensure_ascii=False)))
        return overview(report)

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

    def capture(self, session_id, content):
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO experiment_dialogue(session_id) VALUES (?)', (session_id,))
            record = self._read(session_id, db)
            for match in PATHS.finditer(content):
                value = match['quoted'] or match['bare']
                if value not in record['sources'].values():
                    record['sources']['S' + str(len(record['sources']) + 1)] = value
            active = record['active'] or bool(START.search(content) or re.search(r'继续(?:数值)?实验', content))
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
        files = sorted(path.rglob('*.npz')) if path.is_dir() else [path]
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

    def _config(self, record):
        document = deepcopy(record['document'])
        axis = document.pop('axis', None)
        for role in ('train', 'test'):
            spec = document.get(role)
            if not isinstance(spec, dict):
                continue
            if spec.get('kind') == 'npz':
                refs = spec.pop('source_refs', [])
                spec['paths'] = [str(self._source(record, ref)) for ref in refs]
            elif spec.get('kind') == 'roi_images':
                for member in spec.get('members', []):
                    for key in ('header', 'roi', 'data', 'centers'):
                        ref = member.pop(key + '_ref', None)
                        if ref is not None:
                            member[key + '_path'] = str(self._source(record, ref))
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
        for role in ('train', 'test'):
            if document.get(role, {}).get('kind') == 'npz':
                for key in ('labels_key', 'wavelengths_key'):
                    if not document[role].get(key):
                        raise DraftIssue(f'{role}.{key}：请明确NPZ标签与波长字段，或先检查输入源')
        return ExperimentConfig.model_validate(document)

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
        shown = deepcopy(record['document'])
        if config is not None:
            shown['preprocessing'] = [step.model_dump() for step in config.preprocessing]
            shown['model'] = config.model.model_dump()
            for role in ('train', 'test'):
                shown[role]['evaluation_unit'] = getattr(config, role).evaluation_unit
        plan = describe(shown)
        if config is not None:
            waves = config.wavelengths_nm
            plan += f'\n已核验目标波长：{len(waves)}个，{waves[0]:g}至{waves[-1]:g} nm。'
            plan += '\n默认输出准确率、宏平均precision/recall/F1、各类指标、混淆矩阵、分类均值与标准差曲线。'
            plan += '\nPLS响应不作为校准概率；中心化、标准化和PCA仅在训练集拟合。'
        if issues:
            question = '请补充或修正：\n' + '\n'.join('• ' + item for item in issues[:16])
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
                'run_status': record['run_status'], 'experiment_id': record['experiment_id']}

    def update(self, session_id, arguments):
        if self.tasks.active(session_id):
            raise DataError('EXPERIMENT_BUSY', '实验已提交，不能修改正在运行的方案')
        patch = arguments.model_dump(mode='json', exclude_unset=True)
        revision = patch.pop('expected_revision')
        reset = patch.pop('reset', False)
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            record = self._read(session_id, db)
            if record is None or revision != record['revision']:
                raise DataError('EXPERIMENT_DRAFT_CONFLICT', '实验草稿已更新，请读取最新修订后合并')
            if record['run_status'] == 'running':
                raise DataError('EXPERIMENT_BUSY', '本次实验正在运行，不能修改其配置')
            document = merge({} if reset else record['document'], patch)
            if document != record['document'] or reset:
                db.execute("UPDATE experiment_dialogue SET document_json=?,revision=revision+1,reviewed_revision=NULL,"
                           "review_turn=NULL,review_sources_json=NULL,run_status='idle',experiment_id=NULL,active=1 WHERE session_id=?",
                           (json.dumps(document, ensure_ascii=False, allow_nan=False), session_id))
        return self.view(session_id)

    def presented(self, session_id, turn):
        view = self.view(session_id)
        if view['can_run']:
            config = self._config(self._read(session_id))
            sources = self.review_sources(config)
            with connect_database(self.database) as db:
                db.execute('UPDATE experiment_dialogue SET reviewed_revision=?,review_turn=?,review_sources_json=? WHERE session_id=? AND revision=?',
                           (view['revision'], turn, json.dumps(sources, ensure_ascii=False), session_id, view['revision']))
        return view

    def review_sources(self, config):
        from spectrumagent.data.readers import open_envi
        files = set()
        for spec in (config.train, config.test):
            if spec.kind == 'npz':
                for value in spec.paths:
                    files.update(self._archives(Path(value)))
            else:
                for member in spec.members:
                    dataset = open_envi(member.header_path, member.data_path, raw=True)
                    files.update((Path(dataset.header_path), Path(dataset.data_path)))
                    files.add(Path(member.roi_path))
                    if member.centers_path:
                        files.add(Path(member.centers_path))
        return {str(path.resolve()): sha256(path) for path in sorted(files)}

    def cancel(self, session_id):
        with connect_database(self.database) as db:
            db.execute('UPDATE experiment_dialogue SET active=0,reviewed_revision=NULL,review_turn=NULL WHERE session_id=?', (session_id,))

    def run_confirmed(self, session_id, content, turn, *, progress=None, expected_revision=None):
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
            config = self._config(record)
            db.execute("UPDATE experiment_dialogue SET run_status='running' WHERE session_id=?", (session_id,))
            db.execute('DELETE FROM experiment_selection WHERE session_id=?', (session_id,))
        try:
            options = {'expected_sources': json.loads(record['review_sources_json'])}
            if progress is not None:
                options['progress'] = progress
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
