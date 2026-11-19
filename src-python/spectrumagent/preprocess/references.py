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
    cursor = db.execute('SELECT r.* FROM preprocess_run r JOIN annotation_version a ON a.id=r.annotation_version_id '
                        'AND a.cube_id=r.cube_id JOIN preprocess_recipe_version v ON v.id=r.recipe_version_id WHERE '
                        + ' AND '.join(conditions) + (' ORDER BY r.created_at DESC,r.id LIMIT 1' if discovery else ''), arguments)
    row = cursor.fetchone()
    return dict(zip([col[0] for col in cursor.description], row)) if row is not None else None
