"""Offline comparison reports, bound to the archived inference and its artifacts."""
from collections import Counter, defaultdict
from hashlib import sha256
from html import escape
import json
from os import scandir
from pathlib import Path
from stat import FILE_ATTRIBUTE_REPARSE_POINT, S_ISDIR, S_ISREG
from urllib.parse import quote

from spectrumagent.data import DataError
from spectrumagent.storage import guard as storage
from .service import read_json, write_json

REPORT = 'report.html'
MANIFEST = 'report-manifest.json'
REASONS = {'brightness':'低亮度', 'side_edges':'左右边缘', 'quality_or_neighborhood':'质量或邻域',
           'image_boundary':'图像外边界'}


def archive_parts(name, *, companions=False):
    parts = tuple(name.split('/'))
    valid = all(part not in ('', '.', '..') and not any(c in part for c in '\\:\0') for part in parts)
    nested = companions and len(parts)==3 and parts[0]=='companions' and parts[1].isdecimal()
    if not valid or (len(parts)!=1 and not nested):
        raise DataError('INFERENCE_ARTIFACT_CHANGED', '推理产物路径不合法')
    return parts


def archive_path(folder, name, *, companions=False):
    path = folder.joinpath(*archive_parts(name,companions=companions))
    if path.resolve() != path:
        raise DataError('INFERENCE_ARTIFACT_CHANGED', '推理产物路径发生变化')
    return path


def export_paths(folder, names):
    # Read each directory once. Windows exposes ordinary entries and reparse
    # attributes in the scan, so validation needs no per-file realpath calls.
    listings = {}
    for name in names:
        parts = archive_parts(name,companions=True)
        try:
            for depth, part in enumerate(parts):
                prefix = parts[:depth]
                if prefix not in listings:
                    with scandir(folder.joinpath(*prefix)) as entries:
                        listings[prefix] = {entry.name:entry for entry in entries}
                info = listings[prefix][part].stat(follow_symlinks=False)
                expected = S_ISREG if depth==len(parts)-1 else S_ISDIR
                if not expected(info.st_mode) or getattr(info,'st_file_attributes',0)&FILE_ATTRIBUTE_REPARSE_POINT:
                    raise DataError('INFERENCE_ARTIFACT_CHANGED', '推理产物路径发生变化')
        except (OSError,KeyError) as error:
            raise DataError('INFERENCE_ARTIFACT_CHANGED', '推理产物缺失或校验失败') from error
        yield name, folder.joinpath(*parts)


def verify_digest(digest, size, item):
    if digest != item['sha256'] or ('bytes' in item and size != item['bytes']):
        raise DataError('INFERENCE_ARTIFACT_CHANGED', '推理产物缺失或校验失败')


def verified_json(folder, result, name):
    try:
        data = archive_path(folder,name).read_bytes()
        verify_digest(sha256(data).hexdigest(),len(data),result['artifacts'][name])
        return json.loads(data)
    except (OSError, KeyError, ValueError, TypeError) as error:
        raise DataError('INFERENCE_ARTIFACT_CHANGED', '推理归档元数据缺失或校验失败') from error


def relative_paths(files, declared):
    roots = tuple(Path(path).resolve() for path in declared)
    return [
        next(((Path(root.name)/path.relative_to(root) if len(roots)>1 else path.relative_to(root)).as_posix()
              for root in roots if path != root and path.is_relative_to(root)),path.name)
        for path in map(Path,files)
    ]


def archived_inputs(folder, result):
    config = verified_json(folder,result,'config.json')
    sources = verified_json(folder,result,'sources.json')
    review = verified_json(folder,result,'review.json') if 'review.json' in result['artifacts'] else {}
    paths = review.get('files') or [name for name in sources if Path(name).suffix.lower()=='.hdr']
    # The original ordered review is authoritative. The source table is a
    # fallback for older archives and must agree with the recorded basenames.
    if len(paths)!=len(result['files']) or any(
        path not in sources or not Path(path).is_absolute() or Path(path).suffix.lower()!='.hdr'
        or Path(path).name!=row['name'] for row,path in zip(result['files'],paths)
    ):
        return config, []
    return config, paths


