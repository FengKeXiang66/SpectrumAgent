"""Read-only inventory of explicitly assigned ENVI and ROI directories."""
from collections import Counter, defaultdict
import csv
import json
from os.path import normpath
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

from spectrumagent.data import DataError
from spectrumagent.data.readers import open_envi
from .inputs import roi_maps, sha256

ROLES = ('训练', '测试')
DIRECTORY_KEYS = [role + kind for role in ROLES for kind in ('原图', '标注')]
CAPABILITY = ('本机实验流程支持已有 ENVI 原图和外部 ROI 标注 JSON，也支持已整理好的训练和测试 NPZ。'
              '原图与标注优先按 source_hdr 只读配对。标准 LabelMe 标注或路径迁移时可在指定原图目录用 imagePath 匹配。'
              '核对 HDR、IMG 和 shapes 中的区域与材质标签，列出缺失和异常。'
              '可分轮提供目录和用途。已有训练与测试划分时可显式配对，未划分时可先按已确认的实物、批次或原图分组划分。'
              '后续可按需进行波长对齐、从标注区域取谱，仅用训练集自动比较预处理与模型参数（Study），审阅并确认显式实验训练和测试方案，'
              '再用归档模型做 ENVI 整图或 NPZ 批量推理。')
ACCEPT = re.compile(r'(?:对[的，,、 ]*|好[的，,、 ]*)?(?:按这个关系检查|先检查(?:一下)?|先看看|开始配对|检查一下|可以检查|确认配对|运行只读配对预览)|对|好|可以')
EDIT = '调整目录用途'
APPROVE = '按这个关系检查'
DISMISS = re.compile(r'(?:取消|停止|不用|先不)(?:本次)?(?:配对|检查|预览)|算了')
SOURCE = re.compile(r'(?<![A-Za-z0-9])S\d+(?![A-Za-z0-9])', re.I)
ROLE_FIELD = re.compile(r'(?:(训练|测试)(?:集)?(?:的|侧)?\s*(ENVI(?:原图|数据)?|原始数据|原图|数据|图像|标注|JSON)|'
                        r'(对应(?:的)?(?:JSON\s*)?标注|标注)|来源与标注清单|来源清单)', re.I)


def external_annotations(text):
    return bool(re.search(r'JSON', text, re.I) and re.search(r'标注|选区', text)
                and re.search(r'ENVI|高光谱|原图|目录|文件夹|已有|已经有', text, re.I))


def mentioned_roles(text):
    """Associate session source references with their nearest directory label."""
    fields = defaultdict(list)
    role = key = None
    cursor = 0
    for ref in SOURCE.finditer(text):
        for label in ROLE_FIELD.finditer(text[cursor:ref.start()]):
            if label[1]:
                role = label[1]
                key = role + ('标注' if label[2].lower() in ('标注','json') else '原图')
            elif label[3]:
                key = role + '标注' if role else None
            else:
                key = '清单'
        fields[key].append(ref[0].upper())
        cursor = ref.end()
    return fields
PAGE = re.compile(r'(?:查看)?(配对明细|未配对原图|配对异常)(?:\s*第?\s*(\d{1,6})\s*页?)?[。！!\s]*')
REPLAY = re.compile(r'^\s*(?:请)?(?:核验中心取谱|按中心清单(?:重新)?取谱)(?=$|[\s，,：:；;。！!“"])')
TRAIN_COMMAND = '用本次配对结果新建训练方案'
PREPARE_REPLAY = '用本次取谱结果新建训练方案'
HELP = '请在同一条消息中列出：训练原图：路径；测试原图：路径；训练标注：路径；测试标注：路径。多目录用顿号分隔，含空格的路径请加双引号。可选：来源清单：CSV路径。'


def requested(content, path_pattern):
    text = path_pattern.sub(' ', content)
    return bool(content.strip(' 。！!') == PREPARE_REPLAY or REPLAY.match(content) or PAGE.fullmatch(text.strip()) or '配对预览' in text or
                (re.search(r'(?:训练|测试)(?:集)?(?:的)?标注(?:目录|文件夹)', text)
                 and path_pattern.search(content)))


def directories(content, path_pattern):
    paths = {}
    def bind(match):
        ref = f'S{len(paths)+1}'
        paths[ref] = Path(match['quoted'] or match['bare']).resolve()
        return ' '+ref+' '
    fields = mentioned_roles(path_pattern.sub(bind,content))
    if None in fields or any(ref not in paths for refs in fields.values() for ref in refs):
        raise ValueError(HELP)
    return validate_directories({key:[paths[ref] for ref in refs] for key,refs in fields.items()})


def validate_directories(fields):
    if len(fields.get('清单',[])) > 1 or any(not fields.get(key) for key in DIRECTORY_KEYS):
        raise ValueError(HELP)
    for key, group in fields.items():
        for path in group:
            if not (path.is_file() and path.suffix.lower() == '.csv' if key == '清单' else path.is_dir()):
                raise ValueError(f'{key}路径不可用：{path}')
    return fields


def relative_key(parent, parts):
    """Resolve LabelMe's relative references lexically, within a scan root."""
    result = list(parent)
    for part in parts:
        if part == '..':
            if not result:
                return None
            result.pop()
        else:
            result.append(part.casefold())
    return tuple(result)


