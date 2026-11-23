"""Re-extract the published five-class center lists, independently of their reference spectra."""
from collections import defaultdict
import csv
import json
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
from threadpoolctl import threadpool_limits

from spectrumagent.data.readers import open_envi
from spectrumagent.data import DataError
from spectrumagent.storage import guard
from .inputs import mapping_weights, quality_mask, roi_maps, sha256
from .schema import Quality
from .service import save_arrays, write_json

# Published extraction contract; the reference NPZ only participates in verification.
VERSION = 'five_class_pet_only_20261110'
CLASSES = {1: 'PE', 2: 'PP', 3: 'PET', 4: 'EPS', 5: '纸'}
AXIS = np.arange(1120., 1680., 5.)
QUALITY = Quality(min_mean=.02, min_std=.002, max_zero_fraction=.05, saturation=65535.)


def verified_output(path, digest):
    try:
        identifier = str(UUID(path.parent.name))
        role = {'训练光谱.npz':'训练','测试V2光谱.npz':'测试'}[path.name]
        record = json.loads((path.parent/'核验.json').read_text('utf-8'))
        if (identifier == path.parent.name and record['version'] == VERSION
                and record['splits'][role]['output_sha256'] == digest):
            return identifier
    except (ValueError, OSError, KeyError, TypeError):
        pass
    raise DataError('CENTER_REPLAY_CHANGED','取谱产物与本机核验记录不一致')


def frozen_file(root, name, hashes):
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or sha256(path) != hashes.get(name):
        raise ValueError(f'发布清单与文件不符：{name}')
    return path


def centers_by_source(path):
    grouped = defaultdict(list)
    seen = set()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        for index, item in enumerate(csv.DictReader(stream)):
            hdr = Path(item['source'])
            row, col, region, label = (int(item[k]) for k in ('row','col','region','label'))
            if not hdr.is_absolute() or label not in CLASSES or region < 1 or (hdr,row,col) in seen:
                raise ValueError(f'{path.name} 第 {index+2} 行来源、类别、区域或重复中心有误')
            seen.add((hdr,row,col))
            grouped[hdr].append((index,row,col,region,label))
    if not seen:
        raise ValueError(f'{path.name} 没有中心记录')
    return grouped


def extract_image(pair, rows):
    hdr, img, annotation = (Path(pair[k]) for k in ('hdr','img','annotation'))
    before = img.stat()
    dataset = open_envi(hdr, img, raw=True)
    doc = json.loads(annotation.read_text(encoding='utf-8-sig'))
    signature = doc['source_signature']
    if (Path(doc['source_hdr']) != hdr or Path(signature['img_path']) != img
            or before.st_size != signature['img_bytes'] or not signature.get('hdr_sha256')):
        raise ValueError(f'标注与当前原图不匹配：{hdr.name}')
    region, truth = roi_maps(annotation, dataset.shape[:2], CLASSES, sha256(hdr))
    unit = str(dataset.metadata.get('wavelength units','')).lower()
    if unit not in ('nm','nanometers','nanometres'):
        raise ValueError(f'{hdr.name} 缺少本取谱方案要求的 nm 波长声明')
    weights = mapping_weights(dataset.wavelengths, AXIS, 5., 5.)
    used = weights.sum(axis=1) > 0
    cube = dataset.to_numpy()
    index, rr, cc, rid, label = np.asarray(rows, dtype=np.int64).T
    if ((rr < 1) | (cc < 1) | (rr+1 >= region.shape[0]) | (cc+1 >= region.shape[1])).any():
        raise ValueError(f'{hdr.name} 有中心的 3×3 邻域超出图像')
    if not np.array_equal(truth[rr,cc], label):
        raise ValueError(f'{hdr.name} 中心清单类别与 ROI 标签不一致')
    result = np.empty((len(rr),len(AXIS)), np.float32)
    for start in range(0,len(rr),512):
        sl = slice(start,start+512)
        total = np.zeros((len(rr[sl]),len(AXIS)), np.float64)
        for dr in (-1,0,1):
            for dc in (-1,0,1):
                r,c = rr[sl]+dr,cc[sl]+dc
                raw = np.asarray(cube[r,c,:], dtype=np.float64)
                mapped = (raw / float(dataset.metadata['scale_factor'])) @ weights
                ok = (region[r,c] == rid[sl]) & quality_mask(mapped,raw[:,used],QUALITY)
                if not ok.all():
                    i = start + int(np.flatnonzero(~ok)[0])
                    raise ValueError(f'{hdr.name} 中心 ({rr[i]}, {cc[i]}) 的邻域跨区或未通过质量检查')
                total += mapped
        result[sl] = total / 9
    after = img.stat()
    if (after.st_size,after.st_mtime_ns) != (before.st_size,before.st_mtime_ns):
        raise ValueError(f'读取过程中 IMG 发生变化：{hdr.name}')
    return index, result, truth[rr,cc]


