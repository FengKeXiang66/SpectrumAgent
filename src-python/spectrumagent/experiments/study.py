"""Reviewed training-only model selection and durable Study results."""
from copy import deepcopy
from pathlib import Path
import json
import re
from threading import Event, RLock, Thread
from time import monotonic, time
from uuid import uuid4

import numpy as np
from threadpoolctl import threadpool_limits

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.storage import guard
from .inputs import check_sources, load_input, sha256
from .pipeline import SpectralPipeline
from .schema import ExperimentConfig, grid_hint
from .service import read_json, save_arrays, write_json

CONFIRM = re.compile(r'确认(?:探索性)?(?:运行)?\s*(?:寻优|Study)[。！!\s]*',re.I)
ADOPT = re.compile(r'采用(?:(推荐方案|最高分方案)|候选\s*(\d+))\s*新建正式训练(?:\s+([0-9a-f-]{36}))?[。！!\s]*')
QUERY = re.compile(r'(?:查看|查询)(?:本次|最近)?(?:(?:Study|寻优)(?:结果|进度|推荐)?|推荐)[。！!\s]*', re.I)
INTENT = re.compile(r'寻优|\bStudy\b|交叉验证|(?:哪种|选|寻找).{0,24}预处理.{0,24}潜变量', re.I)
TERMINAL = {'succeeded','failed','cancelled','interrupted'}
UPPER_BOUND_HINT = '最高分潜变量已触及本次上界，可扩宽潜变量范围继续寻优。'


def requested(text):
    return bool(ADOPT.fullmatch(text) or QUERY.fullmatch(text) or CONFIRM.fullmatch(text) or INTENT.search(text))


FOLDS = re.compile(r"(?:折数\s*[:：为=]?\s*(\d+)|(\d+)\s*折)")
EDIT = re.compile(r'^(?:调整|修改|调|改|整|修)寻优')
EXTRACTION_OPTIONS = re.compile(r'步长|每类(?:的)?(?:(?:抽样|采样)?上限|最多|最大)|(?:抽样|采样)种子|'
                                r'\b(?:sampling_stride|max_per_class|sampling_seed)\b', re.I)


def sampling_text(spec):
    if spec.kind == 'npz':
        return '采样步长沿用已取谱 NPZ · 每类上限不限（沿用输入）'
    limit = spec.max_per_class
    text = f'采样步长 {spec.sampling_stride} 像元 · 每类上限 {limit if limit is not None else "不限"}'
    return text + (f' · 抽样种子 {spec.sampling_seed}' if limit is not None else '')