def result_digest(result):
    return sha256(json.dumps(result,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def report_cache(folder, result):
    path = archive_path(folder,MANIFEST)
    if not path.is_file():
        return None
    try:
        cache = read_json(path)
        if cache['result_sha256'] != result_digest(result) or REPORT not in cache['artifacts']:
            raise ValueError()
        for name in cache['artifacts']:
            if name!=REPORT and not name.startswith('companions/'):
                raise ValueError()
            archive_parts(name,companions=True)
        return cache['artifacts']
    except (OSError, KeyError, ValueError, TypeError) as error:
        raise DataError('INFERENCE_ARTIFACT_CHANGED', '归档对比报告的清单校验失败') from error


def companion_artifacts(folder, files, rows, check):
    catalog = {}
    artifacts, by_file = {}, {}
    for row, value in zip(rows,files):
        if check:
            check()
        hdr = Path(value)
        if hdr.parent not in catalog:
            try:
                catalog[hdr.parent] = sorted(
                    (path for path in hdr.parent.iterdir()
                     if path.suffix.lower() in ('.png','.jpg','.jpeg') and path.is_file()),
                    key=lambda path:path.name.casefold(),
                )
            except OSError:
                catalog[hdr.parent] = []
        stem = hdr.stem.casefold()
        matches = []
        for path in catalog[hdr.parent]:
            suffix, sibling = path.suffix.lower(), path.stem.casefold()
            if sibling != stem and (suffix!='.png' or not sibling.startswith((stem+'-',stem+'_'))):
                continue
            # Original folders are read-only, including when a sibling is a link.
            if path.resolve()!=path:
                continue
            index = row['file_index']
            name = f'companions/{index}/{path.name}'
            destination = archive_path(folder,name,companions=True)
            try:
                source = path.open('rb')
            except OSError:
                continue
            with source:
                block = source.read(1024*1024)
                signature = b'\x89PNG\r\n\x1a\n' if suffix=='.png' else b'\xff\xd8\xff'
                if not block.startswith(signature):
                    continue
                if not destination.parent.is_dir():
                    storage.mkdir(destination.parent,parents=True,exist_ok=True)
                digest, size = sha256(), 0
                with storage.resolve_write(destination,kind='INFERENCE_COMPANION').open('wb') as output:
                    while block:
                        if check:
                            check()
                        output.write(block)
                        digest.update(block)
                        size += len(block)
                        block = source.read(1024*1024)
            artifacts[name] = {'sha256':digest.hexdigest(),'bytes':size}
            matches.append((suffix,name,path.name))
        by_file[row['file_index']] = matches
    return artifacts, by_file


def majority(row, classes):
    # Lower numeric class ID breaks ties, as in the desktop viewer.
    labels = sorted(classes,key=int)
    winner = max(labels,key=lambda label:row['counts'].get(label,0),default=None)
    return winner if winner is not None and row['counts'].get(winner,0)>0 else None


def render_report(result, config, companions):
    classes = result['classes']
    counts, reasons = Counter(), Counter()
    directories = defaultdict(list)
    for row in result['files']:
        counts.update(row['counts'])
        reasons.update(row.get('exclusion_counts',{}))
        path = row.get('relative_path') or row['name']
        directory, _, _ = path.rpartition('/')
        directories[directory or '根目录'].append((row,path,majority(row,classes)))

    def table(head, rows):
        headings = ''.join(f'<th scope="col">{escape(str(cell))}</th>' for cell in head)
        content = ''.join('<tr>'+''.join(f'<td>{escape(str(cell))}</td>' for cell in row)+'</tr>' for row in rows)
        return f'<div class="table"><table><thead><tr>{headings}</tr></thead><tbody>{content}</tbody></table></div>'

    def preview(name, caption):
        url = quote(name,safe='/')
        return (f'<figure><a href="{url}" target="_blank" rel="noopener"><img loading="lazy" src="{url}" '
                f'alt="{escape(caption)}"></a><figcaption>{escape(caption)}</figcaption></figure>')

    classified = sum(row['classified'] for row in result['files'])
    excluded = sum(row['excluded'] for row in result['files'])
    columns = sorted(classes,key=int)
    votes = Counter(winner for rows in directories.values() for _,_,winner in rows)
    config_view = {**config, 'input':{key:value for key,value in config.get('input',{}).items() if key!='paths'}}
    content = [f'<h1>ENVI 分类对比报告</h1><p>模型 {escape(result["model_id"])} · 任务 {escape(result["run_id"])}</p>',
               f'<p>模型 SHA-256 <code>{escape(result["model_sha256"])}</code></p>',
               '<p>预测图和多数票用于查看结果。无真值标签。像元百分比的分母为全部已分类像元。</p>',
               f'<details><summary>运行配置</summary><pre>{escape(json.dumps(config_view,ensure_ascii=False,indent=2))}</pre></details>',
               '<h2>批次汇总</h2>',
               table(['纳入推理的文件','按范围排除的文件','总像元','已分类','未分类'],
                     [[len(result['files']),len(result.get('excluded_files',[])),classified+excluded,classified,excluded]]),
               table(['类别','像元数','已分类像元占比','多数票文件数'],
                     [(classes[label],counts[label],f'{counts[label]/classified:.2%}' if classified else '—',votes[label]) for label in columns]
                     + [('无已分类像元','—','—',votes[None])]),
               table(['未分类原因','像元数'],[(REASONS.get(key,key),count) for key,count in reasons.items()]),
               '<h2>按目录统计的多数票</h2>',
               table(['目录','文件数',*[classes[label] for label in columns],'无已分类像元'],
                     [[directory,len(rows),*[sum(winner==label for _,_,winner in rows) for label in columns],
                       sum(winner is None for _,_,winner in rows)] for directory,rows in directories.items()]),
               '<h2>本模型图例</h2>']
    legend = dict(result.get('background_colors') or {})
    labels = [(classes[label],result.get('colors',{}).get(label,'')) for label in columns]
    labels += [('低亮度筛除',legend.get('brightness','#000000')),('边缘或无效像元',legend.get('other','#e0e0e0'))]
    for label, color in labels:
        color = color if len(color)==7 and color[0]=='#' and all(c in '0123456789abcdefABCDEF' for c in color[1:]) else '#999999'
        content.append(f'<span class="legend"><i style="background:{color}"></i>{escape(label)}</span>')

    content.append('<div class="toolbar"><input id="query" aria-label="搜索目录、文件名或多数票" placeholder="搜索目录、文件名或多数票">'
                   '<select id="vote" aria-label="筛选多数票"><option value="">全部多数票</option>'
                   + ''.join(f'<option value="{label}">{escape(classes[label])}</option>' for label in columns)
                   + '<option value="none">无已分类像元</option></select>'
                   '<button id="expand">展开全部</button><button id="collapse">收起全部</button>'
                   '<button id="tiles" aria-pressed="false">平铺</button><output id="shown"></output></div><main>')
    for directory, rows in directories.items():
        content.append(f'<details class="group"><summary>{escape(directory)} · {len(rows)} 幅</summary><div class="cards">')
        for row,path,winner in rows:
            index = row['file_index']
            images = companions.get(index,[])
            vote_name = classes[winner] if winner else '无已分类像元'
            content.append(f'<article data-path="{escape(path)}" data-vote="{winner or "none"}" data-class="{escape(vote_name)}">'
                           f'<h3>{escape(row["name"])}</h3><p>{escape(path)} · 多数票 {escape(vote_name)} · '
                           f'已分类 {row["classified"]} · 未分类 {row["excluded"]}</p><div class="images"><section><h4>输入图</h4>')
            if f'{index}_input.png' in result['artifacts']:
                content.append(preview(f'{index}_input.png','输入伪彩'))
            else:
                content.append('<p>此归档没有输入伪彩。</p>')
            content.extend(preview(name,'原目录同名照片 · '+caption) for suffix,name,caption in images if suffix!='.png')
            content.append('</section><section><h4>原目录配套染色图</h4>')
            drawings = [preview(name,caption) for suffix,name,caption in images if suffix=='.png']
            content.extend(drawings or ['<p>原目录未找到配套染色图。</p>'])
            if drawings:
                content.append('<p>保留原图配色，类别颜色含义以原流程为准。</p>')
            content.append('</section><section><h4>本模型推理</h4>')
            if f'{index}.png' in result['artifacts']:
                content.append(preview(f'{index}.png','逐像元分类'))
            else:
                content.append('<p>此归档没有分类预览。</p>')
            excluded_note = ' · '.join(f'{REASONS.get(key,key)} {value}' for key,value in row.get('exclusion_counts',{}).items())
            content.append(f'</section></div><p>{escape(excluded_note)}</p></article>')
        content.append('</div></details>')
    return PAGE_HEAD + '\n'.join(content) + '</main>' + PAGE_SCRIPT + '</body></html>'


PAGE_HEAD = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src file: 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'">
<title>ENVI 分类对比报告</title><style>
*{box-sizing:border-box}body{max-width:1440px;margin:auto;padding:20px;background:#f5f8fa;color:#183443;font:15px/1.5 system-ui,sans-serif}
[hidden]{display:none!important}h1,h2,h3,h4{margin:1em 0 .4em}code,pre,p,summary{overflow-wrap:anywhere}pre{white-space:pre-wrap}
.table{overflow:auto;margin:10px 0}table{border-collapse:collapse;background:white;width:100%}th,td{padding:7px 10px;text-align:left;border:1px solid #d6e1e6}
.toolbar{position:sticky;top:0;z-index:2;background:#eaf3f6;border:1px solid #d6e1e6;padding:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:14px 0}
input,select,button{font:inherit;padding:5px 8px}button,summary{cursor:pointer}.legend{display:inline-flex;align-items:center;gap:4px;margin-right:12px}
.legend i{width:14px;height:14px;border:1px solid #566d76}.group{padding:10px 0;border-bottom:1px solid #bdcbd2}.group summary{font-weight:650}
article{background:#fff;border:1px solid #d6e1e6;border-radius:7px;padding:12px;margin:10px 0;min-width:0}.images{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
figure{margin:0 0 8px}img{display:block;max-width:100%;max-height:66vh;object-fit:contain;object-position:left;background:#ecf1f4}figcaption{color:#405966}
.tiles .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,490px),1fr));gap:10px}.tiles img{max-height:290px}
@media(max-width:650px){.images{grid-template-columns:1fr}}
</style></head><body>"""

PAGE_SCRIPT = """<script>
const query=document.getElementById('query'), vote=document.getElementById('vote');
const groups=[...document.querySelectorAll('.group')], cards=groups.map(group=>[...group.querySelectorAll('article')]);
function filter(){
  const search=query.value.trim().toLowerCase();
  let count=0;
  groups.forEach((group,i)=>{
    let found=false;
    for(const card of cards[i]){
      card.hidden=!(card.dataset.path+' '+card.dataset.class).toLowerCase().includes(search)
        || (vote.value!=='' && card.dataset.vote!==vote.value);
      if(!card.hidden){count++;found=true;}
    }
    group.hidden=!found;
    if(found&&(search||vote.value)){group.open=true;}
  });
  document.getElementById('shown').textContent='显示 '+count+' 幅';
}
query.addEventListener('input',filter);vote.addEventListener('change',filter);
document.getElementById('expand').onclick=()=>groups.forEach(group=>{if(!group.hidden)group.open=true;});
document.getElementById('collapse').onclick=()=>groups.forEach(group=>{group.open=false;});
document.getElementById('tiles').onclick=event=>{
  const active=document.body.classList.toggle('tiles');
  event.currentTarget.setAttribute('aria-pressed',String(active));
  if(active)groups.forEach(group=>{if(!group.hidden)group.open=true;});
};
filter();
</script>"""


def build_report(folder, result, config, files, check=None):
    artifacts, companions = companion_artifacts(folder,files,result['files'],check)
    if check:
        check()
    rows = [dict(row) for row in result['files']]
    for row, path in zip(rows,relative_paths(files,config['input']['paths'])):
        row.setdefault('relative_path',path)
    data = render_report({**result,'files':rows},config,companions).encode('utf-8')
    report = archive_path(folder,REPORT)
    storage.resolve_write(report,kind='INFERENCE_REPORT').write_bytes(data)
    artifacts[REPORT] = {'sha256':sha256(data).hexdigest(),'bytes':len(data)}
    write_json(archive_path(folder,MANIFEST),{'result_sha256':result_digest(result),'artifacts':artifacts})
    return artifacts
