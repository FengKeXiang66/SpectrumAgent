"""Session-owned dataset intake. Local paths never enter model task context.

The entry point precedes model routing; choice cards and typed answers therefore
share the same state transitions, including after a session is restored.
"""
from collections import defaultdict
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import numpy as np

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.api.registry import candidates, read_header
from spectrumagent.annotation.labels import LabelStore, now
from spectrumagent.annotation.raster import encode_rle
from spectrumagent.experiments.conversation import PATHS
from spectrumagent.experiments.inputs import roi_maps, sha256
from spectrumagent.experiments.pairing import resolve_annotation_header


COMMAND = re.compile(r'^(选择导入方式|检查同目录标注|使用已配对标注|调整标注路径|进入预处理|配置预处理与训练|进入人工标注|查看导入异常|取消数据导入)\s+([0-9a-f-]{36})(?:\s+(未标注|已有标注))?[。！!\s]*$')
UNLABELED = re.compile(r'未标注|尚未标注|没有标注|不带标注|不含标注|无标注|没有标签|不带标签')
LABELED = re.compile(r'已有标注|带有标注|带标注|有标注|标注好|已标注|带标签|有标签')
VIEW = re.compile(r'(?:请|帮我)?(?:查看|列出|显示)(?:全部|所有)?(?:已导入|已登记)(?:的)?(?:数据|数据集|样品)[。！!\s]*$')
IMPORT_REQUEST = re.compile(r'^(?:(?:请你|请|帮我|麻烦|我想|我要|需要|希望|现在)\s*)*(?:导入|接入|重新导入|开始导入)')
LABEL_COMMAND = re.compile(r'^创建导入标签\s+([0-9a-f-]{36})\s+([\s\S]+)$')
LABEL_NAMES = re.compile(r'^(?:(?:请|帮我|我要|我想|需要)\s*)*(?:为(?:刚导入|本次导入|这批|当前)(?:的)?数据)?'
                         r'(?:创建|新建|建立|添加|增加|建)标签(?:[，,]\s*标签名称(?:为|是)?)?\s*[:：]?\s*([\s\S]*)$')


def snapshot(path):
    stat = Path(path).stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


