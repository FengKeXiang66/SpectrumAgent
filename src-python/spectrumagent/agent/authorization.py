"""Server-owned annotation intent; model arguments never mint consent."""
from hashlib import sha256
import json
import re
from uuid import UUID, uuid4

from spectrumagent.data import DataError

NEGATION = r'不要|不需要|不用|无需|暂不|先不|不能|禁止|别(?=再|对|给|用|做|生成|准备|执行|分割|开始)|勿|取消|停止|不(?:对|给|生成|准备|执行|分割)'
QUERY = r'查看|查询|列出|检查|核对|解释|介绍'
QUESTION = r'怎么|如何|是否|是不是|能否|能不能|为什么|什么|怎样|多久|哪里|哪种|多少|有没有|举例|例如|假如|如果|吗|[？?]'
ACTION_TEXT = {'prepare': '超像素分割', 'save': '保存标注', 'diffuse': '扩散'}


def task_target_hash(pairs):
    normalized = [(str(UUID(cube)), content.lower()) for cube, content in pairs]
    if (not normalized or len({cube for cube, _ in normalized}) != len(normalized)
            or any(not re.fullmatch('[0-9a-f]{64}', content) for _, content in normalized)):
        raise DataError('INVALID_REQUEST', '任务目标需要唯一数据 ID 和完整内容哈希')
    body = json.dumps({'version': 1, 'members': sorted(normalized)}, sort_keys=True, separators=(',', ':'))
    return sha256(body.encode()).hexdigest()