def resolve_annotation_header(doc, annotation, annotation_roots, image_roots, headers, by_relative, by_name):
    source = doc.get('source_hdr')
    if source is not None and source != '':
        if not isinstance(source, str) or not (PureWindowsPath(source).is_absolute() or PurePosixPath(source).is_absolute()):
            raise ValueError('source_hdr 须为绝对路径')
        native = Path(normpath(source))
        if native.is_absolute():
            if native in headers:
                return native, False
            if any(native.is_relative_to(root) for root in image_roots):
                resolved = native.resolve()
                if resolved in headers:
                    return resolved, False

    # imagePath is a matching hint only. Never open the preview image or an
    # HDR outside the scanned roots, even when the JSON contains an old drive.
    image_path = doc.get('imagePath')
    if not isinstance(image_path,str) or not image_path.strip():
        raise ValueError('来源缺失：请提供可匹配的 source_hdr，或用 LabelMe 的 imagePath 回退配对')
    image = PureWindowsPath(image_path)
    if image.suffix.lower() not in {'.png','.jpg','.jpeg','.tif','.tiff','.hdr'}:
        raise ValueError('imagePath 须指向 PNG、JPEG、TIFF 或 HDR 文件')
    reference = image.with_suffix('.hdr')

    def choose(matches):
        if len(matches) > 1:
            raise ValueError('原图配对歧义：' + '、'.join(map(str,sorted(matches))))
        return next(iter(matches),None)

    if not reference.anchor:
        # LabelMe stores imagePath relative to the JSON directory.
        mirrored = set()
        for root in annotation_roots:
            if annotation.is_relative_to(root):
                parent = tuple(part.casefold() for part in annotation.parent.relative_to(root).parts)
                mirrored.update(by_relative.get(relative_key(parent,reference.parts),()))
        matched = choose(mirrored) or choose(by_relative.get(relative_key((),reference.parts),()))
        if matched:
            return matched, True
    matched = choose(by_name.get(reference.name.casefold(),()))
    if matched:
        return matched, True
    raise ValueError('来源缺失：未在对应原图目录中找到 imagePath 匹配的 HDR')


def inventory(fields, roles=ROLES, exclusions=None):
    report = {'pairs': [], 'issues': [], 'unused': [], 'roots': {}, 'annotations': {}, 'manifest': False, 'excluded': []}
    owners = defaultdict(set)
    relative_headers = {role:defaultdict(set) for role in roles}
    named_headers = {role:defaultdict(set) for role in roles}
    excluded = {}
    annotations = []
    image_roots = [root for role in roles for root in fields[role+'原图']]
    for role in roles:
        report['roots'][role] = [str(p) for p in fields[role+'原图']]
        for root in fields[role+'原图']:
            for p in root.rglob('*.hdr'):
                if p.is_file() and p.resolve().is_relative_to(root):
                    resolved = p.resolve()
                    relative_headers[role][tuple(part.casefold() for part in p.relative_to(root).parts)].add(resolved)
                    named_headers[role][p.name.casefold()].add(resolved)
                    reason = exclusions.reason(p, root) if exclusions else ''
                    if reason:
                        excluded[resolved] = {'file':str(resolved), 'relative_file':p.relative_to(root).as_posix(), 'reason':reason}
                    else:
                        owners[resolved].add(role)
        files = sorted({p.resolve() for root in fields[role+'标注'] for p in root.rglob('*.json')
                        if p.is_file() and p.resolve().is_relative_to(root)})
        report['annotations'][role] = len(files)
        if not files:
            report['issues'].append(f'{role}标注目录未找到 JSON')
        annotations.extend((role, p) for p in files)

    candidates = defaultdict(list)
    referenced = set()
    headers = owners.keys() | excluded.keys()
    for role, annotation in annotations:
        try:
            doc = json.loads(annotation.read_text(encoding='utf-8-sig'))
            if not isinstance(doc,dict):
                raise ValueError('标注 JSON 须为对象')
            hdr, fallback = resolve_annotation_header(doc, annotation, fields[role+'标注'], image_roots,
                                                      headers, relative_headers[role], named_headers[role])
            if hdr in excluded:
                continue
            referenced.add(hdr)
            if owners.get(hdr) != {role}:
                raise ValueError(f'来源缺失、目录用途冲突或不在{role}原图目录：{hdr}')
            candidates[hdr].append((role, annotation, doc, fallback))
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
        role, annotation, doc, fallback = entries[0]
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
            if not isinstance(sig,dict):
                raise ValueError('source_signature 须为对象')
            if fallback and 'source_signature' in doc and (not sig.get('hdr_sha256') or sig.get('img_bytes') is None):
                raise ValueError('回退配对的来源签名需要 hdr_sha256 和 img_bytes')
            if not fallback and sig.get('img_path') and Path(sig['img_path']).resolve() != img:
                raise ValueError('IMG 路径与标注签名不一致')
            stat = img.stat()
            if sig.get('img_bytes') is not None:
                size = sig['img_bytes']
                if not (type(size) is int or isinstance(size,str) and size.isdecimal()) or stat.st_size != int(size):
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
    report['excluded'] = [item for _,item in sorted(excluded.items())]
    return report


def can_train(report):
    return not report['issues'] and set(ROLES) == {row['role'] for row in report['pairs']}


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
    lines.append('本次只生成预览，可在查看器核对配对明细、未配对原图和异常。')
    if can_train(report):
        lines.append(f'可发送“{TRAIN_COMMAND}”，沿用以上训练／测试用途和标注创建草稿。')
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