def options(text, waves, current):
    def number(pattern, default):
        values = re.findall(pattern, text)
        return int(values[-1]) if values else default

    matches = FOLDS.findall(text)
    folds = int(matches[-1][0] or matches[-1][1]) if matches else 3
    if not 2 <= folds <= 10:
        raise ValueError('折数须为 2 至 10')
    seed = number(r'(?:随机)?种子\s*[:：为=]?\s*(\d+)', 42)
    matches = re.findall(r'潜变量\s*(?:范围)?\s*[:：为=]?\s*(\d+)\s*(?:\.\.|[-–~～到至])\s*(\d+)',text)
    low, high = tuple(map(int, matches[-1])) if matches else (2, min(16, len(waves)))
    if not 1 <= low <= high <= min(64, len(waves)) or not 0 <= seed < 2**32:
        raise ValueError('请指定合法的潜变量范围和 32 位非负随机种子')
    delta = np.diff(waves)
    uniform = np.allclose(delta, delta[0], rtol=1e-8, atol=1e-10)
    specified = re.findall(r'SG\s*(?:窗口|窗长)\s*[:：为=]?\s*(\d+(?:\s*[、，,]\s*\d+)*)',text,re.I)
    if specified:
        windows = list(dict.fromkeys(map(int,re.findall(r'\d+',specified[-1]))))
        if any(window < 3 or window > len(waves) or window%2==0 for window in windows):
            raise ValueError('SG 窗口必须是 3 至波段数之间的奇数')
    else:
        windows = [9,15] if len(waves)>=15 else [min(9,len(waves) if len(waves)%2 else len(waves)-1)]
    variants = {'原谱':[]}
    if len(waves) >= 3 and uniform:
        for derivative in (1,2):
            variants[f'SG{derivative}'] = [dict(op='savgol',polyorder=2,
                                               derivative=derivative,delta_nm=float(delta[0]))]
    norms = {'无':[], 'L2':[{'op':'l2'}], 'SNV':[{'op':'snv'}]}
    def choose(pattern, allowed):
        matches = re.findall(pattern, text, re.I)
        if not matches:
            return list(allowed)
        names = [value.strip() for value in re.split(r'[、,，/]',matches[-1]) if value.strip()]
        names = [next((name for name in allowed if name.casefold()==value.casefold()), value) for value in names]
        if not names or set(names)-allowed.keys():
            raise ValueError('候选取值可用 '+ '、'.join(allowed))
        return list(dict.fromkeys(names))
    profiles = choose(r'(?:预处理候选|光谱候选)\s*[:：]\s*([^；;。\n]+)',variants)
    normalization = choose(r'归一化候选\s*[:：]\s*([^；;。\n]+)',norms)
    center = [] if '不中心化' in text else [{'op':'center'}]
    preparations = []
    for name in profiles:
        for window in windows if name!='原谱' else [None]:
            steps = [dict(step,window=window) for step in variants[name]]
            label = f'{name}(W{window})' if window and len(windows)>1 else name
            preparations.extend({'name':label+' / '+norm, 'steps':steps+norms[norm]+center} for norm in normalization)
    if '加入当前预处理' in text:
        preparations.append({'name':'当前预处理', 'steps':current})
    grouping = 'image' if re.search(r'按原图|按图像|按图片',text) else 'batch' if re.search(r'按批次|分组方式\s*[:：]\s*批次',text) else (
        'sample' if re.search(r'按实物|按样品',text) else 'auto')
    return dict(folds=folds,seed=seed,components=list(range(low,high+1)),preparations=preparations,grouping=grouping)


def group_kind(config, settings):
    spec = config.train
    if spec.kind == 'npz':
        return 'npz_group' if spec.groups_key else 'exploratory'
    manifest = config.split_manifest
    kind = (manifest.group_by if manifest else 'sample') if settings['grouping']=='auto' else settings['grouping']
    unknown = any(not m.sample_id or m.sample_id == m.header_path for m in spec.members)
    if kind == 'sample' and unknown and not (manifest and manifest.one_image_one_sample):
        if settings['grouping']=='sample':
            raise ValueError('缺少真实实物编号。请补充编号，或明确按原图分组作探索性寻优。')
        return 'batch' if all(m.batch for m in spec.members) else 'image'
    return kind


def image_group(source, sample_id):
    # Keep repeated known objects together even when some other images lack IDs.
    return 'sample:'+sample_id if sample_id and sample_id != source else 'image:'+source


def roi_group_support(config, rows, kind):
    if config.train.kind != 'roi_images':
        return None
    support = {name:set() for name in config.classes.values()}
    batch_by_sample = {}
    complete_labels = True
    for index, member in enumerate(config.train.members):
        if kind == 'batch':
            group = member.batch
            if not group:
                raise ValueError('缺少批次编号，请补充批次或更改分组方式。')
            if (member.sample_id and member.sample_id != member.header_path and
                    batch_by_sample.setdefault(member.sample_id,group) != group):
                raise ValueError('同一实物跨批次，请改为按实物分组。')
        elif kind == 'image':
            group = image_group(member.header_path, member.sample_id)
        else:
            group = member.sample_id
        if rows:
            labels = rows[index]['labels']
        elif member.roi_path.lower().endswith('.json'):
            annotation = json.loads(Path(member.roi_path).read_text('utf-8-sig'))
            labels = {region['label'] for region in annotation['shapes']}
        elif member.roi_path.lower().endswith('.npz'):
            with np.load(member.roi_path, allow_pickle=False) as archive:
                labels = {config.classes[int(value)] for value in np.unique(archive['label_map'][archive['region_map'] > 0])}
        else:
            complete_labels = False
            continue
        for label in labels:
            if label in support:
                support[label].add(group)
    return {label:len(groups) for label, groups in support.items()} if complete_labels else None



