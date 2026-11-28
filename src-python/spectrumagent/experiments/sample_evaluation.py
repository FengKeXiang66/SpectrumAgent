"""Explicit, revisioned object reports derived from verified saved predictions.

This module never fits a model, chooses a Study candidate, or votes on truth.
"""
from collections import Counter, defaultdict
import csv
from functools import lru_cache
import hashlib
from html import escape
import json
import os
from pathlib import Path

import numpy as np

from backend.database import connect_database
from spectrumagent.data import DataError
from .report import metrics

PROTOCOL = 'sample_vote_v1'
MODES = ('IMAGE', 'MAPPED', 'MIXED')
INPUT_ARTIFACTS = ('config.json', 'metrics.json', 'train_predictions.npz', 'test_predictions.npz', 'train_origins.json', 'test_origins.json')


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


@lru_cache(maxsize=8192)
def source_key(source):
    # Only normalize identifiers: archived HDRs need not still be present.
    # Match inputs.source_path's canonical HDR identity, including junctions.
    # The bounded cache makes this one resolution per image, not per pixel.
    return os.path.normcase(str(Path(source).resolve()))


@lru_cache(maxsize=8192)
def source_ref(source):
    return hashlib.sha256(source_key(source).encode()).hexdigest()


def origin_rows(path):
    """Stream the saved JSON array (or sampling wrapper), not a million dicts."""
    decoder = json.JSONDecoder()
    with path.open(encoding='utf-8') as stream:
        buffer, eof = '', False
        def refill():
            nonlocal buffer, eof
            chunk = stream.read(65536)
            buffer += chunk
            eof = not chunk
        def whitespace():
            nonlocal buffer
            while True:
                buffer = buffer.lstrip()
                if buffer or eof: return
                refill()
        def token(character):
            nonlocal buffer
            whitespace()
            if not buffer.startswith(character): raise ValueError('来源 JSON 结构不合法')
            buffer = buffer[1:]
        def value():
            nonlocal buffer
            whitespace()
            while True:
                try:
                    result, end = decoder.raw_decode(buffer)
                    buffer = buffer[end:]
                    return result
                except json.JSONDecodeError:
                    if eof or len(buffer) > 2*1024*1024: raise ValueError('来源记录损坏或过大')
                    refill()
        whitespace()
        wrapped = buffer.startswith('{')
        if wrapped:
            token('{')
            while True:
                key = value(); token(':')
                if key == 'origins': break
                value(); token(',')
        token('[')
        whitespace()
        if not buffer.startswith(']'):
            while True:
                row = value()
                if not isinstance(row, dict): raise ValueError('来源必须逐条对应预测')
                yield row
                whitespace()
                if buffer.startswith(']'): break
                token(',')
        token(']')
        if wrapped: token('}')
        whitespace()
        if buffer: raise ValueError('来源 JSON 包含额外内容')


