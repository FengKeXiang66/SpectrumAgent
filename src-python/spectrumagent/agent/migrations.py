"""TASK-07 12.1/12.2: G1 tables, G3 skill versions and startup seeds."""


DDL = r"""-- G1：LLM 配置（非敏感，key 不在此表）
CREATE TABLE IF NOT EXISTS llm_settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL              -- 设置屏保存 body，首次启动服务端播种空值(base_url/model/temperature/max_tokens/timeout_ms)
);
-- 供值：value 全部来自 PUT /settings/llm 的 body 或启动播种（播种值=空串=未配置，禁预置厂商）

-- G1：调用留痕（每次调用一条，消息全文不落库，只存 sha256）
CREATE TABLE IF NOT EXISTS llm_call (
  id                TEXT PRIMARY KEY,
  session_id        TEXT,          -- agent_session.id，系统级调用记 NULL（status 维持四值枚举不前缀，系统级仅以 session_id=NULL 标识）
  model             TEXT NOT NULL, -- 响应回读（请求用的 model，发送前已知）
  prompt_sha256     TEXT NOT NULL, -- 服务端：发送前对 messages 计算
  tool_names        TEXT,          -- 服务端：本次请求 tools 名列表 JSON（无工具调用记 NULL）
  prompt_tokens     INTEGER,       -- 响应 usage，无 usage 记 NULL（禁 0 禁估算）
  completion_tokens INTEGER,       -- 同上
  total_tokens      INTEGER,       -- 同上（响应 usage 原值，禁由 prompt+completion 派生填写，§2.1 ChatResult.usage 三字段与 DDL 对齐，2026-10-23 勘误补入）
  latency_ms        INTEGER NOT NULL, -- 服务端计时
  status            TEXT NOT NULL, -- ok|blocked|transport_error|http_error
  error             TEXT,
  created_at        TEXT NOT NULL   -- 服务端 timestamp()
);

-- G3：SKILL 版本（只增不改，内容 UPDATE 禁止，仅状态迁移 draft→active / draft→retired / active→retired，retired 终态）
CREATE TABLE IF NOT EXISTS skill_version (
  id            TEXT PRIMARY KEY,
  version_no    INTEGER NOT NULL,     -- 服务端自增
  name          TEXT NOT NULL,
  system_prompt TEXT NOT NULL,        -- 种子数据：来源=本卡 §2.3 规格
  tools_json    TEXT NOT NULL,        -- 种子数据：工具清单快照（几何禁入字段扫描对象）
  examples_json TEXT NOT NULL,        -- 种子数据：来源=本卡 §2.3
  status        TEXT NOT NULL,        -- draft|active|retired，active 全局唯一（断言+测试）
  note          TEXT,
  created_at    TEXT NOT NULL
);
"""

SETTING_KEYS = ("base_url", "model", "temperature", "max_tokens", "timeout_ms")


def migrate(db):
    # The registry's preceding annotation migration owns the transaction.
    # Also works independently and repeatedly on the same connection.
    for statement in DDL.split(";"):
        if statement.strip():
            db.execute(statement)
    for key in SETTING_KEYS:
        if not db.execute("SELECT 1 FROM llm_settings WHERE key=?", (key,)).fetchone():
            db.execute("INSERT INTO llm_settings (key,value) VALUES (?,?)", (key, ""))
    # Complete trigger statements must not pass through DDL.split(";").
    from .skill import ensure_seeded, install_guards
    install_guards(db)
    ensure_seeded(db)
