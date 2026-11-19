"""Typed conversational patches; spectra and local paths stay in the service."""
from typing import Annotated, Literal, Union

from pydantic import Field, FiniteFloat

from . import ToolInput, NoArguments, Reference
from ..tool_context import owner_session
from spectrumagent.experiments.schema import L2, Center, Standard, SNV, Metric


class ArchiveDraft(ToolInput):
    kind: Literal['npz']
    source_refs: list[Reference] | None = None
    spectra_key: str | None = None
    labels_key: str | None = None
    wavelengths_key: str | None = None
    input_stage: Literal['spectra', 'neighborhood_mean'] | None = None
    neighborhood: int | None = None
    evaluation_unit: Literal['spectrum', 'center_pixel'] | None = None


class ImageReference(ToolInput):
    header_ref: Reference
    roi_ref: Reference
    sample_id: Reference
    data_ref: Reference | None = None
    centers_ref: Reference | None = None


class QualityDraft(ToolInput):
    min_mean: FiniteFloat | None = None
    min_std: FiniteFloat | None = None
    max_zero_fraction: FiniteFloat | None = None
    saturation: FiniteFloat | None = None


class ImageDraft(ToolInput):
    kind: Literal['roi_images']
    members: list[ImageReference] | None = None
    neighborhood: int | None = None
    wavelength_unit: Literal['nm', 'um'] | None = None
    mapping_window_nm: FiniteFloat | None = None
    nearest_tolerance_nm: FiniteFloat | None = None
    quality: QualityDraft | None = None
    evaluation_unit: Literal['center_pixel'] | None = None


class SGDraft(ToolInput):
    op: Literal['savgol']
    window: int | None = None
    polyorder: int | None = None
    derivative: int | None = None
    delta_nm: FiniteFloat | None = None
    mode: Literal['interp', 'mirror', 'constant', 'nearest', 'wrap'] | None = None


class ModelDraft(ToolInput):
    n_components: int | None = None
    scale: bool | None = None
    max_iter: int | None = None
    tol: FiniteFloat | None = None


class PCADraft(ToolInput):
    op: Literal['pca']
    n_components: int | None = None


class ClassName(ToolInput):
    label: int
    name: Reference


class ArchiveAxis(ToolInput):
    kind: Literal['archive']
    role: Literal['train', 'test']


class GridAxis(ToolInput):
    kind: Literal['grid']
    start_nm: FiniteFloat
    stop_nm: FiniteFloat
    step_nm: Annotated[FiniteFloat, Field(gt=0)]


class DraftUpdate(ToolInput):
    expected_revision: Annotated[int, Field(ge=0)]
    reset: bool = False
    name: str | None = None
    train: Annotated[Union[ArchiveDraft, ImageDraft], Field(discriminator='kind')] | None = None
    test: Annotated[Union[ArchiveDraft, ImageDraft], Field(discriminator='kind')] | None = None
    classes: list[ClassName] | None = None
    preprocessing: list[Annotated[Union[SGDraft, L2, Center, Standard, SNV, PCADraft], Field(discriminator='op')]] | None = None
    model: ModelDraft | None = None
    axis: Annotated[Union[ArchiveAxis, GridAxis], Field(discriminator='kind')] | None = None
    additional_metrics: list[Metric] | None = None
    test_usage: Literal['independent_test', 'development_regression'] | None = None


class InspectInput(ToolInput):
    source_ref: Reference


def register_experiments(registry, dialogue):
    registry.experiment_dialogue = dialogue
    registry.register('experiments.draft_get', NoArguments,
                      '读取本会话的训练测试实验草稿、修订号、方案与待补字段',
                      lambda args: dialogue.view(owner_session.get()))
    registry.register('experiments.input_inspect', InspectInput,
                      '检查用户提供的输入源引用；只返回文件类型、NPZ字段及维度，不返回谱值、路径或材质猜测',
                      lambda args: dialogue.inspect(owner_session.get(), args.source_ref))
    registry.register('experiments.draft_update', DraftUpdate,
                      '增量保存用户明确给出的实验信息，不启动计算。嵌套字段合并，preprocessing和classes整组替换；'
                      'SG缺参允许留空以便追问。改变步骤时保留已确认参数，reset仅用于用户要求新实验。',
                      lambda args: dialogue.update(owner_session.get(), args))