def replay(report, release, output_root, check=lambda: None):
    if report['issues']:
        raise ValueError('配对预览存在异常，请先处理并重新预览')
    release = release.resolve()
    manifest = json.loads((release/'版本清单.json').read_text(encoding='utf-8-sig'))
    if manifest['version'] != VERSION:
        raise ValueError('当前支持含冻结五分类中心清单与参考 NPZ 的发布目录')
    hashes = manifest['files']
    guard.mkdir(output_root, parents=True, exist_ok=True)
    run = output_root / str(uuid4())
    stats = {}
    with guard.temporary_directory(dir=output_root, prefix='partial-') as temp, threadpool_limits(limits=2):
        # Use a child so the staging parent survives the final atomic rename.
        stage = Path(temp) / 'output'
        guard.mkdir(stage)
        for role, ref_name in (('训练','训练光谱.npz'),('测试','测试V2光谱.npz')):
            csv_name = role+'中心.csv'
            grouped = centers_by_source(frozen_file(release,csv_name,hashes))
            pairs = {Path(p['hdr']):p for p in report['pairs'] if p['role']==role}
            if grouped.keys() != pairs.keys():
                raise ValueError(f'{role}中心清单与已配对原图集合不一致，请重新核对来源')
            n = sum(map(len,grouped.values()))
            spectra = np.empty((n,len(AXIS)),np.float32)
            labels = np.empty(n,np.int64)
            for hdr, rows in grouped.items():
                check()
                pair = pairs[hdr]
                annotation = Path(pair['annotation'])
                frozen_file(release,annotation.relative_to(release).as_posix(),hashes)
                idx, spectra_rows, truth = extract_image(pair,rows)
                spectra[idx],labels[idx] = spectra_rows,truth
            ref_path = frozen_file(release,ref_name,hashes)
            with np.load(ref_path,allow_pickle=False) as ref:
                expected = ref['X3']
                if (not np.array_equal(ref['wavelengths_nm'],AXIS) or
                        not np.array_equal(ref['y'],labels) or expected.shape != spectra.shape):
                    raise ValueError(f'{role}的波长轴、标签顺序或矩阵尺寸与参考不一致')
                different = int(np.count_nonzero(np.any(spectra != expected, axis=1)))
                max_error = float(np.max(np.abs(spectra.astype(float) - expected)))
                if different:
                    raise ValueError(f'{role}共 {different}/{n} 条 X3 与冻结值不同，最大绝对差 {max_error:.9g}')
            save_arrays(stage/ref_name,X3=spectra,y=labels,wavelengths_nm=AXIS)
            stats[role] = dict(images=len(pairs), centers=n, exact=n, max_abs_error=max_error,
                               centers_sha256=hashes[csv_name], reference_sha256=hashes[ref_name],
                               output_sha256=sha256(stage/ref_name))
        check()
        write_json(stage/'核验.json',dict(version=VERSION, release=str(release), classes=CLASSES,
                   neighborhood=3, wavelength_nm=AXIS.tolist(), mapping_window_nm=5, nearest_tolerance_nm=5,
                   quality=QUALITY.model_dump(), splits=stats, sources=report['pairs']))
        guard.replace(stage,run)
    return run,stats
