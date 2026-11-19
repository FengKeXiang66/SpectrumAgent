"""Conservative within-stage estimates; unobserved future stages remain unknown."""
from statistics import median
from time import monotonic


def key(event):
    return tuple(event.get(k) for k in ('phase','branch','outer_fold','selection','inner_fold','image_index','rows_read','completed','unit'))


def family(event):
    return tuple(event.get(k) for k in ('phase','branch','selection'))


def history(service, identifier, signature):
    """Only a completed, same-boot/owner, exact verified input can inform total ETA."""
    import json
    from backend.database import connect_database
    with service.lock:
        job=service.jobs[identifier]
        if job['parent'] is not None: return  # A resumed job has a different remaining work plan.
        owner=job['owner']
    with connect_database(service.database) as db:
        row=db.execute("SELECT id,snapshot FROM training_job WHERE boot_id=? AND owner=? AND json_extract(snapshot,'$.status')='succeeded' "
                       "AND json_extract(snapshot,'$.retry_of') IS NULL AND json_extract(snapshot,'$.input_signature')=? ORDER BY created_at DESC LIMIT 1",(service.boot_id,owner,signature)).fetchone()
        if not row: return
        events=[json.loads(r[0]) for r in db.execute('SELECT payload FROM training_job_event WHERE job_id=? ORDER BY seq',(row[0],))]
    anchors={key(e):i for i,e in enumerate(events) if e['phase']!='fit_warning'}
    durations=[max(0,events[i+1]['elapsed_s']-event['elapsed_s']) if i+1<len(events) else
               max(0,json.loads(row[1])['elapsed_s']-event['elapsed_s']) for i,event in enumerate(events)]
    remaining={}; suffix=[None]*len(events)
    for index in range(len(events)-1,-1,-1):
        kind=family(events[min(index+1,len(events)-1)])
        remaining[kind]=remaining.get(kind,0)+durations[index]
        suffix[index]=remaining.copy()
    with service.lock:
        service.jobs[identifier]['eta_history']={'job_id':row[0],'events':events,'anchors':anchors,'durations':durations,'suffix':suffix,'ratios':{}}


def estimate_total(job, phase, values):
    receipt=job['receipt']; model=job.get('eta_history'); event={'phase':phase,**values}
    receipt.update(eta_seconds=None,eta={'state':'unknown','method':'verified-input-history-v1','samples':0,'scope':'whole_task'})
    if not model: return
    index=model['anchors'].get(key(event))
    if index is None: return
    previous=model['events'][index]; kind=family(event)
    if event.get('unit_seconds') and previous.get('unit_seconds'):
        ratios=model['ratios'].setdefault(kind,[]);ratios.append(event['unit_seconds']/previous['unit_seconds'])
        if any(r<.125 or r>8 for r in ratios[-3:]):
            receipt['eta']['state']='stale';return
    remaining=sum(cost*median(model['ratios'].get(kind,[1])[-8:]) for kind,cost in model['suffix'][index].items())
    receipt.update(eta_seconds=round(remaining,1),eta={'state':'estimated','method':'verified-input-history-v1',
                   'samples':1+sum(len(r) for r in model['ratios'].values()),'scope':'whole_task','history_job_id':model['job_id']})
    job['eta_total_sample']=(monotonic(),max(model['durations'][index],.001))


def observe(job, phase, values):
    receipt = job['receipt']
    key = (phase, values.get('branch'), values.get('outer_fold'), values.get('selection'))
    if phase not in ('lv', 'ipls') or not values.get('unit_seconds'):
        job.pop('eta_sample', None)
        receipt.update(stage_eta_seconds=None, stage_eta={'state': 'unknown', 'method': 'phase-weighted-v1', 'samples': 0, 'scope': 'current_stage'})
        estimate_total(job,phase,values)
        return
    if job.get('eta_key') != key:
        job['eta_key'], job['eta_units'] = key, []
    weight = values['lv'] if phase == 'lv' else values['feature_count']
    job['eta_units'].append(values['unit_seconds'] / max(1, weight))
    units = job['eta_units'][-8:]
    count, total = values['completed'], values['total']
    remaining_weight = sum(range(count + 1, total + 1)) if phase == 'lv' else values['remaining_features']
    valid = len(units) >= 2 and min(units) > 0 and max(units) <= 8 * min(units) and count < total
    seconds = median(units) * remaining_weight if valid else None
    job['eta_sample'] = (monotonic(), max(values['unit_seconds'], median(units) * (count + 1 if phase == 'lv' else weight)))
    receipt.update(stage_eta_seconds=round(seconds, 1) if seconds is not None else None,
                   stage_eta={'state': 'estimated' if valid else 'unknown', 'method': 'phase-weighted-v1',
                        'samples': len(units), 'scope': 'current_stage'})
    estimate_total(job,phase,values)


def expire(job, result):
    sample = job.get('eta_sample')
    if sample and result.get('stage_eta_seconds') is not None and monotonic() - sample[0] > sample[1] * 4:
        result['stage_eta_seconds'] = None
        result['stage_eta'] = {**result['stage_eta'], 'state': 'stale'}
    sample=job.get('eta_total_sample')
    if sample and result.get('eta_seconds') is not None and monotonic()-sample[0]>sample[1]*4:
        result['eta_seconds']=None;result['eta']={**result['eta'],'state':'stale'}
