"""TASK-06 display mappings. Feature selection is our own algorithm, not a
reimplementation of the closed-source DatasetStatistic.dll from SHIS.
"""
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
