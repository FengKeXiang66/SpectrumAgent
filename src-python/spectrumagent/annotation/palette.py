"""Resolve project colors without inventing or modifying any label."""
import os
from pathlib import Path

from backend.database import connect_database


def project_colors(database, classes, headers=(), pinned=None):
    colors = dict(pinned or {})
    if not Path(database).is_file():
        return colors
    with connect_database(database) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'label', 'project'} <= tables:
            return colors
        projects = set()
        for header in headers if 'dataset_registry' in tables else ():
            key = os.path.normcase(str(Path(header).resolve()))
            projects.update(row[0] for row in db.execute('SELECT project_id FROM dataset_registry WHERE header_key=?', (key,)))
        if not projects:
            projects = {row[0] for row in db.execute('SELECT id FROM project')}
        # Never borrow a same-named class from an unrelated project.
        if len(projects) != 1:
            return colors
        rows = list(db.execute('SELECT name,color_hex FROM label WHERE project_id=? AND deleted_at IS NULL', (projects.pop(),)))
    for identifier, name in classes.items():
        if identifier in colors:
            continue
        matches = [color for candidate, color in rows if candidate == name]
        if not matches:
            matches = [color for candidate, color in rows if candidate.casefold() == name.casefold()]
        if len(matches) == 1:
            colors[identifier] = matches[0]
    return colors


def model_colors(database, config):
    headers = [member.header_path for member in config.train.members] if config.train.kind == 'roi_images' else []
    return project_colors(database, config.classes, headers, getattr(config, 'class_colors', {}))
