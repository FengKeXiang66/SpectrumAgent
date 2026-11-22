"""Registration checks shared by discovery and exact execution; no IO or writes."""


def registered_run(db, cube_id, annotation_version_id, recipe_version_id, *, run_id=None, fingerprint=None, discovery=False):
    conditions = ["r.cube_id=?", "r.annotation_version_id=?", "r.recipe_version_id=?", "r.status='succeeded'"]
    arguments = [str(cube_id), str(annotation_version_id), str(recipe_version_id)]
    if not discovery and run_id is None:
        return None
    if run_id is not None:
        conditions.append('r.id=?')
        arguments.append(str(run_id))
    if fingerprint is not None:
        conditions.append('r.input_fingerprint=?')
        arguments.append(fingerprint)
    # Historical results remain readable as records, but cannot become inputs.
    from .current import is_current_run
    cursor = db.execute('SELECT r.* FROM preprocess_run r JOIN annotation_version a ON a.id=r.annotation_version_id '
                        'AND a.cube_id=r.cube_id JOIN preprocess_recipe_version v ON v.id=r.recipe_version_id WHERE '
                        + ' AND '.join(conditions) + (' ORDER BY r.created_at DESC,r.id DESC' if discovery else ''), arguments)
    names = [col[0] for col in cursor.description]
    for values in cursor.fetchall():
        row = dict(zip(names,values))
        if is_current_run(db,row):
            return row
    return None