def study_group_support(config, rows, kind):
    if kind != 'npz_group':
        return roi_group_support(config,rows,kind)
    spec = config.train
    support = {label:set() for label in config.classes}
    # Use only label and group metadata. Spectral arrays remain unopened.
    for path in spec.paths:
        with np.load(path,allow_pickle=False) as archive:
            labels, groups = archive[spec.labels_key], archive[spec.groups_key]
        if labels.ndim!=1 or groups.shape!=labels.shape or groups.dtype.kind not in 'iuUS':
            raise ValueError('NPZ 分组字段须为逐条对应的整型或字符串。')
        groups = groups.astype(str)
        if any(not value.strip() for value in groups):
            raise ValueError('NPZ 分组字段含空组。')
        for label in support:
            support[label].update(np.unique(groups[labels==label]))
    return {config.classes[label]:len(values) for label,values in support.items()}

def check_group_support(support, folds):
    if support and (limit := min(support.values())) < folds:
        limited = '、'.join(f'{label} {count} 组' for label, count in support.items() if count<folds)
        suggestion = f'请将折数改为 {limit}（可发送“调整寻优，折数 {limit}”）或补充训练组。' if limit>=2 else '至少需要每类两个训练组，请补充数据。'
        raise ValueError(f'拟用 {folds} 折，训练标注可用分组不足（{limited}）。'+suggestion)


def make_folds(data, kind, opts, config):
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

    groups = None
    if kind != 'exploratory':
        key = 'batch' if kind == 'batch' else 'sample_id'
        groups = ([image_group(row['source'], row.get('sample_id')) for row in data.origins]
                  if kind=='image' else [row.get(key) for row in data.origins])
        if any(not value for value in groups):
            raise ValueError('存在缺失的分组编号，请为训练图像补充已选的实物或批次分组')
        if kind == 'sample' and not (config.split_manifest and config.split_manifest.one_image_one_sample):
            if any(value == row['source'] for value,row in zip(groups,data.origins)):
                raise ValueError('存在未知实物编号，请补充分组或明确每幅图是独立实物')
        if kind == 'batch':
            batches = {}
            for group,row in zip(groups,data.origins):
                item = row.get('sample_id')
                if item and item != row['source'] and batches.setdefault(item,group) != group:
                    raise ValueError('同一实物出现在多个批次，请改为按实物分组')
        groups = np.asarray(groups,dtype=str)
    n = opts['folds']
    labels = sorted(config.classes)
    support = {str(label):int(len(np.unique(groups[data.y == label])) if groups is not None
                              else np.count_nonzero(data.y == label)) for label in labels}
    if min(support.values()) < n:
        raise ValueError(f'折数 {n} 过多。各类可用{"分组" if groups is not None else "样本"}数 {support}，请减少折数或补充数据')
    for attempt in range(16 if groups is not None else 1):
        seed = (opts['seed']+attempt) % 2**32
        splitter = (StratifiedGroupKFold(n, shuffle=True, random_state=seed) if groups is not None
                    else StratifiedKFold(n, shuffle=True, random_state=seed))
        folds = list(splitter.split(data.X,data.y,groups))
        if any(set(data.y[train]) != set(labels) or set(data.y[validation]) != set(labels)
               for train,validation in folds):
            continue
        if groups is not None and any(set(groups[train]) & set(groups[validation]) for train,validation in folds):
            raise ValueError('发现同组跨折，已停止寻优')
        return groups, folds, support, seed
    raise ValueError('分组交叉验证未能使每折覆盖所有类别，请减少折数或修改随机种子')


