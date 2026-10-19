from pathlib import Path

from spectral.io import envi

from ..errors import DataError
from ..model import MemmapAccess, SpectrumDataSet
from .header import classic, key_name, normalize, read_text, resolve_data, validate_size


class EnviReader:
    def open(self, header_path, data_path=None, *, raw=False) -> SpectrumDataSet:
        path = Path(header_path).resolve()
        if path.suffix.lower() != ".hdr":
            raise DataError("HEADER_INVALID", "EnviReader输入必须是.hdr")
        header = normalize(classic(read_text(path)), require_interleave=True)
        data = resolve_data(path, header, data_path)
        validate_size(data, header)  # Before spectral can create any mapping/read.
        # SpectralLibrary.open performs np.fromfile; it is not a lazy raster reader.
        file_type = next((value for key, value in header.metadata.items() if key_name(key) == "filetype"), "ENVI Standard")
        if str(file_type) != "ENVI Standard":
            raise DataError("HEADER_INVALID", "本阶段只接入ENVI Standard栅格数据")
        try:
            # spectral.open_image's ENVI entry; explicit image preserves our agreed
            # path priority even when several sibling extensions coexist.
            image = envi.open(str(path), image=str(data))
            if tuple(image.shape) != header.shape or image.dtype != header.dtype:
                raise DataError("HEADER_INVALID", "spectral解析结果与已验证头不一致")
        except DataError:
            raise
        except Exception as exc:
            raise DataError("HEADER_INVALID", "spectral无法解析标准ENVI头", reason=type(exc).__name__) from exc
        def mapping():
            validate_size(data, header)
            return image.asarray()  # DN memmap; never image.load().
        class Access(MemmapAccess):
            def read(self, rows, columns, bands):
                validate_size(data, header)
                return super().read(rows, columns, bands)
        metadata = dict(header.metadata, scale_factor=header.scale, scale_applied=not raw, value_mode="raw_dn" if raw else "reflectance", value_description=f"DN原值，未除scale factor={header.scale:g}" if raw else f"float64，DN / {header.scale:g}", byte_order=0 if header.dtype.byteorder in ("<", "=", "|") else 1, header_offset=header.offset, reader="spectral")
        return SpectrumDataSet(name=path.stem, shape=header.shape, dtype=header.dtype.name, interleave=header.interleave, wavelengths=header.wavelengths, fwhm=header.fwhm, data_path=str(data), header_path=str(path), metadata=metadata).bind(Access(mapping), raw=raw, scale_factor=header.scale)
