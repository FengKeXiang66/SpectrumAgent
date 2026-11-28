"""Resolve project colors without inventing or modifying any label."""
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
        from spectrumagent.projects import current
        project = current(db)
        if project is None:
            return colors
        rows = list(db.execute('SELECT name,color_hex FROM label WHERE project_id=? AND deleted_at IS NULL', (project,)))
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
