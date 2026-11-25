"""Read a bounded subset of a scene to propose auditable foreground parameters."""
import base64
from io import BytesIO
import math

import numpy as np
from PIL import Image

from spectrumagent.data import DataError
from .inference import BrightnessEdges, envi_mapping, filtered_files


def suggest(spec, wavelengths, sample=None):
    files, excluded = filtered_files(spec)
    path = sample.resolve() if sample else files[0]
    if path not in files:
        raise DataError('INFERENCE_PROBE_SOURCE','样本图必须在本次待推理原图清单内')
    dataset, _ = envi_mapping(path,spec,wavelengths)
    height,width,_ = dataset.shape
    source = np.asarray(dataset.wavelengths)*(1000 if spec.wavelength_unit=='um' else 1)
    target = np.asarray(wavelengths)
    if len(target) > 2:
        last = len(target)-1
        if last-1 <= 6:
            positions = np.arange(1,last)
        else:
            positions = np.linspace(.15*last,.85*last,6).round().astype(int).clip(1,last-1)
    else:
        # With fewer than three channels there is no interior to sample.
        positions = np.arange(len(target))
    indices = np.unique(np.abs(source[:,None]-target[positions]).argmin(axis=0))
    probe_waves = source[indices]
    rows = np.unique(np.linspace(0,height-1,min(128,height)).round().astype(int))
    samples = np.stack([dataset.read_region(int(row),int(row)+1,0,width)[0][:,indices]
                        for row in rows]).astype(float) / float(dataset.metadata['scale_factor'])
    levels = np.median(samples,axis=2)
    search = int(min(128,width//5))
    inner = levels[:,search:width-search or width]
    values = inner[np.isfinite(inner)]
    if len(values) < 2:
        raise DataError('INFERENCE_PROBE_EMPTY','探查样本有效亮度不足')
    q = np.quantile(values,[.02,.05,.25,.5,.95,.995])
    low, high = float(q[0]),float(q[-1])
    if math.isclose(low,high,abs_tol=1e-12,rel_tol=1e-8):
        return {'sample':path.name,'rows':len(rows),'width':width,'suggestion':{'mode':'none'},
                'note':'采样亮度近乎均匀，建议先关闭亮度／边缘筛选。','excluded_files':excluded}
    hist, bins = np.histogram(np.clip(values,low,high),bins=64,range=(low,high))
    centers = (bins[:-1]+bins[1:])/2
    weight = np.cumsum(hist,dtype=float)
    cumulative = np.cumsum(hist*centers)
    valid = (weight>0)&(weight<weight[-1])
    between = np.zeros_like(weight)
    between[valid] = (cumulative[-1]*weight[valid]-cumulative[valid]*weight[-1])**2 / (
        weight[valid]*(weight[-1]-weight[valid]))
    threshold = float(bins[int(np.argmax(between))+1])
    abnormal = ((levels<low)|(levels>high)|~np.isfinite(levels)).mean(axis=0)
    central = abnormal[search:width-search or width]
    fraction = float(np.clip(np.quantile(central,.98)+.25,.5,.95))
    left = int(np.flatnonzero(abnormal[:search]>=fraction).max(initial=-1)+1)
    right = int(np.flatnonzero(abnormal[::-1][:search]>=fraction).max(initial=-1)+1)
    suggestion = BrightnessEdges(mode='brightness_edges',wavelengths_nm=probe_waves.tolist(), threshold=threshold,
                                 left_min=0,right_min=0,edge_search_columns=search,edge_bad_fraction=fraction,
                                 edge_low=low,edge_high=high)
    allowed = np.isfinite(levels)&(levels>threshold)
    allowed[:,:left] = False
    if right:
        allowed[:,-right:] = False
    gray = np.uint8(np.nan_to_num(np.clip((levels-low)/(high-low),0,1))*220)
    rgb = np.repeat(gray[:,:,None],3,axis=2)
    rgb[~allowed] = [0,0,0]
    rgb[:,:left] = [224,224,224]
    if right:
        rgb[:,-right:] = [224,224,224]
    image = Image.fromarray(rgb)
    image.thumbnail((900,300),Image.Resampling.NEAREST)
    buffer = BytesIO()
    image.save(buffer,format='PNG')
    return {'sample':path.name,'rows':len(rows),'width':width,'suggestion':suggestion.model_dump(mode='json'),
            'brightness_quantiles':dict(zip(('p02','p05','p25','p50','p95','p995'),map(float,q))),
            'estimated_left':left,'estimated_right':right,'sample_retained':float(allowed.mean()),
            'png_base64':base64.b64encode(buffer.getvalue()).decode('ascii'),'excluded_files':excluded,
            'note':'按均匀抽取的图像行和内部波段估计亮度分位数与边缘异常列。黑色为低亮度筛除，浅灰为侧边；这是采样预览。'}