class DatasetIntake:
    def __init__(self, registry, sessions):
        self.registry, self.sessions = registry, sessions
        self.database = registry.database

    def read(self, sid):
        with connect_database(self.database) as db:
            row = db.execute('SELECT document_json FROM dataset_intake WHERE session_id=?', (sid,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, sid, state):
        with connect_database(self.database) as db:
            db.execute('INSERT INTO dataset_intake VALUES (?,?) ON CONFLICT(session_id) DO UPDATE SET document_json=excluded.document_json',
                       (sid, json.dumps(state, ensure_ascii=False)))

    def route(self, machine, content):
        text = PATHS.sub(' ', content).strip(' ，,。！!？?\n')
        command = COMMAND.fullmatch(content.strip())
        paths = [str(Path(m['quoted'] or m['bare']).resolve()) for m in PATHS.finditer(content)]
        state = self.read(machine.session_id)
        from spectrumagent.experiments.workspace_training import OPEN
        dialogue = getattr(machine.tools, 'experiment_dialogue', None)
        current = dialogue._read(machine.session_id) if dialogue else None
        if text == OPEN:
            return self.generate(machine, content, '统一训练', state)
        if state and state['imported_ids'] and text in {'我已经对数据标注完毕', '标注完成', '我已标注完毕', '我已经标注完毕'}:
            return self.generate(machine, content, '标注完成', state)
        if (state and state['imported_ids'] and not (current and current['active'] and current['document'])
                and re.fullmatch(r'(?:接下来|下一步|然后)?(?:请|帮我)?(?:对(?:这批)?数据)?(?:进行|开始)?预处理', text)):
            return self.generate(machine, content, '统一训练', state)
        label_command = LABEL_COMMAND.fullmatch(content.strip())
        label_names = LABEL_NAMES.fullmatch(content.strip())
        if label_command:
            return self.generate(machine, content, 'create_labels', state,
                                 label_payload=label_command[2], expected_id=label_command[1])
        if label_names and not re.search(r'^(?:需要|怎么|如何|能否|是否|有什么|是什么意思)|[?？]$', label_names[1].strip()):
            if not state or state['stage'] not in {'imported', 'labels'}:
                # Labels can be prepared before importing images. Use a real
                # current project, and never guess when several are available.
                context = json.loads(machine.store.session(machine.session_id)['context_json'] or '{}')
                projects = LabelStore(self.database).projects()
                with connect_database(self.database) as db:
                    selected = db.execute('SELECT project_id FROM dataset_registry WHERE id=?', (context.get('selected_cube_id'),)).fetchone()
                project = selected[0] if selected else projects[0]['id'] if len(projects) == 1 else None
                if state and state['stage'] in {'review', 'need_annotations', 'need_images', 'choose_mode'}:
                    state['label_project_id'] = project
                else:
                    state = dict(id=str(uuid4()), stage='labels', mode=None, images=[], annotations=[], created_at=now(),
                        issues=[], pairs=[], imported_ids=[], ready_ids=[], label_project_id=project)
            names = [name.strip().strip('"“”\'‘’') for name in re.split(r'[、,，;；\r\n]+', label_names[1].strip().rstrip('。！!')) if name.strip()]
            return self.generate(machine, content, 'create_labels' if names else 'open_labels', state, label_payload=json.dumps(names))
        if VIEW.fullmatch(text) and not paths:
            return self.generate(machine, content, 'list', state)
        # Explicit training/test, Study, NPZ and inference requests keep their
        # established experiment routes. A generic path does not select those.
        explicit_experiment = bool(re.search(r'训练(?:集)?(?:原图|标注|数据)|测试(?:集)?(?:原图|标注|数据)|推理|寻优|划分|npz|导入(?:已有)?模型', text, re.I)
                                   or any(Path(path).suffix.lower() == '.npz' for path in paths))
        active = state and state['stage'] not in {'imported', 'cancelled', 'labels'}
        new_request = bool(IMPORT_REQUEST.search(text))
        discussion = bool(re.search(r'为什么|为何|如何|怎么|是否|能否|能不能|不要(?:再)?导入|先不导入', text))
        start = bool((new_request or paths and re.search(r'原图|ENVI|已有标注|已标注|导入|原数据|原始数据|数据目录|未标注', text, re.I))
                     and not explicit_experiment and not discussion)
        choice = ('unlabeled' if UNLABELED.search(text) else 'labeled' if LABELED.search(text) else None)
        if command:
            return self.generate(machine, content, command[1], state, command=command)
        if state and state['imported_ids'] and text in {'进入预处理', '开始预处理', '进入标注', '下一步进入标注',
                '配置预处理与训练', '进入人工标注', '开始人工标注', '下一步进入人工标注', '下一步：超像素人工标注'}:
            return self.generate(machine, content, '进入预处理' if '预处理' in text else '进入人工标注', state)
        if active and not new_request and not explicit_experiment and not discussion and (paths or choice or text in {'与原图同目录', '标注与原图同目录', '检查同目录标注', '取消数据导入'}):
            action = '检查同目录标注' if '同目录' in text else '取消数据导入' if text == '取消数据导入' else 'collect'
            return self.generate(machine, content, action, state, paths=paths, choice=choice)
        if start or (paths and not explicit_experiment and not text):
            # Supplying an annotation path to the active intake must not discard
            # the already supplied image directory.
            if active and '标注' in text and not choice:
                return self.generate(machine, content, 'collect', state, paths=paths)
            state = dict(id=str(uuid4()), stage='choose_mode', mode=None, images=[], annotations=[],
                         created_at=now(), issues=[], pairs=[], imported_ids=[], ready_ids=[])
            return self.generate(machine, content, 'start', state, paths=paths, choice=choice)
        return None

    def refresh_annotations(self, state):
        # A saved manual annotation is as usable as an imported ROI. Intake's
        # original ready_ids must not remain a snapshot of external imports.
        with connect_database(self.database) as db:
            ready = {row[0] for row in db.execute(
                'SELECT c.cube_id FROM annotation_confirmation_state c '
                'JOIN annotation_draft d ON d.cube_id=c.cube_id AND d.revision=c.draft_revision '
                'JOIN annotation_version v ON v.id=c.annotation_version_id WHERE v.labeled_pixels>0')}
        state['ready_ids'] = [cube for cube in state['imported_ids'] if cube in ready]

    @staticmethod
    def card(state):
        return {key: state[key] for key in ('id', 'stage', 'mode')} | {
            'image_names': [Path(path).name for path in state['images']],
            'annotation_names': [Path(path).name for path in state['annotations']],
            'image_count': len(state.get('headers', [])), 'paired_count': len(state['pairs']),
            'missing_count': len(state.get('unused', [])), 'issue_count': len(state['issues']),
            'classes': sorted({label for pair in state['pairs'] for label in pair['labels']}),
            'imported_count': len(state['imported_ids']), 'ready_count': len(state['ready_ids']),
            'labels': state.get('labels', []),
            'label_form_open': state.get('label_form_open', False),
            'label_draft': state.get('label_draft', []),
            'annotation_retry': state.get('annotation_retry', False),
            'pairs': [dict(image_name=Path(p['hdr']).name, annotation_name=Path(p['annotation']).name,
                           region_count=p['region_count'], labels=p['labels']) for p in state['pairs']],
        }

    def headers(self, paths):
        headers = set()
        for value in paths:
            root = Path(value)
            for path in candidates(root):
                if root.is_dir() and not path.is_relative_to(root):
                    continue
                # A LabelMe sidecar with a sibling IMG is not an ENVI JSON header.
                if path.suffix.lower() == '.json':
                    doc = json.loads(path.read_text('utf-8-sig'))
                    if 'shapes' in doc:
                        continue
                headers.add(path)
        if not headers:
            raise DataError('EMPTY_DIRECTORY', '指定位置没有可接入的 ENVI 数据头')
        return sorted(headers)

    def preview(self, state, check):
        headers = self.headers(state['images'])
        state['headers'] = list(map(str, headers))
        image_roots = [Path(p) if Path(p).is_dir() else Path(p).parent for p in state['images']]
        annotation_roots = [Path(p) if Path(p).is_dir() else Path(p).parent for p in state['annotations']]
        by_relative, by_name = defaultdict(set), defaultdict(set)
        for header in headers:
            by_name[header.name.casefold()].add(header)
            for root in image_roots:
                if header.is_relative_to(root):
                    by_relative[tuple(p.casefold() for p in header.relative_to(root).parts)].add(header)
        annotations = set()
        for value in state['annotations']:
            root = Path(value)
            if root.is_file() and root.suffix.lower() == '.json':
                annotations.add(root)
            elif root.is_dir():
                annotations.update(p.resolve() for p in root.rglob('*') if p.is_file()
                                   and p.suffix.lower() == '.json' and p.resolve().is_relative_to(root))
            else:
                raise DataError('ANNOTATION_PATH_INVALID', '标注路径须为 JSON 文件或目录')
        state.update(pairs=[], issues=[], unused=[])
        bound = defaultdict(list)
        references = defaultdict(list)
        roi_count = 0
        for annotation in sorted(annotations):
            check()
            try:
                annotation_hash = sha256(annotation, check)
                doc = json.loads(annotation.read_text('utf-8-sig'))
                if not isinstance(doc, dict) or 'shapes' not in doc:
                    continue
                roi_count += 1
                header, fallback = resolve_annotation_header(doc, annotation, annotation_roots, image_roots,
                                                      set(headers), by_relative, by_name)
                references[header].append(annotation)
                signature = doc.get('source_signature', {})
                if not isinstance(signature, dict):
                    raise ValueError('source_signature 须为对象')
                if fallback and 'source_signature' in doc and (not signature.get('hdr_sha256') or signature.get('img_bytes') is None):
                    raise ValueError('回退配对的来源签名需要 hdr_sha256 和 img_bytes')
                header_hash = sha256(header, check)
                dataset = read_header(header, raw=True)
                labels = sorted({shape['label'] for shape in doc['shapes']})
                if not labels or any(not isinstance(label, str) or not label.strip() for label in labels):
                    raise ValueError('标注缺少有效类别名称')
                regions, _ = roi_maps(annotation, dataset.shape[:2], dict(enumerate(labels, 1)), header_hash)
                if not np.any(regions > 0):
                    raise ValueError('标注没有覆盖有效像素')
                if not fallback and signature.get('img_path') and Path(signature['img_path']).resolve() != Path(dataset.data_path).resolve():
                    raise ValueError('数据文件路径与标注签名不一致')
                if signature.get('img_bytes') is not None:
                    size = signature['img_bytes']
                    if not (type(size) is int or isinstance(size, str) and size.isdecimal()) or int(size) != Path(dataset.data_path).stat().st_size:
                        raise ValueError('数据文件大小与标注签名不一致')
                if sha256(annotation, check) != annotation_hash or sha256(header, check) != header_hash:
                    raise ValueError('扫描期间来源发生变化，请重新检查')
                bound[header].append(dict(hdr=str(header), annotation=str(annotation), labels=labels, region_count=len(doc['shapes']),
                    annotation_sha256=annotation_hash, header_sha256=header_hash,
                    data_path=dataset.data_path, data_snapshot=snapshot(dataset.data_path)))
            except (DataError, OSError, ValueError, KeyError, TypeError) as error:
                detail = error.payload.detail if isinstance(error, DataError) else str(error)
                state['issues'].append(f'{annotation.name}：{detail}')
        for header, pairs in sorted(bound.items()):
            if len(references[header]) > 1:
                state['issues'].append(f'{header.name}：多份标注指向同一原图，未选择其中任何一份')
            else:
                state['pairs'].extend(pairs)
        matched = {p['hdr'] for p in state['pairs']}
        state['unused'] = [str(p) for p in headers if str(p) not in matched]
        if not annotations:
            state['issues'].append('指定位置没有 JSON 标注文件')
        elif not roi_count:
            state['issues'].append('未找到包含 shapes 的 ROI JSON 标注')
        state['stage'] = 'review'

    def import_images(self, state, check, persist):
        records = []
        # Labeled imports use the exact preview membership. Newly appearing
        # files require another preview rather than widening a reviewed batch.
        headers = list(map(Path, state['headers'])) if state['stage'] == 'review' else self.headers(state['images'])
        for header in headers:
            check()
            try:
                record = self.registry.import_path(str(header)).datasets[0]
            except (DataError, OSError, ValueError) as error:
                detail = error.payload.detail if isinstance(error, DataError) else str(error)
                state['issues'].append(f'{header.name}：登记失败，{detail}')
                continue
            cube = str(record.id)
            if cube not in state['imported_ids']:
                state['imported_ids'].append(cube)
            with connect_database(self.database) as db:
                confirmed = db.execute('SELECT 1 FROM annotation_confirmation_state c JOIN annotation_draft d ON d.cube_id=c.cube_id '
                                       'WHERE c.cube_id=? AND c.draft_revision=d.revision', (cube,)).fetchone()
            if confirmed and cube not in state['ready_ids']:
                state['ready_ids'].append(cube)
            persist()
            records.append(record)
        if not records:
            raise DataError('DATASET_IMPORT_FAILED', '没有成功登记的原图，请查看异常并调整原图位置')
        return records

    def remember(self, machine, records, round_id):
        from . import context as memory
        context = json.loads(machine.store.session(machine.session_id)['context_json'] or '{}')
        listing = {'dataset_count': len(records)}
        for index, record in enumerate(records, 1):
            listing.update({f'dataset_{index}_id': str(record.id), f'dataset_{index}_name': record.display_name})
        context = memory.observe(context, 'datasets.list', {}, listing, round_id=round_id)
        context['last_imported_cube_ids'] = [str(record.id) for record in records]
        machine.store.save_context(machine.session_id, context)

    def apply_pair(self, pair, record, state):
        cube = str(record.id)
        if (sha256(Path(pair['annotation'])) != pair['annotation_sha256']
                or sha256(Path(pair['hdr'])) != pair['header_sha256']
                or snapshot(pair['data_path']) != pair['data_snapshot']):
            raise DataError('SOURCE_CHANGED', '配对预览后来源发生变化，请重新检查')
        with connect_database(self.database) as db:
            prior = db.execute('SELECT source_sha256,header_sha256 FROM dataset_external_annotation WHERE cube_id=?', (cube,)).fetchone()
            confirmed = db.execute('SELECT 1 FROM annotation_confirmation_state c JOIN annotation_draft d ON d.cube_id=c.cube_id '
                                   'WHERE c.cube_id=? AND c.draft_revision=d.revision', (cube,)).fetchone()
        if prior == (pair['annotation_sha256'], pair['header_sha256']) and confirmed:
            return
        labels = self.sessions.drafts.labels(cube)
        positions = {}
        for name in pair['labels']:
            matches = [i for i, row in enumerate(labels) if row[1].casefold() == name.casefold() or row[2].casefold() == name.casefold()]
            if len(matches) > 1:
                raise DataError('LABEL_AMBIGUOUS', '外部类别对应多个项目标签，请先调整标签名称')
            if not matches:
                raise DataError('LABEL_REQUIRED', f'尚未创建标签“{name}”，请先在 AI 对话中明确创建，再重新接入标注。导入不会自动创建标签。')
            positions[name] = matches[0]
        # Reuse the external ROI rasterizer, then encode exact pixel runs. This
        # avoids a change in polygon edge semantics between the two backends.
        regions, _ = roi_maps(Path(pair['annotation']), record.dataset.shape[:2],
                              dict(enumerate(pair['labels'], 1)), pair['header_sha256'])
        source_doc = json.loads(Path(pair['annotation']).read_text('utf-8-sig'))
        if (sha256(Path(pair['annotation'])) != pair['annotation_sha256']
                or sha256(Path(pair['hdr'])) != pair['header_sha256']
                or snapshot(pair['data_path']) != pair['data_snapshot']):
            raise DataError('SOURCE_CHANGED', '读取标注期间来源发生变化，请重新检查')
        document = self.sessions.drafts.empty(cube)
        for index, shape in enumerate(source_doc['shapes'], 1):
            document['regions'].append(dict(region_id=f'r-{index:04d}', op='add', class_index=positions[shape['label']],
                geometry=dict(type='pixel_set', rows=encode_rle(regions == index), segments_fingerprint=None),
                source='migration', confidence='high', created_at=state['created_at']))
        self.sessions.import_external(cube, document)
        with connect_database(self.database) as db:
            db.execute('INSERT INTO dataset_external_annotation VALUES (?,?,?,?) ON CONFLICT(cube_id) DO UPDATE SET '
                       'source_path=excluded.source_path,source_sha256=excluded.source_sha256,header_sha256=excluded.header_sha256',
                       (cube, pair['annotation'], pair['annotation_sha256'], pair['header_sha256']))

    def generate(self, machine, content, action, state, *, paths=None, choice=None, command=None, label_payload=None, expected_id=None):
        sid, store = machine.session_id, machine.store
        row = store.new_round(sid, PATHS.sub('本地输入源', content), [], 'running')
        control = getattr(machine, 'control', None)
        check = control.check if control else lambda: None
        step_count = 0
        def step(tool, summary):
            nonlocal step_count
            step_count += 1
            return machine._step_event(store.add_step(row, tool, {}, 'ok', summary, 0))
        def finish(answer, *, card=True):
            answer = PATHS.sub('本地文件', answer)
            if state and card:
                self.refresh_annotations(state)
                self.save(sid, state)
            store.save_answer(row['id'], answer)
            store.round_status(row['id'], 'done')
            return 'done', dict(content=answer, step_count=step_count, request_status='finished', reply_status='replied',
                                **({'data_intake': self.card(state)} if state and card else {}))
        try:
            check()
            if action in {'统一训练', '配置预处理与训练', '进入预处理'}:
                if command and (not state or command[2] != state['id']):
                    yield finish('这张导入卡片已失效，请使用当前会话最新的导入卡片。', card=False)
                    return
                from spectrumagent.experiments.workspace_training import prepare
                if state and state['imported_ids']:
                    self.refresh_annotations(state)
                    targets = state['ready_ids']
                    if not targets:
                        yield finish('本批还没有已保存的区域标注，请先在画布保存，或接入已有标注。')
                        return
                else:
                    with connect_database(self.database) as db:
                        targets = [r[0] for r in db.execute('SELECT cube_id FROM annotation_confirmation_state')]
                dialogue = machine.tools.experiment_dialogue
                prepare(dialogue, self.registry, self.sessions, sid, targets, check)
                view = dialogue.presented(sid, row['turn_id'], check=check)
                card = dialogue.draft_presentation(sid, view, check)
                yield step('experiments.draft_presentation', card)
                omitted = len(state['imported_ids'])-len(targets) if state and state['imported_ids'] else 0
                yield finish('已将保存的区域标注接入统一训练方案；可在对话中指定预处理或发起Study寻优。\n'
                             + (f'本批 {omitted} 张未保存标注的图片未纳入方案。\n' if omitted else '')
                             + view['plan']+'\n'+view['question'], card=False)
                return
            if action == '标注完成':
                self.refresh_annotations(state)
                remaining = len(state['imported_ids'])-len(state['ready_ids'])
                yield finish(f"已核对保存的区域标注：{len(state['ready_ids'])}/{len(state['imported_ids'])} 张。"
                    + (f'仍有 {remaining} 张未保存，请先在画布保存。' if remaining else
                       '可点击“配置预处理与训练”，或回复“接下来对数据进行预处理”，在对话中配置方案和Study寻优。'))
                return
            if action == 'list':
                ids = []
                lines = []
                listing = {}
                offset = 0
                while True:
                    page = self.registry.catalog(limit=100, offset=offset)
                    titles = {'need_annotation': '待标注', 'need_preprocess': '已标注，可配置训练', 'ready': '已标注，有配方结果'}
                    for record in page['datasets']:
                        ids.append(record['id'])
                        index = len(ids)
                        listing.update({f'dataset_{index}_id': record['id'], f'dataset_{index}_name': record['display_name']})
                        lines.append(f"D{index} · {record['display_name']} · {titles.get(record.get('workflow_status'), '待标注')}")
                    offset += len(page['datasets'])
                    if offset >= page['total']:
                        break
                listing['count'] = len(ids)
                from . import context as memory
                context = json.loads(store.session(sid)['context_json'] or '{}')
                context = memory.observe(context, 'datasets.list', {}, listing, round_id=row['id'])
                store.save_context(sid, context)
                yield step('datasets.list', listing)
                yield finish(f'已登记 {len(ids)} 个数据集。\n'+'\n'.join(lines), card=False)
                return
            if not state or command and command[2] != state['id'] or expected_id and expected_id != state['id']:
                yield finish('这张导入卡片已失效，请使用当前会话最新的导入卡片。', card=False)
                return
            self.refresh_annotations(state)
            # A new import supersedes the old directory-role draft, but never
            # discards its local source references or any completed results.
            if action == 'start':
                with connect_database(self.database) as db:
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name='experiment_pairing_intake'").fetchone():
                        db.execute('DELETE FROM experiment_pairing_intake WHERE session_id=?', (sid,))
            if action == '取消数据导入':
                state['stage'] = 'cancelled'
                yield finish('已结束本次数据导入；已完成的登记与标注保留。')
                return
            if state['stage'] == 'cancelled':
                yield finish('本次导入已经取消，请重新发起导入。', card=False)
                return
            if action == 'open_labels':
                state['label_form_open'] = True
                yield finish('请在下方表单填写标签名称，提交后我会创建并保存。同名标签会复用。')
                return
            if action == 'create_labels':
                state['label_form_open'] = True
                if state['stage'] not in {'imported', 'labels', 'review', 'need_annotations', 'need_images', 'choose_mode'}:
                    yield finish('请先完成本次数据导入，再创建标注标签。')
                    return
                # Resolve the target from the session-owned batch, never from a
                # model-generated project ID or whichever project sorts first.
                with connect_database(self.database) as db:
                    projects = {state['label_project_id']} if state.get('label_project_id') else set()
                    for cube in state['imported_ids']:
                        project = db.execute('SELECT project_id FROM dataset_registry WHERE id=?', (cube,)).fetchone()
                        if project:
                            projects.add(project[0])
                if len(projects) != 1:
                    yield finish('无法确定标签所属的单一项目，请先在标注界面选择项目后创建标签。')
                    return
                names = json.loads(label_payload)
                if isinstance(names, list) and len(names) <= 100 and all(isinstance(name, str) and len(name) <= 100 for name in names):
                    state['label_draft'] = names
                labels = LabelStore(self.database).ensure_names(projects.pop(), names)
                state['labels'] = labels
                state['label_form_open'] = False
                state.pop('label_draft', None)
                created = sum(not label['existing'] for label in labels)
                yield step('labels.create_many', {'created_count': created, 'existing_count': len(labels)-created,
                    **{f'label_{i}_name': label['name'] for i, label in enumerate(labels, 1)}})
                if state['imported_ids']:
                    remaining = len(state['imported_ids']) - len(state['ready_ids'])
                    next_step = (f'标签类别已就绪，尚有 {remaining} 个样品未保存区域标注。下一步请点击“下一步：超像素人工标注”，'
                                 '选择逐张生成或提前生成全部，再在画布上点选区域并赋予标签。' if remaining else
                                 '本批样品已有可用区域标注，下一步可在对话中配置预处理与训练；也可调整区域。')
                else:
                    next_step = '导入图片后即可使用这些标签进行标注。'
                if state.get('annotation_retry'):
                    next_step = '请点击“重新接入标注”，把 ROI 类别匹配到这些已有标签；导入不会再创建标签。'
                yield finish(f"标签已就绪：{'、'.join(label['name'] for label in labels)}（新增 {created} 个，复用 {len(labels)-created} 个）。{next_step}")
                return
            if action == '进入人工标注':
                targets = state['imported_ids']
                if not targets:
                    yield finish('本次尚无可进入该步骤的样品，请先完成数据接入。')
                    return
                # Selecting annotation is a choice of scope, not permission
                # to segment. Use the existing explicit mode/task flow next.
                context = store.context(sid)
                machine.tools.select_annotation_targets(targets, context)
                store.save_context(sid, context)
                state['stage'] = 'imported'
                state['label_form_open'] = False
                answer = finish(f'下一步：为本次导入的 {len(targets)} 个样品进行超像素人工标注。'
                    '请在下方选择“逐张生成（推荐）”或“提前生成全部”；分割就绪后点击任务卡片的“进入标注”，'
                    '在画布中选择标签、点选超像素并保存区域标注。创建标签本身不会产生区域标注。')
                yield answer[0], {**answer[1], 'annotation_target_cube_ids': targets,
                                  'reply_status': 'needs_input', 'task_result': 'needs_input'}
                return
            if action == '查看导入异常':
                yield finish('\n'.join([*state['issues'], *('未配对：'+Path(p).name for p in state.get('unused', []))]) or '本次没有配对异常。')
                return
            if action == '调整标注路径':
                state.update(stage='need_annotations', mode='labeled', pairs=[], issues=[], annotations=[])
                yield finish('请选择或输入对应的标注目录或 JSON 文件路径。')
                return
            if action == '使用已配对标注':
                if state['stage'] == 'imported' and not state.get('annotation_retry'):
                    yield finish('这批数据已经接入，可直接进入后续步骤。')
                    return
                if state.get('annotation_retry') and state['stage'] == 'imported':
                    state['stage'] = 'review'
                    prior_label_issues = state.pop('annotation_label_issues', [])
                    state['issues'] = [issue for issue in state['issues'] if issue not in prior_label_issues]
                if state['stage'] != 'review' or not state['pairs']:
                    yield finish('请先提供标注路径并完成有效配对。')
                    return
                # Revalidate the complete preview before any imports or labels.
                for pair in state['pairs']:
                    check()
                    if (sha256(Path(pair['annotation']), check) != pair['annotation_sha256']
                            or sha256(Path(pair['hdr']), check) != pair['header_sha256']
                            or snapshot(pair['data_path']) != pair['data_snapshot']):
                        raise DataError('SOURCE_CHANGED', '配对预览后来源发生变化，请重新检查标注路径')
                records = self.import_images(state, check, lambda: self.save(sid, state))
                self.remember(machine, records, row['id'])
                self.save(sid, state)
                yield step('datasets.import', {'status': 'imported', 'dataset_count': len(records)})
                indexed = {os.path.normcase(str(Path(r.dataset.header_path).resolve())): r for r in records}
                state['annotation_retry'] = False
                for pair in state['pairs']:
                    check()
                    record = indexed.get(os.path.normcase(pair['hdr']))
                    if record is None:
                        continue  # Its registration error is already in issues.
                    try:
                        self.apply_pair(pair, record, state)
                        cube = str(record.id)
                        if cube not in state['ready_ids']:
                            state['ready_ids'].append(cube)
                        self.save(sid, state)
                        yield step('annotations.external_import', {'status': 'saved', 'cube_id': cube})
                    except (DataError, OSError, ValueError) as error:
                        detail = error.payload.detail if isinstance(error, DataError) else str(error)
                        issue = f"{Path(pair['hdr']).name}：{detail}"
                        state['issues'].append(issue)
                        if isinstance(error, DataError) and error.code in {'LABEL_REQUIRED', 'LABEL_AMBIGUOUS'}:
                            state['annotation_retry'] = True
                            state.setdefault('annotation_label_issues', []).append(issue)
                state['stage'] = 'imported'
                yield finish(f"已登记 {len(state['imported_ids'])} 个数据集，其中 {len(state['ready_ids'])} 个具备可用标注。"
                    + ('导入不会创建标签。请在 AI 对话中创建所需标签或处理重名，再点击“重新接入标注”。' if state['annotation_retry'] else
                       '可在对话中配置预处理与训练。其余样品可补充标注。'))
                return
            if action == '选择导入方式':
                if state['stage'] not in {'choose_mode', 'need_images'} or command[3] is None:
                    yield finish('导入方式已经确定，请使用当前步骤的操作。')
                    return
                choice = 'unlabeled' if command[3] == '未标注' else 'labeled'
            if choice:
                state['mode'] = choice
            if paths:
                # Bind every path to the nearest explicit field. A path-only
                # reply belongs to the field currently being requested.
                matches = list(PATHS.finditer(content))
                groups = defaultdict(list)
                role = 'annotations' if state['images'] and state['mode'] == 'labeled' and action != 'start' else 'images'
                cursor = 0
                for match, path in zip(matches, paths):
                    fields = list(re.finditer(r'原图|原始数据|标注(?=目录|文件|路径|位置|在|为|\s*[：:]|\s*$)', content[cursor:match.start()]))
                    if fields:
                        role = 'annotations' if fields[-1][0] == '标注' else 'images'
                    groups[role].append(path)
                    cursor = match.end()
                state.update(groups)
            if action == '检查同目录标注':
                state['mode'] = 'labeled'
                state['annotations'] = list(dict.fromkeys(str(Path(p) if Path(p).is_dir() else Path(p).parent) for p in state['images']))
            if not state['images']:
                state['stage'] = 'need_images'
                yield finish('请选择或输入原图目录或 ENVI 文件路径。')
            elif not state['mode']:
                state['stage'] = 'choose_mode'
                yield finish('已收到原图位置，请选择这批数据尚未标注还是已有标注。')
            elif state['mode'] == 'unlabeled':
                records = self.import_images(state, check, lambda: self.save(sid, state))
                self.remember(machine, records, row['id'])
                state['headers'] = [r.dataset.header_path for r in records]
                state['stage'] = 'imported'
                self.save(sid, state)
                yield step('datasets.import', {'status': 'imported', 'dataset_count': len(records)})
                yield finish(f"已登记 {len(records)} 个数据集，异常 {len(state['issues'])} 条。下一步请提供标签名称，再选择超像素分割范围并人工点选标注。")
            elif not state['annotations']:
                state['stage'] = 'need_annotations'
                yield finish('请选择或输入对应的标注目录或 JSON 文件路径，也可以选择“与原图同目录”。无需先指定训练和测试用途。')
            else:
                self.preview(state, check)
                yield finish(f"原图 {len(state['headers'])} 个，成功配对 {len(state['pairs'])} 个，未配对 {len(state['unused'])} 个，异常 {len(state['issues'])} 条。请核对类别与异常后接入标注。")
        except (DataError, OSError, ValueError, KeyError, TypeError) as error:
            detail = error.payload.detail if isinstance(error, DataError) else str(error)
            if action == 'create_labels':
                if isinstance(error, DataError) and error.code == 'INVALID_LABEL':
                    detail = '；'.join(field['message'] for field in error.payload.context.get('fields', [])) or detail
                yield finish('标签创建未完成：'+detail+'。请调整名称后再提交。')
                return
            # This local reply is rendered directly; never included in a model
            # prompt. Redact paths nevertheless to keep history summaries safe.
            detail = PATHS.sub('本地文件', detail)
            if state and state['imported_ids']:
                yield step('datasets.import', {'status': 'imported', 'dataset_count': len(state['imported_ids'])})
            yield finish('数据接入未完成：'+detail+'。请调整路径或重新检查；已完成的样品保留。')
