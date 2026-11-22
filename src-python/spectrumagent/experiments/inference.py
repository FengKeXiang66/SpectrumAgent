"""Unlabelled inference using an archived model and its frozen fitted pipeline."""
import base64
import csv
import colorsys
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from threading import Event, RLock, Thread
from time import time
from typing import Annotated, Literal, Union
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
from PIL import Image
from pydantic import Field, FiniteFloat, model_validator
from scipy.ndimage import minimum_filter
from threadpoolctl import threadpool_limits

from spectrumagent.data import DataError
from spectrumagent.data.readers import open_envi
from spectrumagent.storage import guard as storage
from .inputs import record_source, check_sources, mapping_weights, sha256
from .schema import InputModel, Quality
from .service import write_json, read_json, save_arrays


def class_palette(classes):
    fixed = [(31,119,180),(255,127,14),(44,160,44),(214,39,40),(148,103,189),(140,86,75),(227,119,194),(127,127,127),(188,189,34),(23,190,207)]
    return {str(label): fixed[i] if len(classes)<=len(fixed) else tuple(int(v*255) for v in colorsys.hsv_to_rgb(i/len(classes),.65,.85))
            for i,label in enumerate(classes)}


class NPZInference(InputModel):
    kind: Literal['npz']
    paths: Annotated[list[str], Field(min_length=1)]
    spectra_key: str
    wavelengths_key: str
    input_stage: Literal['spectra', 'neighborhood_mean']
    neighborhood: Annotated[int, Field(ge=1)]
    evaluation_unit: Literal['spectrum', 'center_pixel']


class NoForeground(InputModel):
    mode: Literal['none']


class BrightnessEdges(InputModel):
    mode: Literal['brightness_edges']
    wavelengths_nm: Annotated[list[FiniteFloat], Field(min_length=1)]
    threshold: FiniteFloat
    left_min: Annotated[int, Field(ge=0)]
    right_min: Annotated[int, Field(ge=0)]
    edge_search_columns: Annotated[int, Field(ge=0)]
    edge_bad_fraction: Annotated[FiniteFloat, Field(gt=0, le=1)]
    edge_low: FiniteFloat
    edge_high: FiniteFloat

    @model_validator(mode='after')
    def valid_levels(self):
        if self.edge_low>=self.edge_high or len(set(self.wavelengths_nm))!=len(self.wavelengths_nm):
            raise ValueError('边缘亮度上下界或探测波长不合法')
        return self


class ENVIInference(InputModel):
    kind: Literal['envi']
    paths: Annotated[list[str], Field(min_length=1)]
    wavelength_unit: Literal['nm', 'um']
    mapping_window_nm: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    nearest_tolerance_nm: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    quality: Quality
    foreground: Annotated[Union[NoForeground,BrightnessEdges],Field(discriminator='mode')] = NoForeground(mode='none')


