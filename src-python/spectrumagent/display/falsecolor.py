"""TASK-06 display mappings. Feature selection is our own algorithm, not a
reimplementation of the closed-source DatasetStatistic.dll from SHIS.
"""
import base64
import struct
import zlib

import numpy as np


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
