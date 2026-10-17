"""Temporary ENVI/SNV smoke demonstration; deliberately not an operator API."""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock

import numpy as np
from spectral import envi

_sample_lock = Lock()


def ensure_sample(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    header = directory / "smoke-8x8x8.hdr"
    with _sample_lock:
        if not header.exists():
            cube = np.linspace(0.05, 0.95, 8 * 8 * 8, dtype=np.float32).reshape(8, 8, 8)
            envi.save_image(str(header), cube, dtype=np.float32, interleave="bip", ext=".dat")
    return header


@dataclass(frozen=True)
class SmokeResult:
    metrics: dict | None
    completed_blocks: int
    requested_blocks: int
    cancelled: bool

    def cancelled_payload(self) -> dict:
        return {
            "error": "CANCELLED", "detail": "用户取消，已完成结果保留，指标不完整。",
            "status": "cancelled", "metrics_complete": False,
            "completed_blocks": self.completed_blocks,
            "requested_blocks": self.requested_blocks,
            "partial_metrics": self.metrics,
        }


async def run_smoke(header: Path, blocks: int, cancel: Event) -> SmokeResult:
    """Check cancellation before scheduling each block; never cancel only a Future."""
    started = time.perf_counter()

    def read_cube() -> np.ndarray:
        cube = np.asarray(envi.open(str(header)).load(), dtype=np.float64)
        if cube.ndim != 3 or cube.shape[-1] < 2 or not np.isfinite(cube).all():
            raise ValueError("ENVI 冒烟样本必须是有限数值的三维立方体，且至少包含两个波段。")
        return cube

    cube = await asyncio.to_thread(read_cube)
    if blocks > cube.shape[0] * cube.shape[1]:
        raise ValueError("块数不得超过样本像元数。")
    pixels = cube.reshape(-1, cube.shape[-1])
    chunks = np.array_split(pixels, blocks)
    completed = 0
    nan_count = 0
    value_count = 0
    low, high = float("inf"), float("-inf")
    metrics = None

    def compute(chunk: np.ndarray) -> np.ndarray:
        # SNV demonstration only: normalize each pixel across its spectral bands.
        spread = chunk.std(axis=-1, keepdims=True)
        return (chunk - chunk.mean(axis=-1, keepdims=True)) / np.where(spread > 0, spread, 1)

    for chunk in chunks:
        if cancel.is_set():
            return SmokeResult(metrics, completed, blocks, True)
        normalized = await asyncio.to_thread(compute, chunk)
        completed += 1
        nan_count += int(np.isnan(normalized).sum())
        value_count += normalized.size
        finite = normalized[np.isfinite(normalized)]
        if finite.size:
            low, high = min(low, float(finite.min())), max(high, float(finite.max()))
        metrics = {
            "nan_ratio": nan_count / value_count,
            "reflectance_range": [low, high], "bands": int(cube.shape[-1]),
            "shape": list(cube.shape),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        await asyncio.sleep(0)  # give disconnect/cancellation observers a turn
    return SmokeResult(metrics, completed, blocks, cancel.is_set())