def aggregate(parts, classes, definition, declared_sources=None):
    """Pool all valid observations across views. Conflicts/ties never vote truth."""
    mode, minimum = definition['mode'], definition['minimum_valid']
    if mode == 'MIXED':
        return dict(protocol=PROTOCOL, status='not_applicable', reason='一图多物／混合材质，不存在唯一整图类别，实物级评价不适用。',
                    definition=definition, total_objects=None, roles={})
    mappings = {row['source_ref']: row['sample_id'] for row in definition.get('mapping', [])}
    groups, image_truth, sample_truth, sides = {}, defaultdict(set), defaultdict(set), defaultdict(set)
    allowed, source_groups = defaultdict(set), {}
    def group(role, source):
        cached = source_groups.get((role, source))
        if cached is not None: return cached
        ref = source_ref(source)
        if mode == 'MAPPED' and ref not in mappings: raise ValueError('分组表未覆盖来源')
        sample = source_key(source) if mode == 'IMAGE' else mappings[ref]
        sides[sample].add(role)
        row = groups.setdefault((role, sample), dict(sample_id=sample, display_id=Path(source).name if mode == 'IMAGE' else sample,
            truth=Counter(), votes=Counter(), sources=set(), observations=0, valid=0))
        row['sources'].add(ref)
        source_groups[role, source] = row
        return row
    # Include declared images even when all their observations were filtered out.
    for role, sources in (declared_sources or {}).items():
        for source in sources:
            allowed[role].add(source_ref(source)); group(role, source)
    for role, truth, prediction, origins in parts:
        count = 0
        for i, origin in enumerate(origins):
            if i >= len(truth) or not isinstance(origin.get('source'), str):
                raise ValueError('来源与预测数量或字段不一致')
            source = origin['source']; ref = source_ref(source)
            if declared_sources is not None and ref not in allowed[role]: raise ValueError('预测来源不属于该数据划分')
            row = group(role, source)
            target, predicted = int(truth[i]), int(prediction[i])
            if target not in classes: raise ValueError('保存真值不在类别表内')
            row['truth'][target] += 1
            image_truth[ref].add(target)
            sample_truth[row['sample_id']].add(target)
            if predicted in classes:
                row['votes'][predicted] += 1; row['valid'] += 1
            row['sources'].add(ref); row['observations'] += 1
            count += 1
        if count != len(truth) or len(prediction) != len(truth): raise ValueError('来源与预测数量不一致')
    roles = {}
    for role in ('train', 'test'):
        rows, accepted_truth, accepted_prediction = [], [], []
        reasons = Counter()
        for (side, _), row in sorted(groups.items()):
            if side != role: continue
            flags = []
            if len(sample_truth[row['sample_id']]) > 1 or any(len(image_truth[s]) > 1 for s in row['sources']): flags.append('truth_conflict')
            if not row['truth']: flags.append('truth_unavailable')
            if len(sides[row['sample_id']]) > 1: flags.append('split_overlap')
            if row['valid'] < minimum: flags.append('insufficient')
            leaders = [key for key, n in row['votes'].items() if n == max(row['votes'].values(), default=0)]
            if len(leaders) > 1: flags.append('tie')
            target = next(iter(row['truth'])) if len(row['truth']) == 1 and 'truth_conflict' not in flags else None
            predicted = leaders[0] if len(leaders) == 1 else None
            if not flags:
                accepted_truth.append(target); accepted_prediction.append(predicted)
            reasons.update(flags)
            rows.append(dict(sample_id=row['sample_id'], display_id=row['display_id'], image_count=len(row['sources']),
                observations=row['observations'], valid=row['valid'], truth_counts=dict(row['truth']), votes=dict(row['votes']),
                truth=target, prediction=predicted, correct=target == predicted if not flags else None,
                status=flags[0] if flags else 'included', reasons=flags))
        score = metrics(np.asarray(accepted_truth), np.asarray(accepted_prediction), classes, []) if accepted_truth else None
        roles[role] = dict(total=len(rows), included=len(accepted_truth), excluded=len(rows)-len(accepted_truth),
                           exclusion_counts=dict(reasons), metrics=score, rows=rows)
    return dict(protocol=PROTOCOL, status='ready', definition=definition, total_objects=len(sides), roles=roles,
        truth_basis='已保存预测对应观测的真值；未通过质量筛选或未被抽样的区域不参与本报告。',
        observation_note='阈值作用于保存的有效像元／中心像元观测，不等于原图全部前景像元。',
        macro_definition='与像素指标一致：仅在纳入评价的真值中出现的类别上宏平均；PLS响应不是概率。')