def evaluate(config, data, folds, opts, progress):
    from sklearn.cross_decomposition import PLSRegression
    from sklearn.metrics import accuracy_score, f1_score

    labels = np.array(sorted(config.classes))
    total = len(opts['preparations'])*len(opts['components'])
    rows = []
    for prep in opts['preparations']:
        transformed = []
        prep_error = None
        try:
            candidate = ExperimentConfig.model_validate({**config.model_dump(), 'preprocessing':prep['steps']})
            for train, validation in folds:
                progress(candidate=len(rows)+1, total=total, component=opts['components'][0],
                         fold=len(transformed)+1, folds=len(folds))
                pipe = SpectralPipeline(candidate.preprocessing)
                X = pipe.fit_transform(data.X[train])
                V = pipe.transform(data.X[validation])
                rank = np.linalg.matrix_rank(X-X.mean(axis=0))
                transformed.append((X, V, data.y[train], data.y[validation], rank))
        except (ValueError, DataError, np.linalg.LinAlgError) as error:
            if isinstance(error, DataError) and error.code == 'STUDY_CANCELLED':
                raise
            prep_error = '预处理无法在全部折计算'
        for components in opts['components']:
            row = dict(id=len(rows)+1, preprocessing=prep['steps'], name=prep['name'], n_components=components)
            rows.append(row)
            if prep_error or any(components > fold[-1] for fold in transformed):
                row['error'] = prep_error or '潜变量超出至少一折的训练特征秩'
                continue
            params = config.model.model_dump()
            params['n_components'] = components
            scores = []
            for index,(X,V,y,v,_) in enumerate(transformed,1):
                progress(candidate=row['id'],total=total,component=components,fold=index,folds=len(folds))
                try:
                    model = PLSRegression(**params)
                    model.fit(X,(y[:,None]==labels).astype(float))
                    predictions = [model.predict(samples) for samples in (X,V)]
                    if not all(np.isfinite(values).all() for values in predictions):
                        raise ValueError('nonfinite prediction')
                    estimations = [labels[values.argmax(axis=1)] for values in predictions]
                except (ValueError,FloatingPointError,np.linalg.LinAlgError):
                    row['error'] = f'第 {index} 折的 PLS-DA 拟合或预测无效'
                    break
                scores.append([f1_score(y,estimations[0],labels=labels,average='macro',zero_division=0),
                               accuracy_score(y,estimations[0]),
                               f1_score(v,estimations[1],labels=labels,average='macro',zero_division=0),
                               accuracy_score(v,estimations[1])])
            if 'error' in row:
                continue
            means, stds = np.mean(scores,axis=0), np.std(scores,axis=0,ddof=1)
            row.update(train_f1=float(means[0]), train_accuracy=float(means[1]), cv_f1=float(means[2]),
                       cv_accuracy=float(means[3]), cv_f1_sd=float(stds[2]), cv_accuracy_sd=float(stds[3]))
    valid = [row for row in rows if 'cv_f1' in row]
    if not valid:
        raise ValueError('没有能在全部折评测的候选，请调整范围')
    simplicity = lambda row: (row['n_components'],len(row['preprocessing']),-row['cv_f1'],row['id'])
    ranked = sorted(valid,key=lambda row:(-row['cv_f1'],*simplicity(row)))
    best = ranked[0]
    threshold = best['cv_f1'] - best['cv_f1_sd']/np.sqrt(len(folds))
    recommended = min((row for row in valid if row['cv_f1'] >= threshold),key=simplicity)
    upper = opts['components'][-1]
    return dict(candidates=ranked+[row for row in rows if 'error' in row],best=best['id'],
                recommended=recommended['id'],one_se_threshold=float(threshold),component_upper=upper,
                component_upper_reached=best['n_components']==upper and upper<min(64,len(config.wavelengths_nm)))


