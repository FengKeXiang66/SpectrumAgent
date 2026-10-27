"""TASK-06 display mappings. Feature selection is our own algorithm, not a
reimplementation of the closed-source DatasetStatistic.dll from SHIS.
"""
import base64
import math
import struct
import zlib

import numpy as np
from spectrumagent.data import DataError

FEATURECOLOR_ALGO_VERSION = 1


def select_feature_bands(cube_reader, shape, wavelengths):
    """Our deterministic TASK-06 algorithm; SHIS's DLL has no source to copy.

    rho and wavelengths use band indices; corr uses candidate positions only.
    """
    height, width, bands = shape
    if bands < 3:
        raise DataError('INVALID_BANDS', '伪彩至少需要三个波段')
    stride = max(1, math.ceil(height/128))
    sample = np.asarray(cube_reader.read_subimage(list(range(0, height, stride)),
                        list(range(0, width, stride)), list(range(bands))), dtype=np.float64)
    with np.errstate(invalid='ignore', divide='ignore'):
        sigma = np.std(sample, axis=(0, 1), dtype=np.float64)
        noise = np.std(np.diff(sample, axis=1), axis=(0, 1), dtype=np.float64)/np.sqrt(2.)
        rho = sigma/(noise+1e-12)
    candidates = np.flatnonzero(rho >= np.median(rho))
    axis = np.asarray(wavelengths if wavelengths else range(bands), dtype=np.float64)
    fallback = not bool(wavelengths)
    best, best_score = None, -np.inf
    if len(candidates) >= 3:
        # Select columns BEFORE correlation. A BxB matrix indexed by positions
        # can silently produce plausible but wrong results even below 0.75.
        x = sample.reshape(-1, bands)[:, candidates]
        with np.errstate(invalid='ignore', divide='ignore'):
            corr = np.abs(np.corrcoef(x.T))
        assert corr.shape == (len(candidates), len(candidates))
        corr = np.nan_to_num(corr, nan=0.0)
        for i in range(len(candidates)-2):
            j, k = np.triu_indices(len(candidates)-i-1, k=1)
            j, k = j+i+1, k+i+1
            permitted = axis[candidates[k]]-axis[candidates[i]] >= .15*(axis[-1]-axis[0])
            j, k = j[permitted], k[permitted]
            if not len(j):
                continue
            scores = rho[candidates[i]]+rho[candidates[j]]+rho[candidates[k]]-2.5*(corr[i, j]+corr[i, k]+corr[j, k])/3
            winner = int(np.argmax(scores))
            # Traversal is lexicographic, so equal scores keep smaller a.
            if scores[winner] > best_score:
                best_score = scores[winner]
                best = (int(candidates[i]), int(candidates[j[winner]]), int(candidates[k[winner]]))
    if best is None:
        fallback = True
        if wavelengths:
            selected = [int(np.argmin(np.abs(axis-(axis[0]+p*(axis[-1]-axis[0]))))) for p in (0., .5, 1.)]
        else:
            selected = [int(p*(bands-1)+.5) for p in (0., .5, 1.)]
        if len(set(selected)) < 3:
            selected = [0, (bands-1)//2, bands-1]
        best = tuple(sorted(selected))
    a, b, c = best
    return c, b, a, fallback


def map_values(values, stretch):
    """One range shared by the entire input, including all RGB channels."""
    finite = np.isfinite(values)
    result = np.zeros(values.shape, dtype=np.uint8)
    if not finite.any():
        return result
    selected = values[finite]
    low, high = (np.percentile(selected, [2, 98]) if stretch == 'auto'
                 else (selected.min(), selected.max()))
    if high == low:
        return result
    scaled = np.clip((selected-low)/(high-low)*255, 0, 255)
    # none deliberately preserves HEAD's truncation; auto is a new round path.
    result[finite] = np.rint(scaled).astype(np.uint8) if stretch == 'auto' else scaled.astype(np.uint8)
    return result


def compose_rgb(r, g, b, stretch):
    # Independent channel stretching amplifies low-variance channel noise to
    # full range. Map the joint distribution once, then only assemble RGB.
    rgb = map_values(np.stack((r, g, b), axis=2), stretch)
    height, width, _ = rgb.shape

    def chunk(tag, data):
        body = tag+data
        return struct.pack('>I', len(data))+body+struct.pack('>I', zlib.crc32(body))

    rows = b''.join(b'\x00'+row.tobytes() for row in rgb)
    data = (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows))+chunk(b'IEND', b''))
    return base64.b64encode(data).decode('ascii')


CONCENTRATION_PALETTE = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]]


def concentration_colors(values, low, high):
    """Fixed training-Y range; callers must disclose clipped values separately."""
    values = np.asarray(values, dtype=np.float64)
    if not np.isfinite(values).all() or not np.isfinite([low, high]).all() or high < low:
        raise ValueError("finite values and ordered fixed range required")
    scaled = np.full(values.shape, .5) if high == low else np.clip((values-low)/(high-low), 0, 1)
    palette = np.asarray(CONCENTRATION_PALETTE)
    positions = np.linspace(0, 1, len(palette))
    return np.stack([np.rint(np.interp(scaled, positions, palette[:, channel])).astype(np.uint8)
                     for channel in range(3)], axis=-1)
