"""Finish abandoned execution leases once, before the new engine accepts work."""
from datetime import datetime, timezone
import json

from backend.database import connect_database


def recover_workspace(database):
    """Preserve successful results and partial artifacts; never restart compute."""
    stamp = datetime.now(timezone.utc).isoformat()
    error = {'error': 'ENGINE_INTERRUPTED', 'detail': '上次引擎已关闭，任务未完成；已有产物保留，请核对后继续或重新提交。',
             'context': {}}
    with connect_database(database) as db:
        db.execute('BEGIN IMMEDIATE')
        for table in ('preprocess_run', 'training_run', 'inference_run'):
            db.execute(f"UPDATE {table} SET status='failed',error=?,finished_at=? "
                       "WHERE status IN ('pending','running')", (json.dumps(error, ensure_ascii=False), stamp))
        # Training receipts carry progress and references to verified fold checkpoints.
        # Keep those fields so an explicit continuation can reuse completed folds.
        rows = db.execute("SELECT id,snapshot FROM training_job "
                          "WHERE json_extract(snapshot,'$.status') IN ('queued','running')").fetchall()
        for identifier, raw in rows:
            snapshot = json.loads(raw)
            # A worker can finish the atomic result commit just before the shell
            # stops it, without publishing its final task receipt yet.
            run = db.execute('SELECT status FROM training_run WHERE id=?', (snapshot.get('run_id'),)).fetchone()
            succeeded = run is not None and run[0] == 'succeeded'
            snapshot.update(status='failed', phase='interrupted', error=error, cancelable=False,
                            finished_at=stamp, snapshot_version=snapshot.get('snapshot_version', 0) + 1,
                            eta_seconds=None, stage_eta_seconds=None)
            if succeeded:
                snapshot.update(status='succeeded', phase='done', error=None, result_status='complete')
            db.execute('UPDATE training_job SET snapshot=? WHERE id=?',
                       (json.dumps(snapshot, ensure_ascii=False, allow_nan=False), identifier))
        db.execute("UPDATE experiment_dialogue SET run_status='failed' WHERE run_status='running'")
