"""Tiny isolated sources in the same ordinal layout as the reported duplicates."""
import numpy as np


PAIRS = ("20260804210313_15", "20260804210353_75",
         "20260804210443_152", "20260804210509_189")


def catalog_rows():
    return [(f"id-{i}", name, raw) for i, (name, raw) in enumerate(
        [(f"unique-{i}", 0) for i in range(7)]
        + [(name, 0) for name in PAIRS] + [(name, 1) for name in PAIRS], 1)]


def seed_catalog(registry, root):
    root.mkdir(parents=True, exist_ok=True)
    for _, name, raw in catalog_rows():
        header = root / f"{name}.hdr"
        if not header.exists():
            header.with_suffix(".img").write_bytes(np.arange(12, dtype=np.float32).tobytes())
            header.write_text("ENVI\nsamples=2\nlines=2\nbands=3\ndata type=4\n"
                              "interleave=bip\nbyte order=0\nreflectance scale factor=10000\n", "utf-8")
        result = registry.import_path(str(header), raw=bool(raw))
    return result.all_datasets