def source_baseline(registry, cube):
    """Cheap registration/source identity captured before queueing, never spectra."""
    dataset, _ = registry.readable(cube, raw=False)
    from pathlib import Path
    return tuple((s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                 for s in (Path(p).stat() for p in (dataset.header_path, dataset.data_path)))


def unquoted(content):
    return re.sub(r'```[\s\S]*?```|[“「『"\'][^”」』"\']*[”」』"\']', '', content)


def annotation_mode(content):
    """Closed replies to the annotation mode question, never questions/examples."""
    text = content.strip().rstrip('。！!').strip()
    refs = r'D\d+(?:\s*(?:[-–—~～至到]\s*D?\d+|[、,，]\s*D\d+))*'
    scope = rf'(?:(?:对)?(?:{refs}|(?:所有|全部)(?:已导入的?|的)?数据)(?:进行|开始)?\s*[，,：:]?\s*)?'
    prefix = r'(?:请)?(?:选择)?' + scope
    if re.fullmatch(prefix + r'(?:从第[一1]张(?:图像|图片)?开始)?逐张生成(?:超像素)?', text, re.I):
        return 'per_image'
    if re.fullmatch(prefix + r'提前(?:批量生成(?:全部)?|生成全部)(?:超像素)?', text, re.I):
        return 'all'
    return None


def dataset_references(text, catalog):
    """Expand inclusive D ranges against the actual displayed catalogue only."""
    # UUIDs can begin with d + decimal digits + '-'. They are complete IDs,
    # never malformed catalogue ranges (for example d1234567-abcd-...).
    text = re.sub(r'(?<![a-zA-Z0-9_-])[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}(?![a-zA-Z0-9_-])',
                  ' ', text, flags=re.I)
    refs = []
    ranges = r'(?<![a-zA-Z0-9_-])D(\d+)\s*[-–—~～至到]\s*D?(\d+)(?![a-zA-Z0-9_-])'
    def expand(match):
        start, end = map(int, match.groups())
        if not 0 < start <= end or end - start + 1 > len(catalog):
            raise DataError('TASK_TARGET_REQUIRED', '数据范围无效，请使用已展示目录中的连续 D 编号')
        refs.extend('D'+str(index) for index in range(start, end+1))
        return ' '
    remainder = re.sub(ranges, expand, text, flags=re.I)
    if re.search(r'(?<![a-zA-Z0-9_-])D\d+\s*[-–—~～至到]', remainder, re.I):
        raise DataError('TASK_TARGET_REQUIRED', '数据范围不完整，请明确起止 D 编号')
    refs.extend(re.findall(r'(?<![a-zA-Z0-9_-])D\d+(?![a-zA-Z0-9_-])', remainder, flags=re.I))
    by_ref = {row['ref'].upper(): row['id'] for row in catalog}
    if any(ref.upper() not in by_ref for ref in refs):
        raise DataError('TASK_TARGET_REQUIRED', '请先列出数据，再使用目录中的 D 编号指定范围')
    return list(dict.fromkeys(by_ref[ref.upper()] for ref in refs))


def regression_configuration(content):
    text = unquoted(content)
    return bool(re.search(r'(?:回归|PLS).*(?:方案|模板|参数)|(?:回归|训练)方案', text, re.I)
                and not re.search(r'标注|画布|超像素|分割|扩散', text))


def operations(content):
    text = unquoted(content).strip()
    # Saving a numerical plan or setting its random seed is not a canvas action.
    if regression_configuration(content):
        return set()
    # Fail closed for questions/examples/negation rather than interpreting an
    # occurrence of "分割" as an instruction. Labels are parsed separately.
    if re.search(QUESTION, text):
        return set()
    if annotation_mode(content):
        return {'prepare'}
    clauses = re.split(r'[，,。；;\n]', text)
    result = set()
    if re.search(r'准备(?:当前|这张).*标注', text) and '默认' in text and not re.search(NEGATION + '|' + QUERY, text):
        result.add('prepare')
    for clause in clauses:
        if re.search(NEGATION + '|' + QUERY, clause):
            continue
        if re.search(r'(?:生成|准备|执行|进行|开始|重试|分割|逐张)', clause) and re.search(r'超像素|分割|逐张', clause):
            result.add('prepare')
        if re.search(r'扩散|种子', clause) and re.search(r'生成|进行|使用|执行|开始|扩散', clause):
            result.add('diffuse')
        if '保存' in clause and '已保存' not in clause:
            result.add('save')
    return result


class AnnotationAuthorization:
    def __init__(self, service):
        self.service = service

    def pending_target(self, sid, state):
        target = self.service.annotation_targets.get(sid)
        if (target and target['boot_id'] == self.service.boot_id
                and target['target_id'] == (state.get('annotation_pending_target') or {}).get('target_id')):
            return target
        return None

    def capture(self, sid, content, workspace, request_id, state, *, selected_cube_ids=None):
        from backend.database import connect_database
        registry = self.service.registry
        if registry is None:
            return
        denied = set()
        for clause in re.split(r'[，,。；;\n]', unquoted(content)):
            if not re.search(NEGATION, clause):
                continue
            if re.search(r'分割|超像素|逐张', clause): denied.add('prepare')
            if re.search(r'扩散|种子', clause): denied.add('diffuse')
            if '保存' in clause: denied.add('save')
        if denied:
            if 'prepare' in denied:
                self.service.annotation_targets.pop(sid, None)
                state.pop('annotation_pending_target', None)
            old = state.get('operation_authorization')
            if old:
                record = self.service.authorization_records.get(old['authorization_id'])
                while record:
                    record['operations'] = [op for op in record['operations'] if op not in denied]
                    if not record['operations']:
                        record['status'] = 'revoked'
                    record = self.service.authorization_records.get(record.get('parent_authorization_id'))
                state['operation_authorization'] = {**old, 'operations': [op for op in old['operations'] if op not in denied]}
        clean = unquoted(content)
        if re.search(r'取消标注|停止标注|不(?:再)?标注', clean):
            self.service.annotation_targets.pop(sid, None)
            state.pop('annotation_pending_target', None)
        ops = operations(content)
        pending = self.pending_target(sid, state)
        if not ops and re.search(r'预处理|配方|建模|训练|模型|推理',clean):
            return  # A later processing request does not amend an annotation target.
        # A range/label answer is task selection, not permission to prepare/save.
        selecting = not re.search(QUESTION, clean) and any(
            not re.search(NEGATION + '|' + QUERY, clause)
            and (pending is not None or bool(re.search(r'标注|标签', clause)))
            for clause in re.split(r'[，,。；;\n]', clean))
        if not ops and not selecting:
            return
        # Read complete ledger order; D references use the catalogue last shown
        # to the user, not a freshly sorted provider-generated list.
        with connect_database(self.service.database) as db:
            rows = db.execute('SELECT id FROM dataset_registry ORDER BY rowid').fetchall()
        all_ids = [r[0] for r in rows]
        catalog_snapshot_id = sha256(json.dumps(all_ids, separators=(',', ':')).encode()).hexdigest()
        names = registry.display_names()
        ids = []
        expected_hashes = {}
        selector_text = '，'.join(c for c in re.split(r'[，,。；;\n]', unquoted(content))
                                 if not re.search(NEGATION + '|' + QUERY, c))
        # “全部使用默认参数” describes parameters, not a member selection.
        all_targets = bool(re.search(r'(?:所有|全部)(?:(?:已)?导入的?|的|已登记的?)?(?:数据(?:集)?|样品|图片|图像)|(?:数据(?:集)?|样品|图片|图像)(?:中的?)?(?:所有|全部)', selector_text))
        excluded = [c for c in re.split(r'[，,。；;\n]', unquoted(content)) if re.search(NEGATION, c)]
        if re.search(r'除了?|排除|不包括|不包含|不含', selector_text) or all_targets and any(
                re.search(r'(?<![a-zA-Z0-9_-])D\d+(?![a-zA-Z0-9_-])', c, re.I)
                or any(cube in c or names.get(cube) and names[cube] in c for cube in all_ids) for c in excluded):
            raise DataError('TASK_TARGET_REQUIRED', '当前范围包含排除条件，请明确列出要处理的数据，避免扩大范围')
        if re.search(r'冻结版本|dataset_version_id', selector_text) and self.service.versions:
            for version in re.findall(r'(?:冻结版本|dataset_version_id)\s*[:：=]?\s*([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})', selector_text):
                if version not in all_ids:
                    for member in self.service.versions.get_frozen(version)['members']:
                        ids.append(member['cube_id'])
                        expected_hashes[member['cube_id']] = member['content_hash']
        if selected_cube_ids is not None:
            # Structured UI selections and session-owned intake batches supply
            # this server-side argument; model tools cannot create this evidence.
            if type(selected_cube_ids) is not tuple or not selected_cube_ids or len(set(selected_cube_ids)) != len(selected_cube_ids):
                raise DataError('TASK_TARGET_REQUIRED','请选择非空且不重复的实际数据集范围')
            ids=list(selected_cube_ids)
        elif ids:
            pass
        elif all_targets:
            ids = all_ids
        else:
            for cube in all_ids:
                if cube in selector_text or names.get(cube) and re.search(r'(?<![a-zA-Z0-9_])'+re.escape(names[cube])+r'(?![a-zA-Z0-9_])', selector_text):
                    ids.append(cube)
            ids.extend(dataset_references(selector_text, state.get('dataset_catalog', [])))
            if re.search(r'当前(?:这)?(?:张|幅|图|样品|数据)', selector_text) and workspace and workspace.get('cube_id'):
                ids.append(workspace['cube_id'])
            if not ids and annotation_mode(content) and pending and pending['cube_ids']:
                ids = pending['cube_ids'].copy()
            if not ids and re.search(r'继续|下一张|逐张', content):
                old = state.get('operation_authorization') or {}
                if old.get('boot_id') == self.service.boot_id:
                    ids = self.service.authorization_records.get(old.get('authorization_id'), {}).get('cube_ids', [])
            if not ids and state.get('selected_cube_id') and state.get('task_selection_source') == 'user' and re.search(r'继续|默认|分割|逐张|保存', content):
                ids = [state['selected_cube_id']]
        ids = list(dict.fromkeys(ids))
        if not ops and not ids:
            if pending is None:
                target = {'target_id': str(uuid4()), 'boot_id': self.service.boot_id, 'cube_ids': [],
                          'baselines': {}, 'expected_content_hashes': {}, 'source_request_id': request_id,
                          'awaiting_mode':bool(re.search(r'标注|逐张',clean))}
                self.service.annotation_targets[sid] = target
                state['annotation_pending_target'] = {'target_id': target['target_id'], 'member_count': 0}
            return
        if not ids or any(cube not in all_ids for cube in ids):
            actions = '、'.join(ACTION_TEXT[op] for op in sorted(ops) if op in ACTION_TEXT)
            message = f'请明确要{actions}的数据范围' if actions else '请明确要处理的数据范围'
            raise DataError('TASK_TARGET_REQUIRED', message)
        baselines = {}
        for cube in ids:
            try:
                baselines[cube] = source_baseline(registry, cube)
            except (DataError, OSError):
                baselines[cube] = None  # Unavailable members fail in isolation, never rebound later.
        if annotation_mode(content) and pending and pending['cube_ids'] == ids:
            # Mode selection must use the scope captured in the range answer:
            # neither a later import nor a source replacement can inherit it.
            baselines = pending['baselines'].copy()
            expected_hashes = pending['expected_content_hashes'].copy()
            catalog_snapshot_id = pending['catalog_snapshot_id']
        selection_id = pending['target_id'] if pending and annotation_mode(content) else None
        selection_request = pending['source_request_id'] if selection_id else request_id
        if not ops or 'prepare' in ops:
            target = {'target_id': str(uuid4()), 'boot_id': self.service.boot_id, 'cube_ids': ids,
                      'baselines': baselines, 'expected_content_hashes': expected_hashes,
                      'source_request_id': selection_request, 'catalog_snapshot_id': catalog_snapshot_id}
            target['awaiting_mode'] = not ops and bool((pending or {}).get('awaiting_mode') or re.search(r'标注|逐张',clean))
            self.service.annotation_targets[sid] = target
            state['annotation_pending_target'] = {'target_id': target['target_id'], 'member_count': len(ids)}
            selection_id = target['target_id']
        if not ops:
            return
        previous = self.service.authorization_records.get((state.get('operation_authorization') or {}).get('authorization_id'))
        parent = None
        if previous and previous['status'] not in {'invalid','revoked'} and set(previous['cube_ids']) == set(ids) and all(
                previous['baselines'].get(cube) == baselines[cube] for cube in ids):
            # Preserve operation-specific consent as an explicit evidence chain;
            # a later save request does not erase an earlier seed authorization.
            ops.update(previous['operations'])
            expected_hashes = {**previous['expected_content_hashes'], **expected_hashes}
            parent = previous['authorization_id']
        record = {
            'authorization_id': str(uuid4()), 'session_id': sid, 'boot_id': self.service.boot_id,
            'source_request_id': request_id, 'source_user_message_id': (request_id + ':input') if request_id else None,
            'source_digest': sha256(content.encode()).hexdigest(), 'cube_ids': ids,
            'target_selection_id': selection_id, 'target_source_request_id': selection_request,
            'catalog_snapshot_id': catalog_snapshot_id,
            'selector': 'ui_selection' if selected_cube_ids is not None else 'all' if all_targets else 'explicit_or_resolved_reference',
            'operations': sorted(ops), 'baselines': baselines, 'profile': 'annotation-default-v1',
            'expected_content_hashes': expected_hashes,
            'status': 'pending_verification', 'verified_targets': {},
            'parent_authorization_id': parent,
        }
        self.service.authorization_records[record['authorization_id']] = record
        state['operation_authorization'] = {k:v for k,v in record.items() if k not in {'cube_ids','baselines','expected_content_hashes'}}
        state['task_target'] = {'authorization_id': record['authorization_id'], 'member_count': len(ids),
                                'operations': sorted(ops), 'identity_status': 'pending'}

    def require(self, sid, state, name, args, batch=None):
        operation = {'annotations.prepare': 'prepare', 'annotations.prepare_batch': 'prepare',
                     'annotations.propose': 'diffuse', 'annotations.draft_confirm': 'save'}.get(name)
        if operation is None:
            return None
        grant = self.service.authorization_records.get((state.get('operation_authorization') or {}).get('authorization_id'), {})
        if (grant.get('session_id') != sid or grant.get('boot_id') != self.service.boot_id
                or grant.get('status') in {'invalid','revoked'} or operation not in grant.get('operations', [])):
            raise DataError('OPERATION_NOT_AUTHORIZED', '该操作没有对应的明确用户指令，请指定操作和数据范围')
        if name == 'annotations.prepare_batch':
            if args.get('retry_of'):
                receipt = batch.receipts.get(args['retry_of']) if batch else None
                if not receipt or receipt.get('owner_session_id') != sid:
                    raise DataError('OPERATION_NOT_AUTHORIZED', '父任务不属于本会话')
                ids = [m['cube_id'] for m in receipt['members']]
            elif args.get('dataset_version_id'):
                ids = [m['cube_id'] for m in self.service.versions.get_frozen(args['dataset_version_id'])['members']]
            else:
                ids = args.get('cube_ids') or []
        else:
            ids = [args.get('cube_id')]
        if not ids or not set(ids).issubset(grant['cube_ids']):
            raise DataError('OPERATION_NOT_AUTHORIZED', '工具目标超出用户明确指定的范围')
        for cube in ids:
            if grant['baselines'].get(cube) is None:
                continue
            actual = source_baseline(self.service.registry, cube)
            expected = tuple(tuple(p) for p in grant['baselines'].get(cube, []))
            if actual != expected:
                grant['status'] = 'invalid'
                raise DataError('SOURCE_CHANGED', '源身份与授权时不一致，请重新明确准备任务')
        return grant

    def verify_target(self, grant, engine, cube):
        """Bind a single write to content identity before invoking its handler."""
        baseline = grant['baselines'].get(cube)
        if engine is None or baseline is None:
            raise DataError('SOURCE_CHANGED', '源身份尚未核验，未执行操作')
        identity, signature = engine.source_identity(cube)
        if (signature != tuple(map(tuple, baseline))
                or grant['expected_content_hashes'].get(cube, identity) != identity):
            grant['status'] = 'invalid'
            raise DataError('SOURCE_CHANGED', '源内容与授权目标不同')
        target = task_target_hash([(cube, identity)])
        grant['expected_content_hashes'][cube] = identity
        grant['verified_targets'][target] = [cube]
        grant['status'] = 'active'
        return target
