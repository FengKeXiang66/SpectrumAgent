"""TASK-07 12.1–12.3 domain tables and startup seeds."""


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

-- G2/G3：会话、轮次与步骤（R10：session→round→step 三层，round 为 HUMAN_CHECK 续执行锚）
CREATE TABLE IF NOT EXISTS agent_session (
  id              TEXT PRIMARY KEY,
  title           TEXT,           -- 服务端规则：创建时空串，首条用户消息后填截断 40 字（仅空→非空一次，R10 豁免），禁 LLM 生成后回写
  skill_version_id TEXT NOT NULL REFERENCES skill_version(id), -- 创建时取当前 active，无 active 拒绝创建，此后不可改
  created_at      TEXT NOT NULL,  -- 不可改
  updated_at      TEXT NOT NULL   -- 服务端规则：每轮消息后更新（审计字段非内容，R10 豁免）
);
-- G2：编排轮次（R10：HUMAN_CHECK 挂起后续执行的持久化锚，落盘≠回灌，往轮仍不回灌 LLM）
CREATE TABLE IF NOT EXISTS agent_round (
  id           TEXT PRIMARY KEY,
  session_id   TEXT NOT NULL REFERENCES agent_session(id),
  seq          INTEGER NOT NULL,   -- 服务端自增（会话内轮次号）
  user_message TEXT NOT NULL,      -- 本轮用户消息原文：INTERPRET 上下文与续执行的权威源（业务轮次数据，llm_call 仍只存 messages sha256，两口径分工不变）
  calls_json   TEXT NOT NULL,      -- 本轮 LLM tool_call 序列（仅过 Pydantic 校验的调用，含 id/name/arguments，几何禁入 schema 保证无坐标谱值）
  status       TEXT NOT NULL,      -- running|human_check|done|error
  created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_step (
  id              TEXT PRIMARY KEY,
  session_id      TEXT NOT NULL REFERENCES agent_session(id),
  round_id        TEXT NOT NULL REFERENCES agent_round(id), -- 服务端规则：所属轮次（R10，剩余调用定位与续执行依赖它）
  seq             INTEGER NOT NULL,   -- 服务端自增（会话内）
  tool            TEXT NOT NULL,      -- LLM 返回的 tool_call.name
  arguments_json  TEXT NOT NULL,      -- 过 Pydantic 校验后的参数，rejected 路径供值：{"_raw_sha256":…,"_raw_truncated":…}（原文截断上限 4KB，大对象禁入）
  result_digest   TEXT,               -- 执行结果 sha256，rejected 记 NULL
  result_summary  TEXT,               -- 服务端短摘要，大对象禁入
  status          TEXT NOT NULL,      -- ok|rejected|human_check_pending|error
  latency_ms      INTEGER NOT NULL,
  created_at      TEXT NOT NULL
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
    from .state import install_guards as install_agent_guards
    install_agent_guards(db)
