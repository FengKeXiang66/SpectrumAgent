"""Explicit project label aliases; never translate or infer material meanings."""
import unicodedata
from backend.database import connect_database
from spectrumagent.data import DataError


def normalized(name):
    return unicodedata.normalize('NFC', name.strip())


def resolve(database, project, name):
    key = normalized(name)
    with connect_database(database) as db:
        labels = db.execute('SELECT id,code,name FROM label WHERE project_id=?', (project,)).fetchall()
        aliases = db.execute('SELECT label_id FROM label_alias WHERE project_id=? AND alias=?', (project, key)).fetchall()
    hits = {row[0] for row in labels if normalized(row[2]) == key} | {row[0] for row in aliases}
    if len(hits) > 1:
        raise DataError('LABEL_AMBIGUOUS', '标签名称或别名对应多个类别，请明确选择现有 code')
    return next((row[1] for row in labels if row[0] in hits), None)


def add(database, project, alias, code):
    key = normalized(alias)
    if not key:
        raise DataError('INVALID_REQUEST', '别名不能为空')
    existing = resolve(database, project, key)
    if existing and existing != code:
        raise DataError('LABEL_AMBIGUOUS', '别名已被另一类别使用')
    with connect_database(database) as db:
        row = db.execute('SELECT id FROM label WHERE project_id=? AND code=?', (project, code)).fetchone()
        if not row:
            raise DataError('LABEL_NOT_FOUND', '别名必须指向项目中已存在的 code')
        db.execute('INSERT OR IGNORE INTO label_alias(project_id,alias,label_id) VALUES(?,?,?)', (project, key, row[0]))
