"""Plan train/test membership on labeled images before any spectral sampling."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import random
import re
from uuid import uuid4

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix

from backend.database import connect_database
from spectrumagent.storage import guard
from .pairing import inventory
from .service import write_json

HEADER = re.compile(r'原始数据|原图|原始光谱|标注|分组表')
PAGE = re.compile(r'(?:查看)?划分明细(?:\s*第?\s*(\d{1,6})\s*页?)?')
RATIO = re.compile(r'测试(?:集)?(?:占比|比例|占|留出)?\s*(?:改为|改成|设为|为)?\s*(\d+(?:\.\d+)?)\s*[%％]')
SEED = re.compile(r'(?:随机)?种子\s*[=:：为]?\s*(\d+)')
HOLD = re.compile(r'(?:指定|留出)测试(?:组|批次)\s*[:：]\s*([^；;。\n]+)')
IMAGE = '每张图是一件独立实物'
INDIVIDUAL = re.compile(r'(?:确认)?每(?:张|幅)(?:原)?图(?:像)?(?:都是|对应|是|就是)(?:一件|一个)?(?:不同的?|独立的?)?(?:实物|样品)[。！!\s]*')
CONFIRM = '确认保存划分'
HELP = ('请提供原图目录和标注目录，例如：原图在“D:\\数据”，标注在“E:\\标注”，帮我划分训练和测试。'
        'JSON 可提供 sample_id（实物编号）、batch（采集批次），也可以另外提供分组表 CSV。')


def requested(text, paths):
    semantic = paths.sub(' ', text).strip(' 。！!')
    if (paths.search(text) and re.search('划分|分出训练集|分成训练集|识别新.*样品|新批次', semantic)
            and '标注' in semantic and re.search('原图|原始数据|原始光谱',semantic)):
        # Explicit already-assigned input roles still belong to the existing pairing workflow.
        return not re.search(r'(?:训练|测试)(?:集)?(?:的)?(?:原图|标注|数据)(?:目录)?', semantic)
    return bool(semantic in (CONFIRM, '查看划分方案', IMAGE, '按实物划分', '按批次划分', '自动选择测试组')
                or INDIVIDUAL.fullmatch(semantic) or PAGE.fullmatch(semantic)
                or semantic.startswith(('划分预览','调整划分','提供分组表','指定测试组','指定测试批次','把测试比例改为','测试占比改为')))


def inputs(text, paths):
    refs = list(paths.finditer(text))
    masked = paths.sub(lambda m: ' ' * len(m[0]), text)
    fields = defaultdict(list)
    matches = list(HEADER.finditer(masked))
    # Associate each path with its nearest preceding field name.
    for ref in refs:
        preceding = [m for m in matches if m.end() <= ref.start()]
        if not preceding:
            raise ValueError(HELP)
        field = preceding[-1][0]
        key = field if field in ('标注','分组表') else '原图'
        fields[key].append(str(Path(ref['quoted'] or ref['bare']).resolve()))
    return fields


def scan(fields):
    roots = {}
    for key in ('原图','标注'):
        dirs = [Path(p) for p in fields.get(key, [])]
        if not dirs or any(not p.is_dir() for p in dirs):
            raise ValueError(HELP)
        roots['待划分'+key] = dirs
    result = inventory(roots, roles=('待划分',))
    if result['issues']:
        raise ValueError(f"配对有 {len(result['issues'])} 条异常，请处理后重新提交目录。\n" + '\n'.join(result['issues'][:8]))
    if not result['pairs']:
        raise ValueError('没有可划分的已标注图像')
    rows = sorted(result['pairs'], key=lambda r:r['hdr'])
    mapping = fields.get('分组表', [])
    if mapping:
        if len(mapping) != 1:
            raise ValueError('请指定一份包含 source、sample_id 或 batch 的分组表')
        by_hdr = {Path(r['hdr']):r for r in rows}
        seen = set()
        with Path(mapping[0]).open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            columns = set(reader.fieldnames or ())
            if 'source' not in columns or not columns.intersection({'sample_id','batch'}):
                raise ValueError('分组表需要 source（HDR绝对路径）和 sample_id 或 batch 列')
            for item in reader:
                path = Path(item['source'] or '')
                if not path.is_absolute() or path not in by_hdr or path in seen:
                    raise ValueError(f'分组表包含重复或未知来源：{path}')
                seen.add(path)
                row = by_hdr[path]
                for key in ('sample_id','batch'):
                    value = (item.get(key) or '').strip()
                    if value and row[key] not in (None,value):
                        raise ValueError(f'{path.name} 的 {key} 与标注记录冲突')
                    if value:
                        row[key] = value
    return rows, len(result['unused'])


def physical_test(groups, classes, ratio, seed):
    # Binary group membership, missing-test indicators, absolute deviations.
    # First maximize test class coverage while retaining every training class.
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    n, k = len(keys), len(classes)
    size = n + 2*k + 1
    objective = np.zeros(size)
    objective[n:n+k] = k + 2
    objective[-1] = 1/n
    matrix, low, high = [], [], []
    def constraint(vector, lower, upper):
        matrix.append(vector)
        low.append(lower)
        high.append(upper)
    count = np.zeros(size)
    count[:n] = 1
    constraint(count.copy(), 1, n-1)
    def deviation(vector, target, pos):
        a = vector.copy()
        a[pos] = -1
        constraint(a, -np.inf, target)
        b = -vector
        b[pos] = -1
        constraint(b, -np.inf, -target)
    deviation(count, n*ratio, -1)
    for i, label in enumerate(classes):
        counts = np.zeros(size)
        counts[:n] = [sum(label in row['labels'] for row in groups[g]) for g in keys]
        total = counts.sum()
        constraint(counts.copy(), 0, total-1)
        coverage = counts.copy()
        coverage[n+i] = 1
        constraint(coverage, 1, np.inf)
        deviation(counts, total*ratio, n+k+i)
        objective[n+k+i] = 1/total
    binary = n+k
    fit = milp(objective, integrality=[1]*binary+[0]*(size-binary),
               bounds=Bounds(np.zeros(size), [1]*binary+[np.inf]*(size-binary)),
               constraints=LinearConstraint(csr_matrix(matrix),low,high), options={'time_limit':10.})
    if fit.status == 2:
        return set()
    if not fit.success or fit.x is None:
        raise ValueError('本次计算预算内未确定分组方案。请指定测试组或按批次预览。')
    return {key for key,val in zip(keys,fit.x[:n]) if val > .5}


def propose(state):
    rows,mode = state['rows'],state['mode']
    groups = defaultdict(list)
    for row in rows:
        sample = row['sample_id'] or (row['hdr'] if state['individual'] else None)
        group = row['batch'] if mode == 'batch' else sample
        if group is None:
            return [], ('请提供分组表 CSV（source、batch），标明每张图的采集批次。' if mode == 'batch' else
                        f'有图像缺少实物编号。若每张图确属不同实物，回复“{IMAGE}”；有重复拍摄请回复“提供分组表”并附 CSV 路径（source、sample_id）。')
        groups[group].append(row)
    if len(groups) < 2:
        return [], '只有一个分组，无法同时划出训练和测试。请补充分组或样品。'
    classes = sorted({label for row in rows for label in row['labels']})
    ratio = state['ratio']/100
    def evaluate(test):
        train_labels, test_labels, sample_sides = set(),set(),defaultdict(set)
        for group, members in groups.items():
            for row in members:
                side = group in test
                (test_labels if side else train_labels).update(row['labels'])
                if row['sample_id']:
                    sample_sides[row['sample_id']].add(side)
        if train_labels != set(classes) or any(len(s)>1 for s in sample_sides.values()):
            return None
        return len(classes)-len(test_labels), abs(sum(len(groups[g]) for g in test)/len(rows)-ratio)
    if state['hold']:
        test = set(state['hold'])
        if not test < groups.keys():
            return [], '指定的组不在清单内或占用了全部分组。请检查名称。'
    elif mode == 'batch':
        keys = sorted(groups)
        random.Random(state['seed']).shuffle(keys)
        choices = [(evaluate({g}),g) for g in keys]
        viable = [(score,g) for score,g in choices if score is not None]
        test = {min(viable,key=lambda x:x[0])[1]} if viable else set()
    else:
        test = physical_test(groups,classes,ratio,state['seed'])
    if not test or evaluate(test) is None:
        return [], '当前分组无法生成满足条件的方案：训练须覆盖所有类别，已知同一实物不能跨两侧。可调整分组或补充数据。'
    return [dict(row,group=g,split='测试' if g in test else '训练') for g in sorted(groups) for row in groups[g]], ''


def summary(state, plan, reason):
    rows = state['rows']
    group_key = '采集批次' if state['mode']=='batch' else '实物'
    lines = [f"已标注 {len(rows)} 幅，未被标注引用 {state['unused']} 幅。按{group_key}分组，目标测试比例 {state['ratio']:g}%，随机种子 {state['seed']}。"]
    for label in sorted({label for r in rows for label in r['labels']}):
        items = [r for r in rows if label in r['labels']]
        known = {r['sample_id'] or (r['hdr'] if state['individual'] else None) for r in items}
        count = len(known-{None})
        support = f'已知 {count} 件实物' + ('（另有图像缺编号）' if None in known else '')
        warning = '；仅一件实物，无法对该类独立实物作双侧评价' if known and None not in known and count==1 else ''
        train = sum(p['split']=='训练' and label in p['labels'] for p in plan)
        split = f'；训练 {train} 图、测试 {len(items)-train} 图' if plan else ''
        if plan and None not in known:
            sizes = [len({p['sample_id'] or p['hdr'] for p in plan if p['split']==side and label in p['labels']})
                     for side in ('训练','测试')]
            split += f'（训练 {sizes[0]} 件、测试 {sizes[1]} 件）'
        if plan and train == len(items):
            split += '（测试未覆盖）'
        lines.append(f'{label}：{len(items)} 图，{sum(r["region_counts"][label] for r in items)} 个区域，{support}{split}{warning}')
    if not plan:
        return '\n'.join(lines+[reason]), 'needs_input'
    counts = Counter(p['split'] for p in plan)
    groups = {role:{p['group'] for p in plan if p['split']==role} for role in ('训练','测试')}
    lines.append(f"训练 {counts['训练']} 图/{len(groups['训练'])} 组，测试 {counts['测试']} 图/{len(groups['测试'])} 组。分组交叉 0。")
    if state['hold'] and state['mode']=='sample':
        lines.append('指定的测试实物：'+'、'.join(sorted(groups['测试'])))
    if state['mode']=='batch':
        lines.append('留出批次：'+'、'.join(sorted(groups['测试'])))
        if any(not r['sample_id'] for r in rows) and not state['individual']:
            lines.append('部分实物编号未知，同一实物是否在不同批次重复拍摄尚无法完全核验。')
    return '\n'.join(lines+['可查看“划分明细 第1页”，或回复“调整划分，测试占30%”“指定测试组：组名”。核对后回复“确认保存划分”。']), 'ready'


def adjust(state, text):
    previous_mode = state['mode']
    if any(word in text for word in ('按批次','新批次','跨批次','换一批','指定测试批次')):
        state['mode'] = 'batch'
    if '按实物' in text or '新实物' in text or '新塑料样品' in text:
        state['mode'] = 'sample'
    if state['mode'] != previous_mode or '自动选择测试组' in text:
        state['hold'] = []
    if INDIVIDUAL.fullmatch(text) or re.search(r'[，,；;。\s]'+INDIVIDUAL.pattern, text):
        known = [r['sample_id'] for r in state['rows'] if r['sample_id']]
        if len(set(known)) != len(known):
            raise ValueError('已有相同实物编号关联多幅图，不能声明每图独立。请提供完整分组表。')
        state['individual'] = True
    ratio = RATIO.search(text)
    if ratio:
        value = float(ratio[1])
        if not 0 < value < 100:
            raise ValueError('测试比例须在 0% 和 100% 之间')
        state['ratio'] = value
    seed = SEED.search(text)
    if seed:
        state['seed'] = int(seed[1])
    hold = HOLD.search(text)
    if hold:
        state['hold'] = [g.strip(' "“”') for g in re.split('[、,，]',hold[1]) if g.strip()]
    if text.startswith('调整划分') and not (ratio or seed or hold or previous_mode != state['mode']):
        raise ValueError('可调整测试比例、随机种子、按实物或批次分组，或指定测试组。')


def answer(dialogue, session, content, paths):
    text = content.strip(' 。！!')
    with connect_database(dialogue.database) as db:
        record = db.execute('SELECT document FROM experiment_group_split WHERE session_id=?',(session,)).fetchone()
    old = record[0] if record else None
    try:
        return respond(dialogue, session, text, paths, old)
    except (ValueError, OSError) as error:
        if old and text not in (CONFIRM,'查看划分方案') and not PAGE.fullmatch(text):
            state = json.loads(old)
            state['review_again'] = True
            with connect_database(dialogue.database) as db:
                db.execute('UPDATE experiment_group_split SET document=? WHERE session_id=? AND document=?',
                           (json.dumps(state,ensure_ascii=False),session,old))
            raise ValueError(f'{error}\n本次修改未应用；如需使用先前方案，请回复“查看划分方案”重新审阅。') from error
        raise


def respond(dialogue, session, text, paths, old):
    state = json.loads(old) if old else None
    fields = inputs(text, paths) if paths.search(text) and not HOLD.search(text) else {}
    if fields and ('原图' in fields or '标注' in fields):
        state = dict(fields=fields, mode='sample', individual=False, ratio=20.,seed=42,hold=[])
    elif not state:
        raise ValueError(HELP)
    page = PAGE.fullmatch(text)
    if page:
        rows = state.get('plan') or state['rows']
        number = int(page[1] or 1)
        pages = max(1,(len(rows)+9)//10)
        if not 1 <= number <= pages:
            raise ValueError(f'有效页码为 1 至 {pages}')
        lines = [f'第 {number}/{pages} 页']
        for r in rows[10*(number-1):10*number]:
            lines.append(f"{r.get('split','待划分')} · {r.get('group') or r.get('sample_id') or '实物未知'} · "
                         f"{'、'.join(r['labels'])}\n{r['hdr']}\n↳ {r['annotation']}")
        return '\n'.join(lines), 'done'
    if text == '查看划分方案':
        if state.pop('review_again',False):
            with connect_database(dialogue.database) as db:
                if not db.execute('UPDATE experiment_group_split SET document=? WHERE session_id=? AND document=?',
                                  (json.dumps(state,ensure_ascii=False),session,old)).rowcount:
                    raise ValueError('划分方案已更新，请重新查看')
        return summary(state,state['plan'],state['reason'])
    if text == CONFIRM:
        if state.get('review_again'):
            raise ValueError('上次修改未应用，请回复“查看划分方案”后再确认')
        if not state.get('plan'):
            raise ValueError('当前没有可保存的划分。请先补充分组信息并查看预览。')
        dest = dialogue.service.paths.exports/'split-plans'/(state['id']+'.json')
        if state.get('saved') and dest.is_file():
            return f'该版划分已保存：{dest}', 'done'
        fresh,unused = scan(state['fields'])
        if fresh != state['rows'] or unused != state['unused']:
            raise ValueError('数据、分组或标注自预览后已变化，请重新提供目录生成预览。')
        # Serialize final publication against concurrent edits to the same session.
        with connect_database(dialogue.database) as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT document FROM experiment_group_split WHERE session_id=?',(session,)).fetchone()
            if not current or current[0] != old:
                raise ValueError('预览已更新，请查看当前划分方案后再确认')
            guard.mkdir(dest.parent,parents=True,exist_ok=True)
            write_json(dest,dict(schema_version=1,split_id=state['id'],group_by=state['mode'],
                one_image_one_sample=state['individual'],seed=state['seed'],target_test_percent=state['ratio'],
                held_out_override=state['hold'],sources=state['fields'],rows=state['plan']))
            state['saved'] = True
            db.execute('UPDATE experiment_group_split SET document=? WHERE session_id=?',
                       (json.dumps(state,ensure_ascii=False),session))
        return f'已保存逐图划分清单：{dest}\n含各图用途、分组和输入来源，可供后续训练复用。', 'done'
    if fields:
        state['fields'].update(fields)
        state['rows'],state['unused'] = scan(state['fields'])
    elif text.startswith(('提供分组表','划分预览')):
        raise ValueError(HELP)
    adjust(state,paths.sub(' ',text) if fields else text)
    plan,reason = propose(state)
    state.update(id=str(uuid4()),plan=plan,reason=reason,saved=False,review_again=False)
    with connect_database(dialogue.database) as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT document FROM experiment_group_split WHERE session_id=?',(session,)).fetchone()
        if (current[0] if current else None) != old:
            raise ValueError('同时收到了另一份修改，请查看当前划分方案后重试')
        db.execute('INSERT INTO experiment_group_split VALUES (?,?) ON CONFLICT(session_id) DO UPDATE SET document=excluded.document',
                   (session,json.dumps(state,ensure_ascii=False)))
    return summary(state,plan,reason)
