"""Shared, explicit identity survives training and report overrides."""
from copy import deepcopy

import pytest

from test_sample_evaluation import application, workspace, roi_config
from spectrumagent.experiments.evaluation_definition import definition_for, training_digest
from spectrumagent.experiments.schema import SampleDefinition, StudySelection
from spectrumagent.experiments.sample_evaluation import source_ref, report_html


def test_config_identity_report_inherits_and_warns_on_override(application,tmp_path):
    service=application.state.experiments
    config=roi_config(tmp_path)
    definition=dict(mode='IMAGE',minimum_valid=100,mapping=[])
    config.sample_evaluation=SampleDefinition.model_validate(definition)
    config.study_selection=StudySelection(study_id='study',evaluation_target='sample',grouping='image',
        scoring='pooled_oof_sample_macro_f1',definition_digest=training_digest(config,definition))
    result=service.run(config);identifier=result['experiment_id']
    assert result['config']['sample_evaluation']==definition
    view=service.sample_evaluations.view(identifier)
    assert view['definition']['mode']=='IMAGE' and view['definition_origin']=='experiment_config'
    assert view['selection_warning'] is None and view['report'] is None
    mapping=[dict(source_ref=s['source_ref'],sample_id='object'+str(i)) for i,s in enumerate(view['sources'])]
    updated=service.sample_evaluations.update(identifier,0,'MAPPED',mapping=mapping)
    assert '与选优时的定义不一致' in updated['selection_warning']
    assert '与选优时的定义不一致' in report_html(updated,result['config']['classes'])
    assert service.sample_evaluations.declared(identifier)['mapping']==mapping


def test_mapped_reuses_declared_sample_table_and_never_hdr_default(tmp_path):
    config=roi_config(tmp_path)
    config.sample_evaluation=SampleDefinition(mode='MAPPED')
    definition=definition_for(config)
    assert len(definition['mapping'])==4
    config.train.members[0].sample_id=config.train.members[0].header_path
    with pytest.raises(ValueError,match='缺省HDR'):definition_for(config)
    config.sample_evaluation=SampleDefinition(mode='MAPPED',mapping=definition['mapping'][:-1])
    with pytest.raises(ValueError,match='完整对应'):definition_for(config)


def test_definition_digest_is_order_independent_and_training_only(tmp_path):
    config=roi_config(tmp_path);config.sample_evaluation=SampleDefinition(mode='MAPPED')
    definition=definition_for(config);reverse=deepcopy(definition)
    reverse['mapping'].reverse()
    assert training_digest(config,definition)==training_digest(config,reverse)
    reverse['mapping'][0]['sample_id']='changed-test-only'
    assert training_digest(config,definition)==training_digest(config,reverse)
    reverse['mapping'][-1]['sample_id']='changed-training'
    assert training_digest(config,definition)!=training_digest(config,reverse)
