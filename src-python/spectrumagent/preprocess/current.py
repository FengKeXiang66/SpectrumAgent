"""Current workspace state. Legacy SQL names are retained for database compatibility.

There is one editable annotation and one editable definition per recipe. Run and
model records remain evidence of work, but cannot select historical input states.
"""
import sqlite3
from contextlib import nullcontext

from backend.database import connect_database
from spectrumagent.projects import current as project_current
from spectrumagent.data import DataError


def initialize(database):
    with connect_database(database) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS current_run_input (
            run_id TEXT PRIMARY KEY REFERENCES preprocess_run(id) ON DELETE CASCADE,
            annotation_digest TEXT NOT NULL, recipe_digest TEXT NOT NULL)""")


def input_identity(db, annotation_id, recipe_id):
    row = db.execute("""SELECT c.document_sha256,h.sha256 FROM annotation_confirmation_state c
        JOIN recipe_pipeline_hash h ON h.recipe_version_id=?
        JOIN preprocess_recipe_version v ON v.id=h.recipe_version_id
        WHERE c.annotation_version_id=? AND v.version_no=(SELECT MAX(n.version_no) FROM preprocess_recipe_version n WHERE n.recipe_id=v.recipe_id)""", (str(recipe_id), str(annotation_id))).fetchone()
    return tuple(row) if row else None


def is_current_run(db, run):
    identity = input_identity(db, run['annotation_version_id'], run['recipe_version_id'])
    saved = db.execute('SELECT annotation_digest,recipe_digest FROM current_run_input WHERE run_id=?', (run['id'],)).fetchone()
    if identity is None or saved is None or tuple(saved) != identity:
        return False
    draft = db.execute("""SELECT d.revision,c.draft_revision FROM annotation_draft d
        JOIN annotation_confirmation_state c ON c.cube_id=d.cube_id WHERE d.cube_id=?""", (run['cube_id'],)).fetchone()
    return draft is None or draft[0] == draft[1]


class CurrentWorkspace:
    def __init__(self, sessions, runner):
        self.sessions, self.runner = sessions, runner
        self.database = runner.database
        initialize(self.database)

    def state(self):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            members = []
            for cube in db.execute('SELECT id FROM dataset_registry WHERE project_id=? ORDER BY id', (project_current(db),)).fetchall():
                annotation = db.execute('SELECT * FROM annotation_version WHERE cube_id=? ORDER BY version_no DESC LIMIT 1', (cube[0],)).fetchone()
                member = dict(cube_id=cube[0], annotation_id=annotation['id'] if annotation else None,
                              run_id=None, recipe_id=None, status='need_annotation')
                if annotation:
                    member['status'] = 'need_preprocess'
                    run = db.execute("SELECT * FROM preprocess_run WHERE cube_id=? AND status='succeeded' ORDER BY created_at DESC,id DESC LIMIT 1", (cube[0],)).fetchone()
                    if run is not None and is_current_run(db, run):
                        recipe = db.execute('SELECT recipe_id FROM preprocess_recipe_version WHERE id=?', (run['recipe_version_id'],)).fetchone()
                        member.update(run_id=run['id'], recipe_id=recipe[0], recipe_input_id=run['recipe_version_id'], status='ready')
                members.append(member)
        recipes = []
        for recipe in self.runner.recipes.list():
            definition = recipe['versions'][-1]
            recipes.append({key: recipe[key] for key in ('id','code','name','description','builtin')} | {'pipeline': definition['pipeline']})
        return {'members': members, 'recipes': recipes}

    def process(self, cube_id, recipe_id):
        # Prevent current annotation/recipe changes while the bounded engine reads
        # them. The lock order matches annotation operations.
        resources = self.sessions.resources
        lease = resources.lease(cube_id, required=False) if resources else nullcontext()
        with lease, self.sessions._lock, self.runner.recipes.lock:
            with connect_database(self.database) as db:
                row = db.execute('SELECT c.annotation_version_id,c.draft_revision,d.revision FROM annotation_confirmation_state c '
                                 'LEFT JOIN annotation_draft d ON d.cube_id=c.cube_id WHERE c.cube_id=?', (str(cube_id),)).fetchone()
            if row is None or row[1] != row[2]:
                annotation_id = self.sessions.save(cube_id)['id']
            else:
                annotation_id = row[0]
            recipe = self.runner.recipes.get(recipe_id)
            if recipe['deleted']:
                raise DataError('RECIPE_NOT_FOUND', '配方已删除')
            return self.runner.run(cube_id, annotation_id, recipe['versions'][-1]['id'])
