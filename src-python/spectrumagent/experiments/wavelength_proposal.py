"""Read ENVI wavelength metadata and verify a common grid before review."""
from math import ceil, floor, log10
import re

import numpy as np

from spectrumagent.data import DataError
from spectrumagent.data.readers import open_envi
from .inputs import WAVELENGTH_UNITS, mapping_weights

ADOPT = re.compile(r'(?:采用波长建议|采用建议并更新方案)(?:\s+(\d+))?[。！!]*')
CROP = re.compile(
    r'(?:请\s*)?(?:(?:把|将)\s*)?(?:(?:实验方案|(?:目标)?(?:波长|波段)(?:范围)?)\s*)?'
    r'(?:改[为成]|设(?:置)?为|调整[为到]|裁(?:剪)?[为到至])\s*[:：]?\s*'
    r'(\d+(?:\.\d+)?)\s*[-－−–—~～到至]\s*(\d+(?:\.\d+)?)\s*(?:nm|纳米)[。！!]*', re.I)
AUTO_STUDY = re.compile(r'训练集内自动寻优\s+(\d+)\s+折数\s+(\d+)')


def recommend(sides, unit, check=None, *, grid=None):
    axes = {}
    distinct = set()
    for role, rows in sides.items():
        role_axes = []
        for row in rows:
            if check:
                check()
            info = open_envi(row['hdr'], row['img'], raw=True)
            declared = str(info.metadata.get('wavelength units', '')).lower()
            if declared and declared not in WAVELENGTH_UNITS[unit]:
                raise ValueError('HDR 的波长单位与草稿不一致，请先核对波长单位。')
            values = np.sort(np.asarray(info.wavelengths, dtype=float) * (1000 if unit == 'um' else 1))
            if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all() or np.any(np.diff(values)<=0):
                raise ValueError('部分 HDR 缺少有效的原始波长，无法生成建议。')
            axis = tuple(values)
            role_axes.append(axis)
            distinct.add(axis)
        axes[role] = dict(files=len(rows), axes=len(set(role_axes)),
                          start=min(axis[0] for axis in role_axes), stop=max(axis[-1] for axis in role_axes),
                          max_step=max(float(np.diff(axis).max()) for axis in set(role_axes)))
    low = max(axis[0] for axis in distinct)
    high = min(axis[-1] for axis in distinct)
    max_step = max(value['max_step'] for value in axes.values())
    details = dict(sides=axes, overlap_start=low, overlap_stop=high, max_step=max_step)
    if high <= low:
        return dict(details, problem='训练与测试原图没有共同波长范围，无法自动对齐。')
    if grid:
        step, window, tolerance, origin, bounds = grid
        start, stop = bounds
        if not low <= start < stop <= high:
            return dict(details, problem='请在波长详情给出的共同范围内选择起止点。')
        first, last = ceil((start-origin)/step-1e-9), floor((stop-origin)/step+1e-9)
    else:
        minimum_step = max(max_step, (high-low)/9999)
        base = 10.**floor(log10(minimum_step))
        step = next(value*base for value in (1,2,5,10) if value*base >= minimum_step)
        window = tolerance = step
        origin = 0.
        first, last = ceil(low/step), floor(high/step)
    if last <= first:
        return dict(details, problem='共同波长范围太窄，无法按建议步长取到两个等间距波段。')
    if last-first>=10000:
        return dict(details, problem='目标网格最多支持 10000 个波段，请缩小范围。')
    target = origin + np.arange(first,last+1)*step
    try:
        for axis in distinct:
            if check:
                check()
            mapping_weights(axis, target, window, tolerance)
    except DataError:
        return dict(details, problem='部分原图无法映射到共同网格，请检查波段或缩小范围。')
    return dict(details, start=float(target[0]), stop=float(target[-1]), step=step, bands=len(target),
                window=window, tolerance=tolerance)


def grid_label(value):
    return (f"{value['start']:g}–{value['stop']:g} nm · 步长 {value['step']:g} nm（{value['bands']} 波段）"
            f" · 窗口/容差 {value['window']:g} nm")
