"""Idempotent startup migration; DDL copied verbatim from TASK-04 §4.1 (R13)."""
from uuid import uuid4

from .labels import CustomRequest, insert_label, now, plastic_catalog


DDL = r"""-- 项目（阶段一：仅默认项目一条；project_id 为阶段二账号体系预留）
CREATE TABLE IF NOT EXISTS project (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  note       TEXT
);

-- 标签字段（schema）：枚举/布尔/连续/序数
CREATE TABLE IF NOT EXISTS label_schema (
  id         TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES project(id),
  name       TEXT NOT NULL,
  tree_path  TEXT NOT NULL,
  field_type TEXT NOT NULL CHECK (field_type IN ('enum','bool','continuous','ordinal')),
  unit       TEXT,
  config     TEXT,                    -- JSON：连续值域 {min,max} / 序数档位 / 布尔默认值
  created_at TEXT NOT NULL,
  UNIQUE (project_id, tree_path)
);

-- 枚举值（标签）
CREATE TABLE IF NOT EXISTS label (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES project(id),
  schema_id   TEXT NOT NULL REFERENCES label_schema(id),
  code        TEXT NOT NULL,
  name        TEXT NOT NULL,
  tree_path   TEXT NOT NULL,
  color_hex   TEXT NOT NULL,
  shortcut_key INTEGER,               -- 0 仅背景；1–9 其余；>9 类超出部分留 NULL（仅鼠标点选）
  sort_order  INTEGER NOT NULL,
  is_background INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  UNIQUE (project_id, code),
  UNIQUE (project_id, shortcut_key),
  CHECK (shortcut_key IS NULL
         OR (shortcut_key = 0 AND is_background = 1)
         OR (shortcut_key BETWEEN 1 AND 9))
);

-- 标注版本（先建版本表，annotation 对它有外键）
CREATE TABLE IF NOT EXISTS annotation_version (
  id             TEXT PRIMARY KEY,
  cube_id         TEXT NOT NULL,
  version_no      INTEGER NOT NULL,
  snapshot_ref    TEXT NOT NULL,      -- 快照目录（label_map.npz / spectra.npz / label_index.json）
  n_pixels        INTEGER NOT NULL,
  labeled_pixels  INTEGER NOT NULL,
  auto_ratio      REAL NOT NULL DEFAULT 0,   -- 阶段一恒 0
  params          TEXT NOT NULL,             -- JSON：当次分割参数（n_segments/compactness/pca_components/k/block_size/特征口径版本），复现性凭据
  note            TEXT,
  created_at      TEXT NOT NULL,
  UNIQUE (cube_id, version_no)
);

-- 标注区域（**每 label 一条/版本**，不是操作日志；几何 = 该 label 全覆盖的超像素 id 集合，仅供追溯）
-- 只在保存版本时写入，故 version_id 必填；阶段一 granularity 恒为 'pixel'，'sample'/'scene' 为阶段二预留
-- 'scene' 无写入路径（见 5.4）
CREATE TABLE IF NOT EXISTS annotation (
  id          TEXT PRIMARY KEY,
  cube_id     TEXT NOT NULL,
  version_id  TEXT NOT NULL REFERENCES annotation_version(id),
  granularity TEXT NOT NULL CHECK (granularity IN ('pixel','sample','scene')),
  label_id    TEXT,                   -- enum 时引用 label.id
  label_value TEXT,                   -- JSON：bool / continuous / ordinal 取值
  geometry    TEXT,                   -- JSON：{"superpixels":[...]} 或 {"polygon":[[l,s],...]}
  pixel_count INTEGER NOT NULL,
  source      TEXT NOT NULL DEFAULT 'manual'
              CHECK (source IN ('manual','library','cluster','transfer','model','unmix')),
  confidence  REAL,                   -- 预留，阶段一恒 NULL
  evidence    TEXT,                   -- 预留，阶段一恒 NULL
  annotator_id TEXT,                  -- 预留，阶段一恒 NULL
  created_at  TEXT NOT NULL,
  CHECK (label_id IS NOT NULL OR label_value IS NOT NULL)
);

-- 样本级光谱（带标签样本光谱）
CREATE TABLE IF NOT EXISTS sample_spectrum (
  id          TEXT PRIMARY KEY,
  cube_id     TEXT NOT NULL,
  version_id  TEXT NOT NULL REFERENCES annotation_version(id),
  label_id    TEXT,
  label_value TEXT,
  sample_code TEXT NOT NULL,          -- 样品标识：阶段一取数据集名（cube name）
  n_pixels    INTEGER NOT NULL,
  mean_ref    TEXT NOT NULL,          -- spectra.npz 内键名
  std_ref     TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  CHECK (label_id IS NOT NULL OR label_value IS NOT NULL)
);
"""


def default_project_id(db):
    return db.execute("SELECT id FROM project WHERE name=? ORDER BY created_at,id LIMIT 1", ("默认项目",)).fetchone()[0]


def migrate(db):
    db.execute("BEGIN IMMEDIATE")
    for statement in DDL.split(";"):
        if statement.strip():
            db.execute(statement)
    if not db.execute("SELECT 1 FROM project WHERE name=?", ("默认项目",)).fetchone():
        db.execute("INSERT INTO project (id,name,created_at) VALUES (?,?,?)", (str(uuid4()), "默认项目", now()))
    project_id = default_project_id(db)
    if not db.execute("SELECT 1 FROM label_schema WHERE project_id=? AND tree_path=?", (project_id, "材料")).fetchone():
        db.execute("INSERT INTO label_schema (id,project_id,name,tree_path,field_type,created_at) VALUES (?,?,?,?,?,?)",
                   (str(uuid4()), project_id, "材料", "材料", "enum", now()))
    # §4.3: only PE/PET/PP/BG, idempotent by (project_id, code).
    seeds = [(item, index) for index, item in enumerate(plastic_catalog()[:3], 1)]
    seeds.append(({"code": "BG", "name": "背景", "color_hex": "#9aa7b2"}, 0))
    for item, shortcut in seeds:
        if not db.execute("SELECT 1 FROM label WHERE project_id=? AND code=?", (project_id, item["code"])).fetchone():
            insert_label(db, CustomRequest(project_id=project_id, **item,
                         tree_path=f"材料/塑料/{item['code']}", shortcut_key=shortcut,
                         is_background=item["code"] == "BG"), origin="seed")
    columns = {row[1] for row in db.execute("PRAGMA table_info(dataset_registry)")}
    if "project_id" not in columns:
        db.execute("ALTER TABLE dataset_registry ADD COLUMN project_id TEXT")
    db.execute("UPDATE dataset_registry SET project_id=? WHERE project_id IS NULL", (project_id,))
