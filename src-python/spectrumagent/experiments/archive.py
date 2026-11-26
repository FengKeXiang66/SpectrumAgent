"""Cross-session experiment discovery and reuse of self-produced fitted models."""
from datetime import datetime, timezone
import json

import numpy as np

from spectrumagent.data import DataError


class ExperimentArchive:
    def __init__(self, service):
        self.service = service

    def folders(self):
        if not self.service.root.is_dir():
            return
        for folder in self.service.root.iterdir():
            try:
                if folder.is_dir() and self.service.folder(folder.name).resolve() == folder.resolve():
                    yield folder
            except DataError:
                continue

    def recover_interrupted(self):
        # Called once at app startup, while no experiment worker exists.
        from .service import write_json
        for folder in self.folders():
            try:
                status = json.loads((folder / 'status.json').read_text('utf-8'))
                if status['status'] != 'running':
                    continue
                status.update(status='interrupted', finished_at=datetime.now(timezone.utc).isoformat(),
                              error={'error': 'EXPERIMENT_INTERRUPTED', 'detail': '应用退出时实验尚未完成；保留已有产物，不自动续训。'})
                write_json(folder / 'status.json', status)
            except (OSError, ValueError, KeyError):
                continue

    def item(self, identifier):
        record = self.service.get(identifier)
        config = record.get('config')
        if config is None:
            config = json.loads((self.service.folder(identifier) / 'config.json').read_text('utf-8'))
        scores = record.get('metrics', {})
        return {'experiment_id': identifier, 'name': config['name'], 'status': record['status'],
                'created_at': record.get('started_at', record.get('created_at', '')),
                'model_id': record.get('model_id', identifier) if record['status'] == 'succeeded' else None,
                'train_accuracy': scores.get('train', {}).get('accuracy'),
                'test_accuracy': scores.get('test', {}).get('accuracy'),
                'evaluation_unit': config['test']['evaluation_unit'], 'test_usage': config['test_usage'],
                'phase': record.get('phase'), 'error': record.get('error', {}).get('error')}

    def list(self, *, offset=0, limit=20):
        rows = []
        for folder in self.folders():
            try:
                rows.append(self.item(folder.name))
            except (OSError, ValueError, KeyError, DataError):
                rows.append({'experiment_id': folder.name, 'name': '归档记录不可读', 'status': 'unreadable',
                             'created_at': '', 'model_id': None, 'error': 'EXPERIMENT_ARCHIVE_INVALID'})
        rows.sort(key=lambda row: (row['created_at'], row['experiment_id']), reverse=True)
        return {'items': rows[offset:offset + limit], 'total': len(rows), 'offset': offset, 'limit': limit}

    def model_metadata(self, identifier, *, check=None):
        record = self.service.get(identifier)
        if record['status'] != 'succeeded':
            raise DataError('EXPERIMENT_MODEL_NOT_READY', '只有成功实验才有可复用的完整模型')
        self.service.artifact(identifier, 'model.joblib',check=check)
        config = json.loads(self.service.artifact(identifier, 'config.json',check=check).read_text('utf-8'))
        return {'model_id': record.get('model_id', identifier), 'experiment_id': identifier,
                'name': config['name'], 'stage': 'experiment', 'format': 'explicit_plsda_joblib_v1',
                'sha256': record['model_sha256'], 'classes': config['classes'],
                'wavelengths_nm': config['wavelengths_nm'], 'preprocessing': config['preprocessing'],
                'parameters': config['model'], 'input_stage': config['train'].get('input_stage', 'roi_images'),
                'neighborhood': config['train']['neighborhood'],
                'evaluation_unit': config['train']['evaluation_unit'], 'environment': record['environment']}

    def load_model(self, identifier, *, check=None):
        """Internal inference boundary; never accept an arbitrary pickle path."""
        import joblib
        import sklearn

        from .service import ExperimentModel
        metadata = self.model_metadata(identifier,check=check)
        environment = metadata['environment']
        if environment['sklearn'] != sklearn.__version__ or environment['joblib'] != joblib.__version__:
            raise DataError('EXPERIMENT_MODEL_ENVIRONMENT_CHANGED', '当前模型依赖版本与训练时不同，拒绝直接复用')
        try:
            path = self.service.artifact(identifier,'model.joblib',check=check)
            if check:
                from .inputs import CheckedStream
                with path.open('rb') as stream:
                    model = joblib.load(CheckedStream(stream,check))
            else:
                model = joblib.load(path)
            config = self.service.get(identifier)['config']
            if not isinstance(model, ExperimentModel) or model.config.model_dump(mode='json') != config:
                raise ValueError('model/config mismatch')
            if not np.array_equal(model.classes_, sorted(map(int, metadata['classes']))):
                raise ValueError('class mismatch')
        except (OSError, ValueError, TypeError, AttributeError) as error:
            raise DataError('EXPERIMENT_MODEL_INVALID', '归档模型与配置不一致，不能复用') from error
        return model

    def compare(self, first, second):
        if first == second:
            raise DataError('EXPERIMENT_COMPARISON_INVALID', '请选择两个不同的实验')
        a, b = (self.service.get(identifier) for identifier in (first, second))
        if any(row['status'] != 'succeeded' for row in (a, b)):
            raise DataError('EXPERIMENT_RESULT_NOT_READY', '仅可比较两个已成功完成的实验')
        scores = [json.loads(self.service.artifact(identifier, 'metrics.json').read_text('utf-8'))
                  for identifier in (first, second)]
        checks = {'evaluation_unit': scores[0]['test']['evaluation_unit'] == scores[1]['test']['evaluation_unit'],
                  'test_usage': scores[0]['test']['purpose'] == scores[1]['test']['purpose'],
                  'classes': a['config']['classes'] == b['config']['classes'],
                  'input_declarations': all(a['config'][role] == b['config'][role] for role in ('train', 'test')),
                  'source_fingerprints': a['artifacts']['sources.json']['sha256'] == b['artifacts']['sources.json']['sha256'],
                  'wavelength_axis': a['config']['wavelengths_nm'] == b['config']['wavelengths_nm'],
                  'metric_definition': scores[0]['test']['definition'] == scores[1]['test']['definition']}
        # Verify both provenance manifests rather than trusting a listed hash alone.
        for identifier in (first, second):
            self.service.artifact(identifier, 'sources.json')
        return {'first': first, 'second': second, 'comparable': all(checks.values()), 'checks': checks,
                'metrics': scores, 'note': '仅核对评价口径和输入一致性；不能依据测试或7t结果反向选择训练参数。'}
