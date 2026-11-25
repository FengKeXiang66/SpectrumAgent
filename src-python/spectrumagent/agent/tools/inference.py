from typing import Annotated, Literal, Union
from pydantic import Field
from . import ToolInput, Reference, NoArguments
from .experiments import QualityDraft, InspectInput
from ..tool_context import owner_session
from spectrumagent.experiments.inference import NoForeground


class BrightnessDraft(ToolInput):
    mode: Literal['brightness_edges']
    wavelengths_nm: list[float] | None = None
    threshold: float | None = None
    left_min: int | None = None
    right_min: int | None = None
    edge_search_columns: int | None = None
    edge_bad_fraction: float | None = None
    edge_low: float | None = None
    edge_high: float | None = None


class NPZDraft(ToolInput):
    kind: Literal['npz']
    source_refs: list[Reference] | None = None
    spectra_key: str | None = None
    wavelengths_key: str | None = None
    input_stage: Literal['spectra','neighborhood_mean'] | None = None
    neighborhood: int | None = None
    evaluation_unit: Literal['spectrum','center_pixel'] | None = None


class ExclusionDraft(ToolInput):
    name_fragments: list[str] | None = None
    prefixes: list[str] | None = None


class ENVIDraft(ToolInput):
    kind: Literal['envi']
    source_refs: list[Reference] | None = None
    wavelength_unit: Literal['nm','um'] | None = None
    mapping_window_nm: float | None = None
    nearest_tolerance_nm: float | None = None
    quality: QualityDraft | None = None
    foreground: Annotated[Union[NoForeground,BrightnessDraft],Field(discriminator='mode')] | None = None
    exclusions: ExclusionDraft | None = None
    exclusions_ref: Reference | None = None


class InferenceUpdate(ToolInput):
    expected_revision: Annotated[int,Field(ge=0)]
    reset: bool = False
    model_id: Reference | None = None
    input: Annotated[Union[NPZDraft,ENVIDraft],Field(discriminator='kind')] | None = None


class InlineInferenceAdjustment(ToolInput):
    expected_revision: Annotated[int,Field(ge=0)]
    quality: QualityDraft | None = None
    foreground: Annotated[Union[NoForeground,BrightnessDraft],Field(discriminator='mode')] | None = None


def register_inference(registry, dialogue):
    registry.register('experiments.inference_get',NoArguments,'读取本会话推理草稿、修订号、模型与待补字段；不执行预测',
                      lambda args:dialogue.view(owner_session.get()))
    registry.register('experiments.inference_inspect',InspectInput,'检查I输入源引用的NPZ字段及维度、NPZ/HDR数量，不返回谱值、标签或路径',
                      lambda args:dialogue.inspect(owner_session.get(),args.source_ref))
    registry.register('experiments.inference_update',InferenceUpdate,
                      '只保存用户给出的推理输入定义，不启动计算；复用归档模型的已拟合预处理。未提及的可选字段省略，null不删除既有值（saturation除外）；评价单位和邻域自动继承。新推理用reset=true；SG等模型参数不能修改。',
                      lambda args:dialogue.update(owner_session.get(),args))
