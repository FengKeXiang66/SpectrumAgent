from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from spectrumagent.data import SpectrumDataSet


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportRequest(Envelope):
    path: Annotated[str, Field(min_length=1)]
    raw: StrictBool = False
    data_path: str | None = None


class DatasetRecord(Envelope):
    id: UUID
    dataset: SpectrumDataSet
    existing: bool


class ImportSummary(Envelope):
    total: int
    imported: int
    existing: int


class ImportResponse(Envelope):
    datasets: list[DatasetRecord]
    summary: ImportSummary


class RegionRequest(Envelope):
    l0: Annotated[int, Field(strict=True, ge=0)] = 0
    l1: Annotated[int, Field(strict=True, gt=0)] = 32
    s0: Annotated[int, Field(strict=True, ge=0)] = 0
    s1: Annotated[int, Field(strict=True, gt=0)] = 32
    raw: StrictBool | None = None


class BandResponse(Envelope):
    id: UUID
    band: int
    shape: tuple[int, int]
    raw: bool
    values: list[list[float | int]]


class RegionResponse(Envelope):
    id: UUID
    shape: tuple[int, int, int]
    raw: bool
    values: list[list[list[float | int]]]


class PreviewResponse(Envelope):
    id: UUID
    band: int
    width: int
    height: int
    mime: str = "image/png"
    png_base64: str
