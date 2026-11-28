"""One explicit physical definition for Study, training configuration and reports."""
import hashlib
import json

from .schema import SampleDefinition


def specification(value):
    return SampleDefinition.model_validate({key:value[key] for key in ('mode','minimum_valid','mapping') if key in value}).model_dump(mode='json')


def definition_for(config, *, training_only=False):
    from .sample_evaluation import source_ref
    if config.sample_evaluation is None: return None
    definition = config.sample_evaluation.model_dump(mode='json')
    if definition['mode'] == 'MIXED': return definition
    roles = ('train',) if training_only else ('train','test')
    if any(getattr(config,role).kind != 'roi_images' for role in roles):
        raise ValueError('实物评价只支持有原图来源的ENVI；NPZ groups不能认定为实物编号')
    members = [member for role in roles for member in getattr(config,role).members]
    refs = {source_ref(member.header_path) for member in members}
    if definition['mode'] == 'MAPPED':
        if not definition['mapping']:
            # Empty mapping explicitly means reuse the complete declared sample_id
            # table, never a batch field or the implicit HDR-as-ID fallback.
            if any(not member.sample_id.strip() or member.sample_id == member.header_path for member in members):
                raise ValueError('MAPPED需要完整实物分组表，缺省HDR路径不能作为已确认实物编号')
            definition['mapping'] = [dict(source_ref=source_ref(m.header_path),sample_id=m.sample_id.strip()) for m in members]
            definition['mapping'] = list({row['source_ref']:row for row in definition['mapping']}.values())
        mapped = {row['source_ref'] for row in definition['mapping']}
        if not refs <= mapped or not training_only and mapped != refs:
            raise ValueError('实物分组表未完整对应当前原图，请核对数据范围和sample_id')
        definition['mapping'] = [dict(source_ref=row['source_ref'],sample_id=row['sample_id'].strip()) for row in definition['mapping']]
    return definition


def normalize_config(config, *, training_only=False):
    value = definition_for(config, training_only=training_only)
    return config.model_copy(update={'sample_evaluation':SampleDefinition.model_validate(value)}) if value else config


def training_digest(config, definition):
    from .sample_evaluation import source_ref
    if definition is None: return None
    value = specification(definition)
    refs = {source_ref(m.header_path) for m in config.train.members} if config.train.kind == 'roi_images' else set()
    value['mapping'] = sorted((row for row in value['mapping'] if row['source_ref'] in refs),key=lambda row:row['source_ref'])
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
