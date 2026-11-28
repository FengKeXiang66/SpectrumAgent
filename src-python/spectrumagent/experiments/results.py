"""Verified, session-owned result projections; never added to LLM context."""
import base64
from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED

from spectrumagent.data import DataError
from .inputs import independent_duplicate_warning, split_check_text
from .report import split_warning_banner

PLOTS = ('train_input.png', 'train_processed.png', 'test_input.png', 'test_processed.png')
FILES = ('metrics.json', 'curves.json', 'config.json', 'sources.json', *PLOTS)
LIMIT = 16 * 1024 * 1024


def artifact_size(record, name):
    item = (record.get('artifacts') or {}).get(name)
    size = item.get('bytes') if isinstance(item, dict) else None
    if type(size) is not int or size < 0:
        raise DataError('EXPERIMENT_ARTIFACT_NOT_FOUND', f'归档缺少有效的结果文件记录：{name}')
    return size


class ExperimentResults:
    def __init__(self, dialogue):
        self.dialogue, self.service = dialogue, dialogue.service

    def record(self, owner, task_id=None, *, experiment_id=None):
        if experiment_id is None:
            task = self.dialogue.tasks.view(owner, task_id)
            experiment_id = task['experiment_id'] if task['status'] == 'succeeded' else None
        record = self.service.get(experiment_id) if experiment_id else None
        if record is None or record['status'] != 'succeeded':
            error = DataError('EXPERIMENT_RESULT_NOT_READY', '实验尚未成功完成，暂无可展示的完整结果')
            error.status_code = 409
            raise error
        return record

    def read(self, record, name):
        if artifact_size(record, name) > LIMIT:
            raise DataError('EXPERIMENT_RESULT_TOO_LARGE', '该结果文件超过展示、报告导出上限')
        return self.service.artifact(record['experiment_id'], name).read_bytes()

    def summary(self, owner, task_id=None, *, experiment_id=None):
        record = self.record(owner, task_id, experiment_id=experiment_id)
        scores = json.loads(self.read(record, 'metrics.json'))
        checks = record.get('split_checks') or {'status':'unavailable'}
        return {'experiment_id': record['experiment_id'], 'name': record['config']['name'],
                'sample_evaluation': self.service.sample_evaluations.view(record['experiment_id']),
                'metrics': scores, 'classes': record['config']['classes'],
                'processed_axis': 'component' if any(step['op'] == 'pca' for step in record['config']['preprocessing']) else 'wavelength_nm',
                'score_definition': record['score_definition'],
                'training_sampling': record['config'].get('training_sampling'),
                'split_checks': checks, 'split_check_text': split_check_text(checks),
                'split_warning': independent_duplicate_warning(record['config']['test_usage'], checks),
                'model': self.service.archive.model_metadata(record['experiment_id'])}

    def plot(self, owner, task_id, name, *, experiment_id=None):
        if name not in PLOTS:
            raise DataError('EXPERIMENT_ARTIFACT_NOT_FOUND', '只能读取本实验的四幅代表性曲线')
        data = self.read(self.record(owner, task_id, experiment_id=experiment_id), name)
        if len(data) > 4 * 1024 * 1024:
            raise DataError('EXPERIMENT_RESULT_TOO_LARGE', '图像超过界面展示上限，请核对实验产物')
        return {'name': name, 'png_base64': base64.b64encode(data).decode('ascii')}

    def export(self, owner, task_id, kind, *, experiment_id=None, output=None):
        if kind not in {'report', 'bundle'}:
            raise DataError('EXPERIMENT_ARTIFACT_NOT_FOUND', '不支持的导出类型')
        record = self.record(owner, task_id, experiment_id=experiment_id)
        report = self.read(record, 'report.html').decode('utf-8')
        from .sample_evaluation import report_html
        sample_view = self.service.sample_evaluations.view(record['experiment_id'])
        if sample_view['report']:
            report = report.replace('</html>', report_html(sample_view, record['config']['classes'])+'</html>')
        if (record.get('split_checks') or {}).get('status') != 'completed':
            from html import escape
            report = report.replace('</html>', '<p>'+escape(split_check_text(record.get('split_checks')))+'</p></html>')
        if 'data-split-warning=' not in report:
            report = report.replace('</html>', split_warning_banner(record['config']['test_usage'], record.get('split_checks'))+'</html>')
        report_size = len(report.encode('utf-8'))
        embedded_size = report_size + sum(4*((artifact_size(record,name)+2)//3) + 40 for name in PLOTS)
        if embedded_size <= LIMIT:
            for name in PLOTS:
                encoded = base64.b64encode(self.read(record, name)).decode('ascii')
                report = report.replace(f'src="{name}"', f'src="data:image/png;base64,{encoded}"')
        data = report.encode('utf-8')
        if kind == 'report':
            if embedded_size > LIMIT or len(data) > LIMIT:
                raise DataError('EXPERIMENT_RESULT_TOO_LARGE', '报告超过导出上限')
            return data
        target = output if output is not None else BytesIO()
        with ZipFile(target, 'w', compression=ZIP_DEFLATED) as archive:
            archive.writestr('report.html', data)
            archive.writestr('result.json', json.dumps(record, ensure_ascii=False, indent=2))
            if sample_view['report']:
                archive.writestr('sample_evaluation.json', json.dumps(sample_view, ensure_ascii=False, indent=2))
            for name in FILES:
                archive.write(self.service.artifact(record['experiment_id'], name), name)
        return target.getvalue() if output is None else None