class SampleEvaluations:
    def __init__(self, service):
        self.service, self.database = service, service.paths.database
        with connect_database(self.database) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS experiment_sample_evaluation (
                experiment_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, definition TEXT NOT NULL,
                report TEXT NOT NULL, source_digest TEXT NOT NULL, form_id TEXT)''')

    def _record(self, identifier):
        record = self.service.get(identifier)
        if record['status'] != 'succeeded': raise DataError('EXPERIMENT_RESULT_NOT_READY', '请先完成实验')
        config = json.loads(self.service.artifact(identifier, 'config.json').read_text('utf-8'))
        return record, config

    def declared(self, identifier):
        """Read only the user's declaration; no holdout predictions for Study."""
        from .evaluation_definition import specification
        with connect_database(self.database) as db:
            row = db.execute('SELECT definition FROM experiment_sample_evaluation WHERE experiment_id=?',(identifier,)).fetchone()
        return specification(json.loads(row[0])) if row else None

    def sources(self, config):
        if any(config[role]['kind'] != 'roi_images' for role in ('train', 'test')): return []
        rows = {}
        for role in ('train', 'test'):
            for member in config[role]['members']:
                source = member['header_path']; ref = source_ref(source)
                rows.setdefault(ref, dict(source_ref=ref, name=Path(source).name, roles=[]))['roles'].append(role)
        return list(rows.values())

    def _digest(self, record, *, verify):
        values = {}
        for name in INPUT_ARTIFACTS:
            if name not in record['artifacts']: raise DataError('SAMPLE_EVALUATION_UNAVAILABLE', '历史记录缺少预测或来源，无法计算实物评价')
            if verify: self.service.artifact(record['experiment_id'], name)
            values[name] = record['artifacts'][name]['sha256']
        return hashlib.sha256(encode(values).encode()).hexdigest()

    def view(self, identifier):
        record, config = self._record(identifier)
        with connect_database(self.database) as db:
            row = db.execute('SELECT revision,definition,report,source_digest,form_id FROM experiment_sample_evaluation WHERE experiment_id=?', (identifier,)).fetchone()
        image_input = all(config[r]['kind'] == 'roi_images' for r in ('train', 'test'))
        complete = all(name in record['artifacts'] for name in INPUT_ARTIFACTS)
        reason = (None if image_input and complete else '历史记录缺少预测或来源，无法派生实物报告。' if image_input else
            '当前报告需要原图来源。NPZ 的 groups 可能表示批次，本阶段不能将其认定为实物编号。')
        inherited = config.get('sample_evaluation')
        if inherited:
            inherited = dict(inherited, merge='pool_observations', tie='exclude', truth='unique_or_exclude', protocol=PROTOCOL)
        base = dict(revision=0, definition=inherited, definition_origin='experiment_config' if inherited else 'unconfigured',
                    report=None, sources=self.sources(config),
                    applicable=image_input and complete, unavailable_reason=reason, form_id=None)
        if row:
            if self._digest(record, verify=True) != row[3]: raise DataError('SAMPLE_EVALUATION_STALE', '来源记录变化，请重新核对')
            base.update(revision=row[0], definition=json.loads(row[1]), report=json.loads(row[2]), form_id=row[4],definition_origin='report_override')
        selection = config.get('study_selection')
        base.update(study_selection=selection, selection_warning=None)
        if selection and base['definition']:
            from .evaluation_definition import training_digest
            from .schema import ExperimentConfig
            if not selection.get('definition_digest') or training_digest(ExperimentConfig.model_validate(config),base['definition']) != selection['definition_digest']:
                base['selection_warning'] = '本报告实物定义与选优时的定义不一致或选优时未明确实物定义；原排名不代表本报告口径，需重新寻优。'
        return base

    def csv_mapping(self, identifier, path):
        if not Path(path).is_absolute() or Path(path).suffix.lower() != '.csv' or Path(path).stat().st_size > 4*1024*1024:
            raise ValueError('请选择不超过4MB的分组表CSV绝对路径')
        self._record(identifier)
        with Path(path).open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if not {'source', 'sample_id'} <= set(reader.fieldnames or []): raise ValueError('分组表需要 source（HDR绝对路径）、sample_id 列；batch不能代替实物编号')
            rows = []
            for item in reader:
                if len(rows) >= 4096 or not Path(item.get('source') or '').is_absolute(): raise ValueError('来源必须为HDR绝对路径，最多4096条')
                rows.append(dict(source_ref=source_ref(item['source']), sample_id=(item.get('sample_id') or '').strip()))
        return rows

    def update(self, identifier, revision, mode, minimum=100, mapping=None, form_id=None):
        if mode not in MODES or type(minimum) is not int or not 1 <= minimum <= 1000000: raise ValueError('请选择有效的评价定义与正整数阈值')
        if type(revision) is not int or revision < 0: raise ValueError('修订号须为非负整数')
        record, config = self._record(identifier)
        sources = self.sources(config)
        if not sources and mode != 'MIXED': raise DataError('SAMPLE_EVALUATION_UNAVAILABLE', '当前实物报告需要原图来源；NPZ分组字段不能直接认定为实物编号')
        mapping = mapping or []
        if mode == 'MAPPED':
            if (len(mapping) != len(sources) or {r['source_ref'] for r in mapping} != {r['source_ref'] for r in sources}
                    or any(not isinstance(r['sample_id'], str) or not r['sample_id'].strip() or len(r['sample_id']) > 160 for r in mapping)):
                raise ValueError('分组表必须完整、唯一覆盖本实验的每幅图，sample_id 不能为空')
            mapping = [dict(source_ref=row['source_ref'], sample_id=row['sample_id'].strip()) for row in mapping]
        elif mapping:
            raise ValueError('仅多图一物模式使用分组表')
        definition = dict(mode=mode, minimum_valid=minimum, mapping=mapping,
            merge='pool_observations', tie='exclude', truth='unique_or_exclude', protocol=PROTOCOL)
        digest = self._digest(record, verify=True)
        classes = {int(k): v for k, v in config['classes'].items()}
        parts = []
        try:
            if mode != 'MIXED':
                for role in ('train', 'test'):
                    with np.load(self.service.artifact(identifier, role+'_predictions.npz'), allow_pickle=False) as data:
                        truth, predicted = data['truth'].copy(), data['prediction'].copy()
                    if truth.ndim != 1 or truth.shape != predicted.shape or truth.dtype.kind not in 'iu' or predicted.dtype.kind not in 'iu': raise ValueError('预测与真值须为同长整数数组')
                    parts.append((role, truth, predicted, origin_rows(self.service.artifact(identifier, role+'_origins.json'))))
            declared = {role: [member['header_path'] for member in config[role]['members']]
                        for role in ('train', 'test')} if mode != 'MIXED' else None
            report = aggregate(parts, classes, definition, declared)
            pixel = json.loads(self.service.artifact(identifier, 'metrics.json').read_text('utf-8'))
            report['pixel_metrics'] = {role: {key: pixel[role].get(key) for key in
                ('n', 'accuracy', 'macro_f1', 'evaluation_unit', 'purpose')} for role in ('train', 'test')}
            for role, row in report['roles'].items():
                if row['metrics'] is not None:
                    row['metrics'].update(evaluation_unit='sample', purpose=pixel[role]['purpose'])
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise DataError('SAMPLE_EVALUATION_UNAVAILABLE', '保存的来源或预测无法完整对应，未生成实物结论') from error
        # Recheck after streaming as well: a file changed during aggregation must
        # not become a report purportedly bound to the original artifact digest.
        if self._digest(record, verify=True) != digest:
            raise DataError('SAMPLE_EVALUATION_STALE', '来源记录变化，请重新核对')
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM experiment_sample_evaluation WHERE experiment_id=?', (identifier,)).fetchone()
            if (row[0] if row else 0) != revision: raise DataError('SAMPLE_EVALUATION_CONFLICT', '评价定义已变化，请刷新后核对')
            db.execute('''INSERT INTO experiment_sample_evaluation VALUES (?,?,?,?,?,?) ON CONFLICT(experiment_id)
                DO UPDATE SET revision=excluded.revision,definition=excluded.definition,report=excluded.report,source_digest=excluded.source_digest,form_id=excluded.form_id''',
                (identifier, revision+1, encode(definition), encode(report), digest, form_id))
        return self.view(identifier)


def report_html(view, classes):
    report = view.get('report')
    if not report: return ''
    definition = report['definition']
    body = [f'<section data-sample-evaluation="true"><h2>实物级派生评价 · {PROTOCOL} · 修订 {view["revision"]}</h2>',
        '<p>声明：'+escape(definition['mode'])+f'；有效观测阈值 N={definition["minimum_valid"]}；同实物所有图观测合并投票，平票与真值冲突排除。</p>']
    if view.get('selection_warning'): body.append('<p role="alert">'+escape(view['selection_warning'])+'</p>')
    if report['status'] != 'ready': return ''.join(body)+ '<p>'+escape(report['reason'])+'</p></section>'
    body += [f'<p><strong>全实验实物数 n={report["total_objects"]}</strong>，不是像元数；训练与测试指标分别计数。</p>',
             '<p>'+escape(report['truth_basis']+' '+report['observation_note']+' '+report['macro_definition'])+'</p>']
    for role, title in (('train', '训练拟合'), ('test', '测试')):
        result = report['roles'][role]; score = result['metrics']
        body.append(f'<h3>{title}：实物 {result["total"]}，纳入 {result["included"]}，排除 {result["excluded"]}</h3>')
        pixel = report['pixel_metrics'][role]
        if pixel['purpose'] == 'development_regression':
            body.append('<p>用途：开发复现核验，不能作为新的独立泛化成绩。</p>')
        body.append(f'<p>原观测指标（{escape(str(pixel["evaluation_unit"]))}）：n={pixel["n"]}，accuracy={pixel["accuracy"]:.4%}，macro-F1={pixel["macro_f1"]:.6f}。以下实物指标与其并列，不替代原指标。</p>')
        body.append(f'<p>accuracy={score["accuracy"]:.4%}；macro-F1={score["macro_f1"]:.6f}</p>' if score else '<p>没有可评价实物，指标未定义。</p>')
        body.append('<p>排除原因（可重叠）：'+escape(encode(result['exclusion_counts']))+'</p>')
        if score: body.append('<details><summary>实物混淆矩阵与各类指标</summary><pre>'+escape(encode(score))+'</pre></details>')
        for included, caption in ((True, '纳入评价的逐实物结果'), (False, '未计入实物指标的完整列表')):
            body.append('<h4>'+caption+'</h4><table><tr><th>实物</th><th>图数</th><th>有效观测</th><th>真值</th><th>预测</th><th>判对</th><th>状态</th></tr>')
            for row in result['rows']:
                if (row['status'] == 'included') != included: continue
                truth = (classes.get(str(row['truth']), classes.get(row['truth'])) if row['truth'] is not None else
                    '；'.join(str(classes.get(str(key), classes.get(key, key)))+': '+str(n) for key,n in row['truth_counts'].items()) or '无保存真值')
                values = [row['display_id'], row['image_count'], row['valid'], truth,
                    classes.get(str(row['prediction']), classes.get(row['prediction'], '无唯一预测')),
                    '未计入' if row['correct'] is None else '是' if row['correct'] else '否', '、'.join(row['reasons']) or 'included']
                body.append('<tr>'+''.join('<td>'+escape(str(value))+'</td>' for value in values)+'</tr>')
            body.append('</table>')
    return ''.join(body)+'</section>'
