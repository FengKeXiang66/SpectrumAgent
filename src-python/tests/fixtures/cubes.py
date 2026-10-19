"""Construct isolated tiny cubes; never inspect or copy real acquisition files."""
import numpy as np


def cube(directory, *, interleave="bil", dtype="<u2", offset=0, extension=".img", scale=65535):
    directory.mkdir(parents=True, exist_ok=True)
    logical = np.arange(24, dtype=dtype).reshape(2, 3, 4)
    physical = logical if interleave == "bip" else logical.transpose(0, 2, 1) if interleave == "bil" else logical.transpose(2, 0, 1)
    data = directory / ("sample" + extension)
    with data.open("wb") as stream:
        stream.write(b"x" * offset)
        stream.write(physical.tobytes())
    codes = {"u1": 1, "i2": 2, "i4": 3, "f4": 4, "f8": 5, "u2": 12, "u4": 13, "i8": 14, "u8": 15}
    kind = np.dtype(dtype)
    header = directory / "sample.hdr"
    header.write_text(f"ENVI\nsamples=3\nlines=2\nbands=4\ndata type={codes[kind.kind+str(kind.itemsize)]}\ninterleave={interleave}\nbyte order={int(kind.byteorder == '>')}\nheader offset={offset}\nwavelength={{1,2,3,4}}\nfwhm={{0.1,0.2,0.3,0.4}}\nreflectance scale factor={scale}\n", "utf-8")
    return header, data, logical
