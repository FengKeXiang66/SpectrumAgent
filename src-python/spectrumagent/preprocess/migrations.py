"""TASK-05 §3/R7: five tables, after the existing #04 migration; code-idempotent seed."""
from datetime import datetime, timezone
import json
from uuid import uuid4


DDL = r"""CREATE TABLE IF NOT EXISTS preprocess_recipe (
  id           TEXT PRIMARY KEY,
  code         TEXT NOT NULL,                -- 唯一标识，如 plastic-snv-sg1
  name         TEXT NOT NULL,
  description  TEXT,
  builtin      INTEGER NOT NULL DEFAULT 0,   -- 1=内置默认配方
  created_at   TEXT NOT NULL,
  UNIQUE (code)
);
CREATE TABLE IF NOT EXISTS preprocess_recipe_version (
  id           TEXT PRIMARY KEY,
  recipe_id    TEXT NOT NULL REFERENCES preprocess_recipe(id),
  version_no   INTEGER NOT NULL,
  pipeline     TEXT NOT NULL,                -- JSON：有序算子链+参数+算子版本
  note         TEXT,                         -- 变更说明（用户备注，非事件JSON）
  created_at   TEXT NOT NULL,
  UNIQUE (recipe_id, version_no)
);
-- 项目选用：只读关联，不是副本
CREATE TABLE IF NOT EXISTS project_recipe (
  project_id   TEXT NOT NULL REFERENCES project(id),   -- R2 补 FK，对齐 #04
  recipe_id    TEXT NOT NULL REFERENCES preprocess_recipe(id),
  selected_at  TEXT NOT NULL,
  PRIMARY KEY (project_id, recipe_id)
);
-- 一次"配方×数据集"套用 = 一个 run（含状态机，R2 补）
CREATE TABLE IF NOT EXISTS preprocess_run (
  id           TEXT PRIMARY KEY,
  cube_id      TEXT NOT NULL,                -- 输入数据集（dataset_registry.id）
  annotation_version_id TEXT NOT NULL REFERENCES annotation_version(id),  -- R7：B10 输入逐像素谱依赖的标注版本（跨里程碑 FK，#04 迁移先跑）
  recipe_version_id TEXT NOT NULL REFERENCES preprocess_recipe_version(id),
  b01_branch   TEXT NOT NULL CHECK (b01_branch IN ('reference','scale','passthrough')),
  input_fingerprint TEXT NOT NULL,           -- sha256(dataset_id|源文件哈希|annotation_version_id|样本像素数)，见 §2.4 R3（R7 修正：原注释写成 JSON 且漏标注版本）
  scaler_params TEXT,                        -- JSON：fit-on-apply 标定结果（B05）
  metrics      TEXT,                         -- JSON：B10 指标快照
  status       TEXT NOT NULL CHECK (status IN ('pending','running','succeeded','failed')),
  error        TEXT,                         -- status='failed' 时的结构化错误摘要
  finished_at  TEXT,
  note         TEXT,
  created_at   TEXT NOT NULL
);
-- 产物登记（大数组不进 DB，路径相对 preprocessed 根）
CREATE TABLE IF NOT EXISTS preprocess_artifact (
  id           TEXT PRIMARY KEY,
  run_id       TEXT NOT NULL REFERENCES preprocess_run(id),
  kind         TEXT NOT NULL CHECK (kind IN ('processed_cube','sample_spectra','overlay','report')),
  relative_path TEXT NOT NULL,               -- POSIX 相对路径（对齐 #04 snapshot_ref 纪律）
  sha256       TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  UNIQUE (run_id, kind, relative_path)       -- R2 补
);
"""

BUILTIN_CODE = "plastic-snv-sg1"
BUILTIN_PIPELINE = {"steps": [
    {"op": "snv", "version": 1, "params": {}},
    {"op": "sg_derivative", "version": 1, "params": {"order": 1, "window": 15, "polyorder": 2}},
]}


def migrate(db):
    required = {"project", "annotation_version"}
    existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required <= existing:
        raise RuntimeError("TASK-04 迁移必须先跑：缺少 project/annotation_version")
    db.execute("PRAGMA foreign_keys=ON")
    with db:
        db.execute("BEGIN IMMEDIATE")
        for statement in DDL.split(";"):
            if statement.strip():
                db.execute(statement)
        if not db.execute("SELECT 1 FROM preprocess_recipe WHERE code=?", (BUILTIN_CODE,)).fetchone():
            identifier, timestamp = str(uuid4()), datetime.now(timezone.utc).isoformat()
            db.execute("INSERT INTO preprocess_recipe (id,code,name,description,builtin,created_at) VALUES (?,?,?,?,?,?)",
                       (identifier, BUILTIN_CODE, "塑料 SNV + SG 一阶导数", "场景示例默认值、可改；需求场景 S1 第418行", 1, timestamp))
            db.execute("INSERT INTO preprocess_recipe_version (id,recipe_id,version_no,pipeline,note,created_at) VALUES (?,?,?,?,?,?)",
                       (str(uuid4()), identifier, 1, json.dumps(BUILTIN_PIPELINE, ensure_ascii=False), None, timestamp))
