"""Read-only inventory of explicitly assigned ENVI and ROI directories."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re

from spectrumagent.data import DataError
from spectrumagent.data.readers import open_envi
from .inputs import roi_maps, sha256

ROLES = ('训练', '测试')
PAGE = re.compile(r'(?:查看)?(配对明细|未配对原图|配对异常)(?:\s*第?\s*(\d{1,6})\s*页?)?[。！!\s]*')
FIELD = re.compile(r'(训练|测试)(?:集)?(?:的)?(原始数据|原图|数据|标注)(?:目录|文件夹)?|来源与标注清单|来源清单')
REPLAY = re.compile(r'^\s*(?:请)?(?:核验中心取谱|按中心清单(?:重新)?取谱)(?=$|[\s，,：:；;。！!“"])')
PREPARE_REPLAY = '用本次取谱结果新建训练方案'
HELP = '请在同一条消息中列出：训练原图：路径；测试原图：路径；训练标注：路径；测试标注：路径。多目录用顿号分隔，含空格的路径请加双引号。可选：来源清单：CSV路径。'


def requested(content, path_pattern):
    text = path_pattern.sub(' ', content)
    return bool(content.strip(' 。！!') == PREPARE_REPLAY or REPLAY.match(content) or PAGE.fullmatch(text.strip()) or '配对预览' in text or
                (re.search(r'(?:训练|测试)(?:集)?(?:的)?标注(?:目录|文件夹)', text)
                 and path_pattern.search(content)))


def directories(content, path_pattern):
    paths = list(path_pattern.finditer(content))
    text = path_pattern.sub(lambda m: ' ' * len(m[0]), content)
    matches = list(FIELD.finditer(text))
    fields = defaultdict(list)
    used = 0
    for i, match in enumerate(matches):
        key = '清单' if not match[1] else match[1] + ('标注' if match[2] == '标注' else '原图')
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        group = [Path(p['quoted'] or p['bare']).resolve() for p in paths if match.end() <= p.start() < end]
        if not group:
            raise ValueError(HELP)
        used += len(group)
        fields[key].extend(group)
    if (used != len(paths) or len(fields['清单']) > 1 or
            any(not fields[role + kind] for role in ROLES for kind in ('标注', '原图'))):
        raise ValueError(HELP)
    for key, group in fields.items():
        for path in group:
            if not (path.is_file() and path.suffix.lower() == '.csv' if key == '清单' else path.is_dir()):
                raise ValueError(f'{key}路径不可用：{path}')
    return fields


def inventory(fields, roles=ROLES):
    report = {'pairs': [], 'issues': [], 'unused': [], 'roots': {}, 'annotations': {}, 'manifest': False}
    owners = defaultdict(set)
    annotations = []
    for role in roles:
        report['roots'][role] = [str(p) for p in fields[role+'原图']]
        for root in fields[role+'原图']:
            for p in root.rglob('*.hdr'):
                if p.is_file() and p.resolve().is_relative_to(root):
                    owners[p.resolve()].add(role)
        files = sorted({p.resolve() for root in fields[role+'标注'] for p in root.rglob('*.json')
                        if p.is_file() and p.resolve().is_relative_to(root)})
        report['annotations'][role] = len(files)
        if not files:
            report['issues'].append(f'{role}标注目录未找到 JSON')
        annotations.extend((role, p) for p in files)

    candidates = defaultdict(list)
    referenced = set()
    for role, annotation in annotations:
        try:
            doc = json.loads(annotation.read_text(encoding='utf-8-sig'))
            hdr = Path(doc['source_hdr'])
            if not hdr.is_absolute():
                raise ValueError('source_hdr 须为绝对路径')
            hdr = hdr.resolve()
            referenced.add(hdr)
            if owners.get(hdr) != {role}:
                raise ValueError(f'来源缺失、目录用途冲突或不在{role}原图目录：{hdr}')
            candidates[hdr].append((role, annotation, doc))
        except (OSError, ValueError, KeyError, TypeError) as error:
            report['issues'].append(f'{role} · {annotation} · {error}')

    manifest = None
    if fields.get('清单'):
        path = fields['清单'][0]
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if not {'split','source','annotation'} <= set(reader.fieldnames or []):
                raise ValueError('来源清单须包含 split、source、annotation 三列')
            manifest = set()
            for row in reader:
                role = {'测试V2':'测试','训练':'训练','测试':'测试'}.get(row['split'])
                if not role or not row['annotation'] or not Path(row['source']).is_absolute():
                    raise ValueError('清单含无法识别的用途、来源或标注')
                manifest.add((role, Path(row['source']).resolve(), (path.parent / row['annotation']).resolve()))
        report['manifest'] = True
        report['manifest_path'] = str(path)

    checked = set()
    for hdr, entries in sorted(candidates.items()):
        if len(entries) != 1:
            report['issues'].append(f'重复绑定 {hdr}：' + '、'.join(str(e[1]) for e in entries))
            continue
        role, annotation, doc = entries[0]
        try:
            key = role, hdr, annotation
            if manifest is not None and key not in manifest:
                raise ValueError('用途、原图或标注与来源清单不一致')
            img = hdr.with_suffix('.img').resolve()
            if img.parent != hdr.parent or not img.is_file():
                raise ValueError('缺少同目录的配套 IMG')
            with img.open('rb') as stream:
                if not stream.read(1):
                    raise ValueError('IMG 大小为零')
            dataset = open_envi(hdr, img, raw=True)
            sig = doc.get('source_signature', {})
            if sig.get('img_path') and Path(sig['img_path']).resolve() != img:
                raise ValueError('IMG 路径与标注签名不一致')
            if sig.get('img_bytes') is not None and img.stat().st_size != int(sig['img_bytes']):
                raise ValueError('IMG 大小与标注签名不一致')
            labels = sorted({shape['label'] for shape in doc['shapes']})
            if not labels or not all(isinstance(label, str) and label.strip() for label in labels):
                raise ValueError('标注缺少材质名称')
            header_hash = sha256(hdr)
            roi_maps(annotation, dataset.shape[:2], dict(enumerate(labels, 1)), header_hash)
            pair = dict(role=role, hdr=str(hdr), img=str(img), annotation=str(annotation),
                        labels=labels, regions=len(doc['shapes']))
            if role == '待划分':
                split = str(doc.get('dataset_split') or '').lower()
                if re.search(r'(?:train|test|valid|infer|训练|测试|验证|推理)', split) or any(
                        part.lower() == '7t' for part in hdr.parts):
                    raise ValueError('该来源已有明确用途或属于 7t 推理数据，请使用未划分数据')
                meta = {}
                for key in ('sample_id', 'batch'):
                    value = doc.get(key)
                    if value is not None and (type(value) not in (str, int) or not str(value).strip()):
                        raise ValueError(f'{key} 须为非空标识')
                    meta[key] = str(value).strip() if value is not None else None
                stat = img.stat()
                pair.update(meta, region_counts=dict(Counter(s['label'] for s in doc['shapes'])),
                    hdr_sha256=header_hash, annotation_sha256=sha256(annotation),
                    img_bytes=stat.st_size, img_mtime_ns=stat.st_mtime_ns)
            report['pairs'].append(pair)
            checked.add(key)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, DataError) as error:
            detail = error.payload.detail if isinstance(error, DataError) else str(error)
            report['issues'].append(f'{role} · {annotation} · {hdr} · {detail}')
    if manifest is not None:
        for role, hdr, annotation in sorted(manifest-checked):
            report['issues'].append(f'清单记录未通过配对：{role} · {hdr} · {annotation}')
    for hdr in sorted(owners):
        if len(owners[hdr]) > 1:
            report['issues'].append(f'原图同时属于训练和测试目录：{hdr}')
        if hdr not in referenced:
            report['unused'].append(str(hdr))
    return report


def overview(report):
    lines = ['ENVI 原图与标注配对预览']
    for role in ROLES:
        rows = [p for p in report['pairs'] if p['role'] == role]
        counts = Counter(label for p in rows for label in p['labels'])
        lines.append(f"{role}：{report['annotations'][role]} 份 JSON，成功配对 {len(rows)} 幅原图。")
        lines.append('各目录配对图数：' + '；'.join(f'{root}（{sum(Path(p["hdr"]).is_relative_to(root) for p in rows)}）'
                                              for root in report['roots'][role]))
        lines.append('含各材质的图数：' + ('，'.join(f'{label} {count}' for label,count in sorted(counts.items())) or '无'))
    lines.append(f"未被标注引用的原图 {len(report['unused'])} 幅；异常记录 {len(report['issues'])} 条。")
    if report['manifest']:
        lines.append('已按来源清单的用途、原图路径和标注路径逐项核对。')
    if report['issues']:
        lines.append(report['issues'][0])
    lines.append('发送“配对明细 第1页”“未配对原图 第1页”或“配对异常 第1页”逐项查看。本次只生成预览。')
    if report.get('manifest_path') and not report['issues'] and (Path(report['manifest_path']).parent / '版本清单.json').is_file():
        lines.append('已有冻结中心和参考光谱时，可发送“核验中心取谱”，重新提取并逐条比较。')
    return '\n'.join(lines)


def details(report, kind, page):
    items = report[{'配对明细':'pairs','未配对原图':'unused','配对异常':'issues'}[kind]]
    pages = max(1, (len(items)+9)//10)
    if not 1 <= page <= pages:
        return f'{kind}共 {pages} 页，请选择有效页码。'
    lines = [f'{kind} · 第 {page}/{pages} 页 · 共 {len(items)} 条']
    for item in items[10*(page-1):10*page]:
        if kind == '配对明细':
            lines.append(f"{item['role']} · {', '.join(item['labels'])} · {item['regions']} 个区域\n"
                         f"{item['hdr']}\n↳ {item['annotation']}")
        else:
            lines.append(item)
    return '\n'.join(lines)