class StudyService:
    def __init__(self, dialogue):
        self.dialogue, self.service = dialogue, dialogue.service
        self.root = self.service.root / 'studies'
        self.active = {}
        self.lock = RLock()
        with connect_database(dialogue.database) as db:
            db.execute('CREATE TABLE IF NOT EXISTS study_draft (session_id TEXT PRIMARY KEY REFERENCES agent_session(id), document TEXT NOT NULL)')

    def folder(self, identifier):
        self.service.folder(identifier)  # canonical UUID
        path = self.root / identifier
        if path.resolve().parent != self.root.resolve():
            raise DataError('STUDY_NOT_FOUND', '寻优记录不存在')
        return path

    def prepare(self, owner, turn, text, *, structured=False):
        with connect_database(self.dialogue.database) as db:
            previous = db.execute('SELECT document FROM study_draft WHERE session_id=?',(owner,)).fetchone()
        previous = json.loads(previous[0]) if previous else None
        changing = bool(EDIT.match(text))
        if EXTRACTION_OPTIONS.search(text):
            raise ValueError('采样步长、每类上限和抽样种子需要在训练方案中修改，寻优会继承这些设置。'
                             '如指波长网格步长，也请在训练方案中修改。本轮未应用改动。'
                             '修改后可发“调整寻优，折数 2”或重新发起寻优。')
        if changing:
            if not previous:
                raise ValueError('当前还没有可调整的寻优方案。请先发起寻优，例如“发起寻优，折数 2，潜变量 2-8”。')
            text = previous['text'] + '\n' + text
        model = re.search(r'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b',text)
        record = self.dialogue._read(owner)
        if model or not record or not record['document'] or record['run_status'] != 'idle':
            self.dialogue.resume_training(owner, archive_id=model[0] if model else None, study_only=True)
        record = self.dialogue._read(owner)
        rows = []
        config = self.dialogue._config(record, training_only=True, train_manifest_rows=rows)
        hint = grid_hint(config.wavelengths_nm)
        grouping, fold_note = None, ''
        try:
            settings = options(text, config.wavelengths_nm, record['document'].get('preprocessing', []))
            grouping = group_kind(config, settings)
            support = study_group_support(config, rows, grouping)
            if not FOLDS.search(text) and support and min(support.values()) == 2:
                settings['folds'] = 2
                limited = '、'.join(name for name,count in support.items() if count==2)
                fold_note = f'未指定折数，{limited} 仅有 2 个训练组，采用 2 折。'
            check_group_support(support,settings['folds'])
        except ValueError as error:
            notes = [hint] if hint else []
            if grouping == 'image':
                notes.append('缺少完整实物编号，按原图探索性分组，同图不跨折，实物独立性未知。')
            raise ValueError('\n'.join([str(error),*notes])) from error
        if changing and previous['revision']==record['revision'] and previous['options']==settings:
            raise ValueError('没有识别到有效变化，未重发寻优方案。可用“调整寻优”或“修改寻优”，'
                             '并写明要改的折数、潜变量、SG 窗口或预处理候选。')
        identifier = str(uuid4())
        document = dict(id=identifier, turn=turn, revision=record['revision'], snapshot=record,
                        config=config.model_dump(mode='json', exclude={'test'}), options=settings, grouping=grouping,
                        text=text, expected_hashes={r[key]:r[key+'_sha256'] for r in rows
                                                    for key in ('hdr','img','annotation') if r.get(key+'_sha256')})
        with connect_database(self.dialogue.database) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO study_draft VALUES (?,?)',(owner,json.dumps(document,ensure_ascii=False)))
            self.dialogue.set_confirmation(db,owner,'study',record['revision'],identifier)
        base = '基于归档实验 '+record['base_experiment_id']+'。\n' if record['base_experiment_id'] else ''
        candidates = '、'.join(item['name'] for item in settings['preparations'])
        windows = list(dict.fromkeys(step['window'] for item in settings['preparations'] for step in item['steps'] if step['op']=='savgol'))
        grouping_text = {'sample':'按实物分组','batch':'按批次分组','npz_group':f'按 NPZ 字段 {getattr(config.train,"groups_key",None)} 分组',
                         'image':'按原图分组（探索性，同图不跨折，已知同一实物保持同组，其余实物独立性未知）',
                         'exploratory':'缺少实物／批次分组，仅能作探索性分层 CV，同源邻域可能泄漏'}[grouping]
        confirmation = '确认探索性寻优' if grouping in ('image','exploratory') else '确认寻优'
        notice = '所有候选仅使用训练集。在每折训练侧拟合；留出测试集用于之后单独确认的正式实验。'
        sampling = sampling_text(config.train)
        axis_notice = hint+'\n' if hint else ''
        overview = f'{settings["folds"]} 折 · {grouping_text} · {len(settings["preparations"])*len(settings["components"])} 个候选'
        reply = (f'{base}寻优方案 · {settings["folds"]} 折，{grouping_text}，分折种子 {settings["seed"]}。\n'
                + (fold_note+'\n' if fold_note else '') + f'预处理候选 {candidates}。'+ ('SG 窗口 '+'、'.join(map(str,windows))+'，二阶多项式。' if windows else '') +
                ('包含中心化。' if '不中心化' not in text else '') +
                f'潜变量 {settings["components"][0]} 至 {settings["components"][-1]}。\n{sampling}。\n{axis_notice}{notice}\n'
                f'可说“调整寻优，折数 3，潜变量 2-8”或提供“SG窗口：9、15；预处理候选：原谱、SG1；归一化候选：无、L2”。审阅后回复“{confirmation}”。')

        return (reply, {'study_preview_id':identifier,'study_confirm':confirmation,'study_overview':overview,'study_fold_note':fold_note,
                         'study_sampling':sampling}) if structured else reply

    def submit(self, owner, turn, content):
        with self.lock:
            if not self.service.lock.acquire(blocking=False):
                raise DataError('EXPERIMENT_BUSY', '已有训练、推理或寻优正在运行')
            try:
                with connect_database(self.dialogue.database) as db:
                    db.execute('BEGIN IMMEDIATE')
                    draft = db.execute('SELECT document FROM study_draft WHERE session_id=?',(owner,)).fetchone()
                    draft = json.loads(draft[0]) if draft else None
                    target = self.dialogue.confirmation(owner,db)
                    current = self.dialogue._read(owner, db)
                    if (not draft or not current or target != ('study',draft['revision'],draft['id'])
                            or draft['revision'] != current['revision'] or draft['turn']==turn):
                        raise DataError('STUDY_CONFIRMATION_REQUIRED','请先审阅当前寻优方案')
                    if draft['grouping'] in ('image','exploratory') and not content.startswith('确认探索性'):
                        raise DataError('STUDY_CONFIRMATION_REQUIRED','此方案使用探索性分组或分层，请单独回复“确认探索性寻优”')
                    identifier = draft['id']
                    folder = self.folder(identifier)
                    guard.mkdir(folder,parents=True)
                    state = dict(study_id=identifier,session_id=owner,status='queued',phase='checking',
                                 started_at=time(),finished_at=None)
                    write_json(folder/'plan.json',draft)
                    state['plan_sha256'] = sha256(folder/'plan.json')
                    write_json(folder/'status.json',state)
                    self.dialogue.clear_confirmation(db,owner,'study')
                event = Event()
                self.active[identifier] = (owner,event)
                try:
                    Thread(target=self.run,args=(draft,state,event),daemon=True).start()
                except Exception:
                    self.active.pop(identifier,None)
                    raise
            except Exception:
                self.service.lock.release()
                raise
        return state

    def run(self, draft, state, cancelled):
        identifier = state['study_id']
        folder = self.folder(identifier)
        last_write = None

        def progress(**changes):
            nonlocal last_write
            if cancelled.is_set():
                raise DataError('STUDY_CANCELLED','寻优已在安全边界取消')
            if changes:
                phase_changed = changes.get('phase',state['phase']) != state['phase']
                state.update(status='running',**changes)
                now = monotonic()
                if phase_changed or last_write is None or now-last_write >= .25:
                    write_json(folder/'status.json',state)
                    last_write = now

        try:
            progress(phase='preparing')
            raw = deepcopy(draft['config'])
            raw['test'] = deepcopy(raw['train'])
            raw['test'].pop('max_per_class',None)
            config = ExperimentConfig.model_validate(raw)
            opts = draft['options']
            with threadpool_limits(limits=2):
                data = load_input(config.train,config.wavelengths_nm,config.classes,progress=progress)
                for path, expected in draft.get('expected_hashes',{}).items():
                    if data.sources[path]['sha256'] != expected:
                        raise ValueError('训练来源内容与清单不一致，请重新核对配对或划分。')
                groups, folds, support, seed = make_folds(data,draft['grouping'],opts,config)
                save_arrays(folder/'training_cache.npz', X=data.X,y=data.y,
                            groups=groups if groups is not None else np.array([],dtype=str),
                            fold_assignment=np.sum([np.isin(np.arange(len(data.y)),v)*i
                                                    for i,(_,v) in enumerate(folds,1)],axis=0))
                write_json(folder/'sources.json',data.sources)
                progress(phase='evaluating')
                result = evaluate(config,data,folds,opts,progress)
                check_sources(data.sources,progress)
            result.update(study_id=identifier,folds=opts['folds'],grouping=draft['grouping'],
                          group_count=len(set(groups)) if groups is not None else None,
                          samples=len(data.y),evaluation_unit=data.unit,class_group_support=support,
                          sampling=data.sampling,seed=seed,requested_seed=opts['seed'])
            write_json(folder/'result.json',result)
            state.update(status='succeeded',phase='reporting',result_sha256=sha256(folder/'result.json'))
        except (DataError,ValueError,OSError,KeyError) as error:
            code = error.code if isinstance(error,DataError) else 'STUDY_FAILED'
            state.update(status='cancelled' if code=='STUDY_CANCELLED' else 'failed',
                         error=error.payload.detail if isinstance(error,DataError) else str(error))
        except Exception:
            state.update(status='failed',error='寻优计算失败，请核验训练输入')
        finally:
            try:
                state['finished_at'] = time()
                write_json(folder/'status.json',state)
            finally:
                with self.lock:
                    self.active.pop(identifier,None)
                    self.service.lock.release()

    def status(self, owner, identifier):
        try:
            state = read_json(self.folder(identifier)/'status.json')
        except FileNotFoundError:
            state = None
        if not state or state['session_id'] != owner:
            error = DataError('STUDY_NOT_FOUND','当前会话没有该寻优任务')
            error.status_code = 404
            raise error
        return state

    def has_active(self, owner):
        with self.lock:
            return any(session_id == owner for session_id, _ in self.active.values())

    def cancel(self, owner, identifier):
        state = self.status(owner,identifier)
        with self.lock:
            active = self.active.get(identifier)
            if active and active[0]==owner:
                active[1].set()
        return state

    def recover(self):
        for path in self.root.glob('*/status.json'):
            try:
                state = read_json(path)
                if state['status'] not in TERMINAL:
                    state.update(status='interrupted',finished_at=time(),error='引擎退出时寻优尚未完成')
                    write_json(path,state)
            except (OSError,ValueError,KeyError):
                continue

    def latest(self, owner):
        states = []
        for path in self.root.glob('*/status.json'):
            try:
                states.append(self.status(owner,path.parent.name))
            except (DataError,OSError,ValueError):
                continue
        return max(states,key=lambda state:state['started_at'],default=None)

    def result(self, owner, identifier):
        state = self.status(owner,identifier)
        if state['status']!='succeeded':
            raise DataError('STUDY_NOT_READY','寻优尚无完整结果')
        path = self.folder(identifier)/'result.json'
        if state.get('result_sha256') and sha256(path) != state['result_sha256']:
            raise DataError('STUDY_RESULT_CHANGED','归档的寻优结果校验失败')
        return read_json(path)

    def adopt(self, owner, identifier, choice):
        result = self.result(owner,identifier)
        candidate = next((row for row in result['candidates'] if row['id']==choice and 'cv_f1' in row),None)
        if not candidate:
            raise DataError('STUDY_CHOICE_INVALID','请选择有效的已评测候选')
        if self.dialogue.tasks.active(owner):
            raise DataError('EXPERIMENT_BUSY','当前训练尚未结束')
        folder = self.folder(identifier)
        check_sources(read_json(folder/'sources.json'))
        state = self.status(owner,identifier)
        if state.get('plan_sha256') and sha256(folder/'plan.json') != state['plan_sha256']:
            raise DataError('STUDY_RESULT_CHANGED','归档的寻优方案校验失败')
        plan = read_json(folder/'plan.json')
        snapshot = plan['snapshot']
        current_train = self.dialogue._config(snapshot,training_only=True).train.model_dump(mode='json')
        if current_train != plan['config']['train']:
            raise DataError('STUDY_SOURCE_CHANGED','训练目录成员已变化，请重新寻优')
        document = deepcopy(snapshot['document'])
        document.update(preprocessing=candidate['preprocessing'],model={**plan['config']['model'],'n_components':candidate['n_components']})
        document['notes'] = (document.get('notes','') + f'\n参数来自训练集内寻优 {identifier}，候选 {choice}。').strip()
        with connect_database(self.dialogue.database) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO experiment_dialogue(session_id) VALUES (?)',(owner,))
            db.execute("UPDATE experiment_dialogue SET document_json=?,sources_json=?,revision=revision+1,active=1,"
                       "reviewed_revision=NULL,review_turn=NULL,review_sources_json=NULL,run_status='idle',"
                       "experiment_id=NULL,base_experiment_id=?,previous_document_json=? WHERE session_id=?",
                       (json.dumps(document,ensure_ascii=False),json.dumps(snapshot['sources'],ensure_ascii=False),
                        snapshot['base_experiment_id'],json.dumps(plan['snapshot']['document'],ensure_ascii=False),owner))
            self.dialogue.clear_confirmation(db,owner)