class InferenceConfig(InputModel):
    model_id: Annotated[str, Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')]
    input: Annotated[Union[NPZInference, ENVIInference], Field(discriminator='kind')]


def files_for(spec):
    extension = '.npz' if spec.kind == 'npz' else '.hdr'
    files = []
    for value in spec.paths:
        path = Path(value).expanduser()
        if not path.is_absolute() or not path.exists():
            raise DataError('INFERENCE_INPUT_INVALID', '推理输入须为存在的绝对文件或目录路径')
        files.extend(sorted(path.rglob('*' + extension)) if path.is_dir() else [path])
    files = [path.resolve() for path in files]
    if not files or len(files) != len(set(files)) or any(path.suffix.lower() != extension for path in files):
        raise DataError('INFERENCE_INPUT_INVALID', '没有找到对应格式的输入，或包含重复文件')
    return files


def envi_mapping(path, spec, target):
    dataset = open_envi(path, raw=True)
    declared = str(dataset.metadata.get('wavelength units', '')).lower()
    units = {'nm': {'nm', 'nanometers', 'nanometres'}, 'um': {'um', 'μm', 'micrometers', 'microns'}}
    if declared and declared not in units[spec.wavelength_unit]:
        raise DataError('INFERENCE_AXIS_INVALID', '声明的波长单位与HDR记录不一致')
    source = np.asarray(dataset.wavelengths) * (1000 if spec.wavelength_unit == 'um' else 1)
    weights = mapping_weights(source, target, spec.mapping_window_nm, spec.nearest_tolerance_nm)
    return dataset, weights


def npz_values(path, spec, target):
    with np.load(path, allow_pickle=False) as archive:
        X, waves = archive[spec.spectra_key].copy(), archive[spec.wavelengths_key].copy()
    if (waves.shape != (len(target),) or not np.array_equal(waves, target)):
        raise DataError('INFERENCE_AXIS_INVALID', '推理NPZ波长必须与模型目标波长逐项一致，不能按列号猜测')
    if X.ndim != 2 or X.shape[1] != len(target) or not len(X) or X.dtype.kind not in 'iuf' or not np.isfinite(X).all():
        raise DataError('INFERENCE_INPUT_INVALID', '推理光谱须为非空、有限且通道数匹配的二维数值矩阵')
    return X


class InferenceService:
    def __init__(self, experiments):
        self.experiments = experiments
        self.lock = RLock()
        self.active = {}

    def folder(self, model_id, run_id):
        base = self.experiments.folder(model_id) / 'inferences'
        # Reuse the UUID validator without allowing a path supplied by a caller.
        self.experiments.folder(run_id)
        folder = base / run_id
        if folder.resolve().parent != base.resolve():
            raise DataError('INFERENCE_NOT_FOUND', '推理任务不存在')
        return folder

    def inspect(self, config):
        metadata = self.experiments.archive.model_metadata(config.model_id)
        spec = config.input
        if spec.kind == 'npz':
            stage = metadata['input_stage']
            expected_stage = ('neighborhood_mean' if metadata['neighborhood'] > 1 else 'spectra') if stage == 'roi_images' else stage
            if (spec.input_stage != expected_stage or spec.neighborhood != metadata['neighborhood']
                    or spec.evaluation_unit != metadata['evaluation_unit']):
                raise DataError('INFERENCE_STAGE_MISMATCH', '输入阶段、邻域或评价单位与模型训练定义不同；不重复平均或重新拟合预处理')
        elif metadata['evaluation_unit'] != 'center_pixel':
            raise DataError('INFERENCE_STAGE_MISMATCH', '该模型按光谱样本训练，不能直接冒充整图像元分类模型')
        files, manifest = files_for(spec), {}
        for path in files:
            record_source(path, manifest)
            if spec.kind == 'npz':
                npz_values(path, spec, metadata['wavelengths_nm'])
            else:
                dataset, _ = envi_mapping(path, spec, metadata['wavelengths_nm'])
                record_source(dataset.data_path, manifest)
                if metadata['neighborhood'] > min(dataset.shape[:2]):
                    raise DataError('INFERENCE_INPUT_INVALID', '模型要求的邻域大于输入图像尺寸')
                fg=spec.foreground
                if fg.mode!='none':
                    wave=np.asarray(dataset.wavelengths)*(1000 if spec.wavelength_unit=='um' else 1)
                    if fg.left_min+fg.right_min>=dataset.shape[1] or np.any(np.min(np.abs(wave[:,None]-fg.wavelengths_nm),axis=0)>spec.nearest_tolerance_nm):
                        raise DataError('INFERENCE_FOREGROUND_INVALID','前景规则的边缘宽度或探测波长与原图不兼容')
        storage.for_database(self.experiments.paths.database).add_sources(list(manifest))
        check_sources(manifest)
        return {'sources': manifest, 'model_sha256': metadata['sha256'], 'files': [str(p) for p in files]}

    def submit(self, owner, config, reviewed):
        with self.lock:
            if not self.experiments.lock.acquire(blocking=False):
                raise DataError('EXPERIMENT_BUSY', '已有训练或推理正在运行，请等待完成或取消')
            run_id = str(uuid4())
            folder = self.folder(config.model_id, run_id)
            try:
                storage.mkdir(folder, parents=True)
                write_json(folder / 'config.json', config.model_dump(mode='json'))
                write_json(folder / 'review.json', reviewed)
                state = {'run_id': run_id, 'model_id': config.model_id, 'kind': config.input.kind, 'owner_session_id': owner,
                         'status': 'queued', 'phase': 'checking', 'completed_files': 0, 'total_files': len(reviewed['files']),
                         'completed_rows': 0, 'total_rows': 0, 'started_at': time(), 'finished_at': None, 'error': None}
                write_json(folder / 'status.json', state)
                self.active[(config.model_id, run_id)] = (owner, Event())
                Thread(target=self._work, args=(config, run_id, reviewed, state), daemon=True).start()
            except Exception:
                self.active.pop((config.model_id, run_id), None)
                self.experiments.lock.release()
                raise
        return {'inference_run_id': run_id, 'model_id': config.model_id, 'status': 'queued'}

    def status(self, model_id, run_id, owner=None):
        try:
            value = read_json(self.folder(model_id, run_id) / 'status.json')
        except FileNotFoundError:
            error = DataError('INFERENCE_NOT_FOUND', '推理记录不存在')
            error.status_code = 404
            raise error from None
        value.pop('owner_session_id', None)
        with self.lock:
            active = self.active.get((model_id,run_id))
            value['cancel_requested'] = bool(active and active[1].is_set())
            value['can_cancel'] = bool(active and active[0] == owner)
        value['elapsed_seconds'] = max(0, (value['finished_at'] or time()) - value['started_at'])
        return value

    def cancel(self, owner, model_id, run_id):
        with self.lock:
            active = self.active.get((model_id, run_id))
            if active and active[0] != owner:
                raise DataError('INFERENCE_OWNER_MISMATCH', '只能取消本会话提交的推理任务')
            if active:
                active[1].set()
        return self.status(model_id, run_id, owner)

    def recover(self):
        for model in self.experiments.archive.folders():
            for path in (model / 'inferences').glob('*/status.json'):
                try:
                    state = json.loads(path.read_text('utf-8'))
                    if state['status'] in {'queued', 'running'}:
                        state.update(status='interrupted', finished_at=time(), error='INFERENCE_INTERRUPTED')
                        write_json(path, state)
                except (OSError, ValueError, KeyError):
                    continue

    def history(self, model_id):
        self.experiments.archive.model_metadata(model_id)
        rows = []
        for path in (self.experiments.folder(model_id) / 'inferences').glob('*/status.json'):
            rows.append(self.status(model_id, path.parent.name))
        return sorted(rows, key=lambda row: row['started_at'], reverse=True)[:20]

    def _work(self, config, run_id, reviewed, state):
        folder = self.folder(config.model_id, run_id)
        cancel = self.active[(config.model_id, run_id)][1]
        def progress(**fields):
            if cancel.is_set():
                raise DataError('INFERENCE_CANCELLED', '推理已在数据批次边界取消')
            state.update(status='running', **fields)
            write_json(folder / 'status.json', state)
        try:
            progress(phase='checking')
            current = self.inspect(config)
            if current != reviewed:
                raise DataError('INFERENCE_SOURCE_CHANGED', '输入文件、目录成员或模型在方案确认后发生变化，请重新核对')
            model = self.experiments.archive.load_model(config.model_id)
            write_json(folder / 'sources.json', current['sources'])
            rows = []
            with threadpool_limits(limits=2):
                for index, value in enumerate(current['files']):
                    progress(phase='predicting', completed_files=index, completed_rows=0, total_rows=0)
                    path = Path(value)
                    if config.input.kind == 'npz':
                        X = npz_values(path, config.input, model.config.wavelengths_nm)
                        responses = []
                        for start in range(0, len(X), 8192):
                            progress(completed_rows=start, total_rows=len(X))
                            responses.append(model.decision_function(X[start:start+8192], model.config.wavelengths_nm))
                        responses = np.concatenate(responses)
                        prediction = model.classes_[responses.argmax(axis=1)]
                        save_arrays(folder / f'{index}.npz', prediction=prediction, responses=responses)
                        with storage.resolve_write(folder / f'{index}.csv', kind='INFERENCE_CSV').open('w', encoding='utf-8-sig', newline='') as stream:
                            writer = csv.writer(stream)
                            writer.writerow(['index', 'class_id', 'class_name'])
                            writer.writerows((i, int(label), model.config.classes[int(label)]) for i, label in enumerate(prediction))
                        excluded, total = 0, len(prediction)
                    else:
                        prediction, excluded, total, image_info = self._image(path, config.input, model, folder, index, progress)
                    rows.append({'file_index': index, 'name': path.name, 'classified': len(prediction), 'excluded': excluded, 'total': total,
                                 'counts': {str(label): int((prediction == label).sum()) for label in model.classes_}})
                    if config.input.kind=='envi':
                        rows[-1].update(image_info)
                    progress(completed_files=index+1, completed_rows=state['total_rows'])
            progress(phase='reporting')
            check_sources(current['sources'])
            self.experiments.artifact(config.model_id, 'model.joblib')
            result = {'run_id': run_id, 'model_id': config.model_id, 'kind': config.input.kind,
                      'created_at': datetime.now(timezone.utc).isoformat(), 'model_sha256': current['model_sha256'],
                      'classes': model.config.model_dump(mode='json')['classes'], 'files': rows,
                      'colors': {key:'#'+''.join(f'{value:02x}' for value in color) for key,color in class_palette(model.classes_).items()},
                      'evaluation_unit': model.config.train.evaluation_unit, 'score_definition': 'uncalibrated_pls_response',
                      'foreground': config.input.foreground.model_dump(mode='json') if config.input.kind=='envi' else None,
                      'note': '闭集分类；无真值标签，不计算准确率。PLS响应不是概率。未分类像元含边界、质量或已声明前景规则排除，均不代表已识别背景或未知类。'}
            result['artifacts'] = {path.name: {'sha256': sha256(path), 'bytes': path.stat().st_size}
                                   for path in folder.iterdir() if path.is_file() and path.name not in {'status.json', 'result.json'}}
            write_json(folder / 'result.json', result)
            state.update(status='succeeded', finished_at=time())
        except Exception as error:
            code = error.code if isinstance(error, DataError) else 'INFERENCE_FAILED'
            state.update(status='cancelled' if code == 'INFERENCE_CANCELLED' else 'failed', error=code, finished_at=time())
        finally:
            try:
                write_json(folder / 'status.json', state)
            finally:
                with self.lock:
                    self.active.pop((config.model_id, run_id), None)
                self.experiments.lock.release()

    def _image_context(self,dataset,spec,target,progress):
        height,width=dataset.shape[:2]
        wave=np.asarray(dataset.wavelengths)*(1000 if spec.wavelength_unit=='um' else 1)
        preview_ids=np.abs(wave[:,None]-np.asarray([target[-1],target[len(target)//2],target[0]])).argmin(axis=0)
        preview=np.empty((height,width,3),np.float32)
        foreground=spec.foreground
        level=np.empty((height,width),np.float32) if foreground.mode!='none' else None
        if level is not None:
            ids=np.abs(wave[:,None]-np.asarray(foreground.wavelengths_nm)).argmin(axis=0)
            if np.any(np.abs(wave[ids]-foreground.wavelengths_nm)>spec.nearest_tolerance_nm):
                raise DataError('INFERENCE_AXIS_INVALID','亮度探测波长附近没有足够接近的原始通道')
        for first in range(0,height,32):
            last=min(first+32,height)
            progress(phase='preparing',completed_rows=first,total_rows=height)
            raw=dataset.read_region(first,last,0,width)
            preview[first:last]=raw[:,:,preview_ids].astype(np.float32)
            if level is not None:
                level[first:last]=np.median(raw[:,:,ids].astype(np.float32)/float(dataset.metadata['scale_factor']),axis=2)
        left,right=0,0
        if level is not None:
            abnormal=((level<foreground.edge_low)|(level>foreground.edge_high)).mean(axis=0)>=foreground.edge_bad_fraction
            search=min(width,foreground.edge_search_columns)
            left=max(foreground.left_min,int(np.flatnonzero(abnormal[:search]).max(initial=-1))+1)
            right=max(foreground.right_min,int(np.flatnonzero(abnormal[::-1][:search]).max(initial=-1))+1)
            if left+right>=width:
                raise DataError('INFERENCE_FOREGROUND_INVALID','声明的边缘屏蔽没有留下有效图像列，请核对尺寸和参数')
        # Display-only stretch; these values never enter classifier or mask decisions.
        display=preview[:,left:width-right if right else width]
        low,high=np.nanpercentile(display,[2,99.7],axis=(0,1))
        rgb=np.uint8(np.nan_to_num(np.clip((preview-low)/np.maximum(high-low,1),0,1))*255)
        return level,left,right,rgb,wave[preview_ids].tolist()

    def _image(self, path, spec, model, folder, index, progress):
        dataset, weights = envi_mapping(path, spec, model.config.wavelengths_nm)
        height, width = dataset.shape[:2]
        k, q = model.config.train.neighborhood, spec.quality
        radius = k // 2
        level,left,right,preview,preview_waves=self._image_context(dataset,spec,model.config.wavelengths_nm,progress)
        preview_image=Image.fromarray(preview)
        preview_image.thumbnail((1200,1200),Image.Resampling.NEAREST)
        preview_image.save(storage.resolve_write(folder/f'{index}_input.png',kind='INFERENCE_PREVIEW'))
        reasons=np.full((height,width),3,np.uint8)
        reasons[:radius]=4
        if radius:
            reasons[-radius:]=4;reasons[:,:radius]=4;reasons[:,-radius:]=4
        if level is not None:
            reasons[np.isfinite(level)&(level<=spec.foreground.threshold)]=1
        reasons[:,:left]=2
        if right:reasons[:,-right:]=2
        progress(phase='predicting',completed_rows=0,total_rows=height)
        labels, accepted = np.zeros((height, width), np.int64), np.zeros((height, width), bool)
        for first in range(0, height, 32):
            last = min(first+32, height)
            low, high = max(0, first-radius), min(height, last+radius)
            raw = dataset.read_region(low, high, 0, width)
            if np.iscomplexobj(raw):
                raise DataError('INFERENCE_INPUT_INVALID', '不支持复数光谱')
            raw = raw.astype(np.float64)
            mapped = (raw / float(dataset.metadata['scale_factor'])) @ weights
            used = raw[:, :, weights.sum(axis=1) > 0]
            valid = (np.isfinite(mapped).all(axis=2) & (mapped.mean(axis=2) > q.min_mean)
                     & (mapped.std(axis=2) > q.min_std) & ((used == 0).mean(axis=2) <= q.max_zero_fraction))
            if q.saturation is not None:
                valid &= (used < q.saturation).all(axis=2)
            valid[:,:left]=False
            if right:valid[:,-right:]=False
            safe = minimum_filter(valid.astype(np.uint8), k, mode='constant', cval=0)[first-low:last-low] > 0
            if level is not None:
                safe &= np.isfinite(level[first:last])&(level[first:last]>spec.foreground.threshold)
            padded = np.pad(mapped, ((radius, radius), (radius, radius), (0, 0)))
            total = np.zeros((last-first, width, len(model.config.wavelengths_nm)), np.float64)
            for dr in range(-radius, radius+1):
                for dc in range(-radius, radius+1):
                    r, c = first-low+radius+dr, radius+dc
                    total += padded[r:r+last-first, c:c+width]
            X = (total[safe] / k**2).astype(np.float32)
            prediction = np.empty(len(X), np.int64)
            for start in range(0, len(X), 8192):
                progress(completed_rows=first, total_rows=height)
                prediction[start:start+8192] = model.predict(X[start:start+8192], model.config.wavelengths_nm)
            labels[first:last][safe] = prediction
            accepted[first:last] = safe
            progress(completed_rows=last, total_rows=height)
        if not accepted.any():
            raise DataError('INFERENCE_EMPTY', '没有通过完整邻域和质量筛选的像元')
        reasons[accepted]=0
        save_arrays(folder / f'{index}.npz', prediction_map=labels, valid_mask=accepted, exclusion_reason=reasons)
        palette = class_palette(model.classes_)
        rgb = np.full((height, width, 3), 224, np.uint8)
        for label in model.classes_:
            rgb[accepted & (labels == label)] = palette[str(label)]
        image = Image.fromarray(rgb)
        image.thumbnail((1200, 1200), Image.Resampling.NEAREST)
        image.save(storage.resolve_write(folder / f'{index}.png', kind='INFERENCE_MAP'))
        counts={name:int((reasons==code).sum()) for code,name in ((1,'brightness'),(2,'side_edges'),(3,'quality_or_neighborhood'),(4,'image_boundary'))}
        return labels[accepted], int((~accepted).sum()), height*width, {'shape':[height,width],'edges':{'left':left,'right':right},
                'exclusion_counts':counts,'preview_wavelengths_nm':preview_waves}

    def result(self, model_id, run_id):
        if self.status(model_id, run_id)['status'] != 'succeeded':
            raise DataError('INFERENCE_NOT_READY', '推理尚未成功完成')
        return json.loads((self.folder(model_id, run_id) / 'result.json').read_text('utf-8'))

    def artifact(self, model_id, run_id, name):
        result = self.result(model_id, run_id)
        item = result['artifacts'].get(name)
        path = self.folder(model_id, run_id) / name
        if not item or Path(name).name != name or not path.is_file() or sha256(path) != item['sha256']:
            raise DataError('INFERENCE_ARTIFACT_CHANGED', '推理产物缺失或校验失败')
        return path

    def plot(self, model_id, run_id, index, kind='prediction'):
        if kind not in {'prediction','input'}:
            raise DataError('INFERENCE_ARTIFACT_CHANGED','不支持的预览类型')
        name=f'{index}.png' if kind=='prediction' else f'{index}_input.png'
        data = self.artifact(model_id, run_id, name).read_bytes()
        if len(data) > 4*1024*1024:
            raise DataError('INFERENCE_RESULT_TOO_LARGE', '分类预览超过显示上限')
        return {'png_base64': base64.b64encode(data).decode('ascii')}

    def export(self, model_id, run_id):
        result = self.result(model_id, run_id)
        if sum(item['bytes'] for item in result['artifacts'].values()) > 64*1024*1024:
            raise DataError('INFERENCE_RESULT_TOO_LARGE', '推理包超过64MiB导出上限；归档产物仍保留')
        output = BytesIO()
        with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
            archive.writestr('result.json', json.dumps(result, ensure_ascii=False, indent=2))
            for name in result['artifacts']:
                archive.write(self.artifact(model_id, run_id, name), name)
        data = output.getvalue()
        if len(data) > 64*1024*1024:
            raise DataError('INFERENCE_RESULT_TOO_LARGE', '推理包超过64MiB导出上限')
        return data
