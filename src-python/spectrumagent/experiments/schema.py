"""The complete numerical contract; dataset roles are never inferred from names."""
from typing import Annotated, Literal, Union

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class ArchiveInput(InputModel):
    kind: Literal["npz"]
    paths: Annotated[list[str], Field(min_length=1)]
    spectra_key: str
    labels_key: str = "y"
    wavelengths_key: str = "wavelengths_nm"
    input_stage: Literal["spectra", "neighborhood_mean"]
    neighborhood: Annotated[int, Field(ge=1)]
    evaluation_unit: Literal["spectrum", "center_pixel"]

    @model_validator(mode="after")
    def stage_matches(self):
        if self.neighborhood % 2 != 1:
            raise ValueError("neighborhood 必须为正奇数")
        if self.input_stage == "spectra" and self.neighborhood != 1:
            raise ValueError("光谱矩阵无法重新计算空间邻域，请提供已平均光谱或原图")
        return self


class ImageMember(InputModel):
    header_path: str
    roi_path: str
    data_path: str | None = None
    centers_path: str | None = None
    sample_id: str


class Quality(InputModel):
    min_mean: FiniteFloat
    min_std: Annotated[FiniteFloat, Field(ge=0)]
    max_zero_fraction: Annotated[FiniteFloat, Field(ge=0, le=1)]
    saturation: FiniteFloat | None


class ImageInput(InputModel):
    kind: Literal["roi_images"]
    members: Annotated[list[ImageMember], Field(min_length=1)]
    neighborhood: Annotated[int, Field(ge=1)]
    wavelength_unit: Literal["nm", "um"]
    mapping_window_nm: Annotated[FiniteFloat, Field(gt=0)]
    nearest_tolerance_nm: Annotated[FiniteFloat, Field(ge=0)]
    quality: Quality
    evaluation_unit: Literal["center_pixel"] = "center_pixel"

    @field_validator("neighborhood")
    @classmethod
    def odd(cls, value):
        if value % 2 != 1:
            raise ValueError("neighborhood 必须为正奇数")
        return value


DatasetInput = Annotated[Union[ArchiveInput, ImageInput], Field(discriminator="kind")]


class SG(InputModel):
    op: Literal["savgol"]
    window: Annotated[int, Field(gt=0)]
    polyorder: Annotated[int, Field(ge=0)]
    derivative: Annotated[int, Field(ge=0, le=2)]
    delta_nm: Annotated[FiniteFloat, Field(gt=0)]
    mode: Literal["interp", "mirror", "constant", "nearest", "wrap"] = "interp"

    @model_validator(mode="after")
    def valid_window(self):
        if self.window % 2 != 1 or not self.derivative <= self.polyorder < self.window:
            raise ValueError("SG要求奇数窗口，derivative <= polyorder < window")
        return self


class L2(InputModel):
    op: Literal["l2"]
    epsilon: Annotated[FiniteFloat, Field(gt=0)] = 1e-12


class Center(InputModel):
    op: Literal["center"]


class Standard(InputModel):
    op: Literal["standard_scale"]


class SNV(InputModel):
    op: Literal["snv"]
    ddof: Literal[0, 1] = 1


class PCA(InputModel):
    op: Literal["pca"]
    n_components: Annotated[int, Field(gt=0)]


Step = Annotated[Union[SG, L2, Center, Standard, SNV, PCA], Field(discriminator="op")]


class PLSDAConfig(InputModel):
    n_components: Annotated[int, Field(gt=0)]
    scale: bool
    max_iter: Annotated[int, Field(gt=0)]
    tol: Annotated[FiniteFloat, Field(gt=0)] = 1e-6


Metric = Literal["kappa", "weighted_f1", "balanced_accuracy"]


class ExperimentConfig(InputModel):
    schema_version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=200)]
    train: DatasetInput
    test: DatasetInput
    wavelengths_nm: Annotated[list[FiniteFloat], Field(min_length=2)]
    classes: dict[int, str]
    preprocessing: list[Step]
    model: PLSDAConfig
    additional_metrics: list[Metric] = Field(default_factory=list)
    test_usage: Literal["independent_test", "development_regression"]
    notes: str = ""

    @field_validator("classes", mode="before")
    @classmethod
    def json_class_keys(cls, value):
        # JSON object keys are strings even when class labels are integers.
        if isinstance(value, dict):
            converted = {int(k) if isinstance(k, str) and k.lstrip("-").isdigit() else k: v for k, v in value.items()}
            if len(converted) != len(value):
                raise ValueError("类别编号重复")
            return converted
        return value

    @model_validator(mode="after")
    def consistent(self):
        if not np.all(np.diff(self.wavelengths_nm) > 0):
            raise ValueError("目标波长须有限且严格递增，单位nm")
        if (len(self.classes) < 2 or len(set(self.classes.values())) != len(self.classes)
                or any(not name.strip() for name in self.classes.values())):
            raise ValueError("需要至少两个名称互异的类别")
        if self.train.neighborhood != self.test.neighborhood:
            raise ValueError("训练与测试的空间邻域定义必须一致")
        if self.train.evaluation_unit != self.test.evaluation_unit:
            raise ValueError("训练与测试的评价单位必须一致")
        axis = np.asarray(self.wavelengths_nm)
        for step in self.preprocessing:
            if step.op == "savgol":
                if axis is None or not np.allclose(np.diff(axis), step.delta_nm, rtol=1e-8, atol=1e-10):
                    raise ValueError("SG的delta_nm须匹配等间隔波长轴，且SG须在PCA前执行")
                if step.window > len(axis):
                    raise ValueError("SG窗口不得大于输入波段数")
            if step.op == "pca":
                axis = None
        return self
