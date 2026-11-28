"""Training-only physical identity and the report protocol reused inside CV."""
from collections import Counter
import numpy as np

from .evaluation_definition import definition_for
from .sample_evaluation import aggregate, source_key, source_ref


def physical_ids(config, origins):
    definition = definition_for(config, training_only=True)
    if not definition or definition['mode']=='MIXED':
        raise ValueError('实物排序须明确IMAGE或MAPPED；MIXED不参与实物排序')
    mapping={row['source_ref']:row['sample_id'] for row in definition['mapping']}
    return np.asarray([source_key(row['source']) if definition['mode']=='IMAGE' else mapping[source_ref(row['source'])]
                       for row in origins],dtype=str)


class SampleScorer:
    def __init__(self, config, data):
        self.config,self.data=config,data
        self.definition=definition_for(config,training_only=True)
        self.groups=physical_ids(config,data.origins)
        members=config.train.members
        self.sources=[m.header_path for m in members]
        self.source_groups=physical_ids(config,[{'source':source} for source in self.sources])

    def score(self, prediction, indices=None):
        indices=np.arange(len(self.data.y)) if indices is None else np.asarray(indices)
        selected=set(self.groups[indices])
        # Include zero-observation views of selected objects; OOF also lists
        # objects with no saved observations at all, without assigning fake folds.
        sources=self.sources if len(indices)==len(self.data.y) else [s for s,g in zip(self.sources,self.source_groups) if g in selected]
        report=aggregate([('test',self.data.y[indices],prediction,(self.data.origins[i] for i in indices))],
            self.config.classes,self.definition,{'test':sources})['roles']['test']
        missing=sorted(set(self.config.classes)-{row['truth'] for row in report['rows'] if row['status']=='included'})
        report['missing_classes']=missing
        report['defined']=report['metrics'] is not None and not missing
        if report['metrics'] is not None:
            report['metrics'].update(evaluation_unit='sample',purpose='training_oof_validation')
        return report

    def support(self):
        # True labels as predictions only to establish structural eligibility,
        # not an estimated score: no candidate predictions influence CV splits.
        report=self.score(self.data.y)
        counts=Counter(row['truth'] for row in report['rows'] if row['status']=='included')
        return {str(label):counts[label] for label in self.config.classes}
