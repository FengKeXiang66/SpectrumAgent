"""Bridge saved pixel annotations to the shared experiment/Study pipeline."""
from copy import deepcopy
from contextlib import nullcontext
import json
from pathlib import Path
import re
from uuid import UUID, uuid4

import numpy as np
from scipy.ndimage import label as components

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.storage import guard
from .inputs import WAVELENGTH_UNITS
from .service import save_arrays, sha256, write_json

OPEN = '使用当前已标注数据新建训练方案'
SPLIT = re.compile(r'(?:将|把)?\s*(?:第)?\s*([\d、，,\s]+)\s*张?\s*(?:图|样品)?\s*(?:设为|作为|用于)测试(?:集)?(?:[，,；;\s]*其余(?:用于|作为|为)训练(?:集)?)?[。！!\s]*')


def verified_output(path, digest):
    """Recognize managed masks without registering app output as external data."""
    try:
        identifier = str(UUID(path.parent.name))
        record = json.loads((path.parent/'manifest.json').read_text('utf-8'))
        if identifier == path.parent.name and record['masks'][path.name] == digest:
            return identifier
    except (OSError, ValueError, KeyError, TypeError):
        pass
    raise DataError('ANNOTATION_SNAPSHOT_CHANGED', '训练区域副本与生成记录不一致，请重新建立训练方案。')


def prepare(dialogue, registry, sessions, owner, cube_ids, check=lambda: None):
    """Copy confirmed raster truth, never polygon projections or processed spectra."""
    if dialogue.tasks.active(owner) or dialogue.study.has_active(owner):
        raise DataError('EXPERIMENT_BUSY', '训练或寻优正在运行，请等待结束后再建立方案。')
    cube_ids = list(dict.fromkeys(cube_ids))
    if not cube_ids:
        raise DataError('ANNOTATION_REQUIRED', '请先保存至少一张图片的区域标注。')
    captured, catalog, declared = [], {}, {}
    for cube in cube_ids:
        check()
        lease = sessions.resources.lease(cube, required=False) if sessions.resources else nullcontext()
        with lease, sessions._lock, connect_database(dialogue.database) as db:
            row = db.execute('SELECT v.snapshot_ref,c.draft_revision,d.revision FROM annotation_confirmation_state c '
                'JOIN annotation_version v ON v.id=c.annotation_version_id '
                'JOIN annotation_draft d ON d.cube_id=c.cube_id WHERE c.cube_id=?', (cube,)).fetchone()
            if not row or row[1] != row[2]:
                raise DataError('ANNOTATION_REQUIRED', '选中的图片有未保存的标注，请保存后重新建立训练方案。')
            base = sessions.paths.snapshots.resolve()
            folder = (base / row[0]).resolve()
            if not folder.is_relative_to(base):
                raise DataError('INVALID_SNAPSHOT_REF', '标注快照位置非法。')
            with np.load(folder/'label_map.npz', allow_pickle=False) as archive:
                raster = archive['label_map'].copy()
            mapping = json.loads((folder/'label_index.json').read_text('utf-8'))
            labels = {r[0]: (r[1], bool(r[2]), r[3]) for r in db.execute('SELECT id,name,is_background,color_hex FROM label WHERE deleted_at IS NULL')}
            declared.update({key: labels[key][0] for key in mapping.values() if key in labels and not labels[key][1]})
            for index in np.unique(raster[raster >= 0]):
                identifier = mapping[str(int(index))]
                if identifier not in labels:
                    raise DataError('LABEL_MAPPING_INVALID', '已保存标注引用的类别不存在，请核对后重新保存。')
                catalog[identifier] = labels[identifier]
            dataset, _ = registry.readable(cube, raw=True)
            if raster.shape != dataset.shape[:2]:
                raise DataError('INVALID_LABEL_MAP', '已保存标注尺寸与原图不一致。')
            captured.append((cube, dataset, raster, mapping))
    used = {mapping[str(int(index))] for _, _, raster, mapping in captured for index in np.unique(raster[raster >= 0])
            if not catalog[mapping[str(int(index))]][1]}
    names = [catalog[key][0] for key in sorted(used)]
    if len(names) < 2 or len(set(names)) != len(names):
        raise DataError('INSUFFICIENT_CLASSES', '训练至少需要两个名称互异且有已保存前景像素的类别；仅创建标签不算标注。')
    class_numbers = {key: i for i, key in enumerate(sorted(used), 1)}
    sources, members, summaries = {}, [], []
    def reference(path):
        text = str(Path(path).resolve())
        ref = next((key for key, value in sources.items() if value == text), None)
        if ref is None:
            ref = 'S'+str(len(sources)+1)
            sources[ref] = text
        return ref
    root = dialogue.service.paths.exports/'workspace-training'/str(uuid4())
    guard.mkdir(root, parents=True)
    axes, units = [], set()
    for cube, dataset, raster, mapping in captured:
        check()
        regions = np.zeros(raster.shape, np.int32)
        truth = np.zeros(raster.shape, np.int64)
        offset, counts = 0, {}
        for old in np.unique(raster[raster >= 0]):
            identifier = mapping[str(int(old))]
            if identifier not in class_numbers:
                continue
            mask = raster == old
            regions_here, count = components(mask)
            regions[mask] = regions_here[mask]+offset
            truth[mask] = class_numbers[identifier]
            counts[catalog[identifier][0]] = int(mask.sum())
            offset += count
        if not counts:
            continue
        roi = root/(cube+'.npz')
        save_arrays(roi, region_map=regions, label_map=truth)
        member = dict(header_ref=reference(dataset.header_path), data_ref=reference(dataset.data_path),
                      roi_ref=reference(roi), sample_id=reference(dataset.header_path))
        members.append(member)
        summaries.append(dict(number=len(members), cube_id=cube, name=dataset.name, counts=counts,
                              roi_ref=member['roi_ref'], roi_sha256=sha256(roi)))
        unit = str(dataset.metadata.get('wavelength units', '')).lower()
        units.add(next((key for key, aliases in WAVELENGTH_UNITS.items() if unit in aliases), None))
        axes.append(np.sort(np.asarray(dataset.wavelengths, float)))
    write_json(root/'manifest.json', {'masks': {Path(sources[row['roi_ref']]).name: row['roi_sha256'] for row in summaries}})
    settings = dict(kind='roi_images', members=members, neighborhood=1, sampling_stride=1,
                    evaluation_unit='center_pixel', quality=dict(min_mean=0., min_std=0., max_zero_fraction=1., saturation=None))
    if len(units) == 1 and None not in units:
        settings['wavelength_unit'] = next(iter(units))
    document = dict(name='当前标注 PLS-DA', train=settings, classes=[dict(label=i, name=name) for i, name in enumerate(names, 1)],
                    class_colors={class_numbers[key]: catalog[key][2] for key in used},
                    preprocessing=[], model=dict(n_components=1, scale=False, max_iter=1000), additional_metrics=['kappa'],
                    test_usage='independent_test', workspace_selection=summaries,
                    notes='从已保存像素标注建立；默认单像元、步长1、无附加预处理。可在对话中修改或进行Study；实物分组未知。')
    omitted = sorted({name for key, name in declared.items() if key not in used})
    if omitted:
        document['notes'] += '无前景标注像素的标签未纳入：'+'、'.join(omitted)+'。'
    if axes and len(axes[0]) >= 2 and all(np.array_equal(axis, axes[0]) for axis in axes) and np.all(np.diff(axes[0]) > 0):
        document['axis'] = dict(kind='saved_native', wavelengths=axes[0].tolist(), declared_unit=settings.get('wavelength_unit'))
    with connect_database(dialogue.database) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO experiment_dialogue(session_id) VALUES (?)', (owner,))
        db.execute("UPDATE experiment_dialogue SET document_json=?,sources_json=?,revision=revision+1,active=1,"
                   "reviewed_revision=NULL,review_turn=NULL,review_sources_json=NULL,run_status='idle',experiment_id=NULL,"
                   "previous_document_json=NULL,base_experiment_id=NULL WHERE session_id=?",
                   (json.dumps(document, ensure_ascii=False), json.dumps(sources, ensure_ascii=False), owner))
        db.execute('UPDATE inference_draft SET active=0 WHERE session_id=?', (owner,))
        dialogue.clear_confirmation(db, owner)
    return document


