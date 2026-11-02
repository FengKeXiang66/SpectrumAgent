import numpy as np
from PIL import Image, ImageDraw
from skimage.measure import find_contours

def polygon(mask):
    padded = np.pad(mask, 1)
    contours = find_contours(padded, .5, fully_connected='low', positive_orientation='low')
    assert len(contours) == 1, len(contours)
    points = []
    for row, col in contours[0]:
        candidates = sorted({(int(np.floor(row)), int(np.floor(col))),
                             (int(np.ceil(row)), int(np.ceil(col)))})
        inside = [(r, c) for r, c in candidates if padded[r, c]]
        assert len(inside) == 1, (row, col, inside)
        r, c = inside[0]
        point = [c - 1, r - 1]
        if not points or point != points[-1]:
            points.append(point)
    if len(points) > 1 and points[-1] == points[0]:
        points.pop()
    while len(points) < 3:
        points.append(points[-1])
    image = Image.new('1', (mask.shape[1], mask.shape[0]))
    ImageDraw.Draw(image).polygon([tuple(p) for p in points], fill=1)
    out = np.asarray(image)
    return points, int(np.count_nonzero(mask != out)), out

rect = np.zeros((282, 1945), dtype=bool); rect[265:280, 1925:1943] = True
lshape = np.ones((3, 5), dtype=bool); lshape[:2, 3:] = False
ring = np.zeros((30, 40), dtype=bool); ring[2:28, 2:38] = True; ring[10:15, 15:20] = False
ring[2:10, 15] = False
for name, mask in [('rectangle', rect), ('L', lshape), ('slotted_hole', ring), ('pixel', np.ones((1, 1), bool)), ('line', np.ones((1, 5), bool))]:
    points, difference, out = polygon(mask)
    print(name, 'area', int(mask.sum()), 'difference', difference, 'vertices', len(points))
    assert difference == 0
