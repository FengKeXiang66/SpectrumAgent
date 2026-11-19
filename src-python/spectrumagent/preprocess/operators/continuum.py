"""B09 fixed endpoints and automatic upper hull on the band-index plane."""
import numpy as np


def upper_hull(row):
    vertices = []
    for index in range(len(row)):
        while len(vertices) >= 2:
            a, b = vertices[-2:]
            cross = (b-a)*(row[index]-row[a])-(row[b]-row[a])*(index-a)
            if cross < 0:
                break
            vertices.pop()
        vertices.append(index)
    return vertices


def continuum(spectra, params):
    x = np.asarray(spectra, dtype=np.float64)
    output = np.full_like(x, np.nan)
    vertices_per_spectrum = []
    zero = 0
    for i, row in enumerate(x):
        if not np.isfinite(row).all():
            vertices_per_spectrum.append(None)
            continue
        vertices = upper_hull(row) if params["method"] == "convex_hull" else sorted({0, len(row)-1})
        baseline = np.interp(np.arange(len(row)), vertices, row[vertices])
        zero += int((baseline == 0).sum())
        np.divide(row, baseline, out=output[i], where=baseline != 0)
        vertices_per_spectrum.append(len(vertices))
    return output, {"method": params["method"], "hull_vertex_counts": vertices_per_spectrum,
                    "zero_continuum_bands": zero}