def split(dialogue, owner, text):
    match = SPLIT.fullmatch(text)
    record = dialogue._read(owner)
    if not match or not record or not record['document'].get('workspace_selection'):
        return False
    if dialogue.tasks.active(owner) or dialogue.study.has_active(owner):
        raise DataError('EXPERIMENT_BUSY', '训练或寻优正在运行，暂不能修改划分。')
    selected = {int(value) for value in re.findall(r'\d+', match[1])}
    document = deepcopy(record['document'])
    members = {item['roi_ref']: item for role in ('train', 'test') for item in document.get(role, {}).get('members', [])}
    rows = document['workspace_selection']
    if not selected or not selected < {r['number'] for r in rows}:
        raise DataError('INVALID_SPLIT', '请指定清单中部分图片作为测试集，其余保留训练，例如“将第2、4张设为测试”。')
    covered = {name for item in rows if item['number'] not in selected for name in item['counts']}
    missing = {item['name'] for item in document['classes']} - covered
    if missing:
        raise DataError('INVALID_SPLIT', '该划分的训练集缺少类别：'+'、'.join(sorted(missing))+'。请调整测试图片。')
    for role, is_test in (('train', False), ('test', True)):
        spec = deepcopy(document['train'])
        spec['members'] = [members[r['roi_ref']] for r in rows if (r['number'] in selected) == is_test]
        if is_test:
            spec.pop('max_per_class', None)
        document[role] = spec
    with connect_database(dialogue.database) as db:
        db.execute('BEGIN IMMEDIATE')
        updated = db.execute("UPDATE experiment_dialogue SET document_json=?,revision=revision+1,reviewed_revision=NULL,"
            "review_turn=NULL,review_sources_json=NULL,active=1 WHERE session_id=? AND revision=? AND run_status='idle'",
            (json.dumps(document, ensure_ascii=False), owner, record['revision']))
        if not updated.rowcount:
            raise DataError('EXPERIMENT_DRAFT_CONFLICT', '方案已更新，请读取当前方案后再划分。')
        dialogue.clear_confirmation(db, owner)
    return True


def sides(document, sources):
    return {title: [dict(hdr=sources[m['header_ref']], img=sources[m['data_ref']]) for m in document[role]['members']]
            for role, title in (('train', '训练'), ('test', '测试')) if document.get(role, {}).get('members')}
