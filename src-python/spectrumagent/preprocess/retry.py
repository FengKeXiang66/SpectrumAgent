"""Retry lineage uses existing submission/action identities and immutable receipts."""
import json
import re

from spectrumagent.data import DataError


def parent_reference(submission):
    return action_parent(submission.action_ref)


def action_parent(action_ref):
    found=re.search(r'(?:^|\.)retry:([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})$',action_ref)
    return found[1] if found else None


def source_reference(db,reference,owner):
    seen=set()
    while reference not in seen:
        seen.add(reference)
        rows=db.execute("SELECT action_ref FROM business_operation WHERE submission_ref=? AND owner_session_id=? AND kind='preprocess.run_batch'",
                        (reference,owner)).fetchall()
        originals=[row for row in rows if action_parent(row[0]) is None]
        if len(originals)==1:return reference
        parents={action_parent(row[0]) for row in rows}
        if originals or len(parents)!=1 or None in parents:break
        reference=parents.pop()
    raise DataError('PREPROCESS_RETRY_SCOPE_MISMATCH','无法确定唯一原批次，请先核对完整回执')


def bind(db, reference, batch_parent, cube_ids):
    """Server-only lineage construction, shared by AI and confirmed UI retries."""
    from . import submissions
    original = source_reference(db, reference, batch_parent.owner_session_id)
    batch = submissions.child(batch_parent, 'retry:' + original)
    return original, batch, state(db, original, batch, cube_ids)


def state(db, reference, submission, cube_ids):
    def reject():
        raise DataError('PREPROCESS_RETRY_SCOPE_MISMATCH','原批次或重试状态待核对；只能继续尚未成功的原失败成员')
    parents=db.execute("SELECT receipt_json FROM business_operation WHERE submission_ref=? AND owner_session_id=? AND kind='preprocess.run_batch' AND instr(action_ref,'.retry:')=0",
                       (reference,submission.owner_session_id)).fetchall()
    if len(parents)!=1 or parents[0][0] is None:reject()
    parent=json.loads(parents[0][0])
    failed={item['cube_id'] for item in parent['items'] if item['status']=='failed'}
    succeeded={item['cube_id'] for item in parent['items'] if item['status']=='succeeded'}
    def verify(items):
        for item in items:
            if item.get('run_id'):
                row=db.execute('SELECT status FROM preprocess_run WHERE id=?',(item['run_id'],)).fetchone()
                if row is None or row[0] not in ('succeeded','failed'):reject()
                if row[0]=='succeeded':succeeded.add(item['cube_id'])
            elif item.get('error_code') in {'OPERATION_IN_PROGRESS','OPERATION_RECONCILIATION_REQUIRED','OPERATION_NEEDS_RECONCILIATION'}:
                reject()
    verify(parent['items'])
    suffix='.retry:'+reference
    related=db.execute("SELECT receipt_json FROM business_operation WHERE owner_session_id=? AND kind='preprocess.run_batch' "
                       "AND substr(action_ref,?)=? AND NOT (submission_ref=? AND action_ref=?)",
                       (submission.owner_session_id,-len(suffix),suffix,submission.submission_ref,submission.action_ref)).fetchall()
    for row in related:
        if row[0] is None:reject()  # An accepted/unknown retry never grants permission to recompute.
        items=json.loads(row[0])['items'];verify(items)
        succeeded.update(item['cube_id'] for item in items if item['status']=='succeeded')
    eligible=failed-succeeded
    if not cube_ids or len(cube_ids)!=len(set(cube_ids)) or not set(cube_ids)<=eligible:reject()
    return {'retained_succeeded':len(succeeded),'remaining_failed':len(eligible-set(cube_ids))}
