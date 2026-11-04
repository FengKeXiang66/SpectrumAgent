# TASK-24 · Rust 测试代码 unwrap 债（把 A10 门恢复成"绝对零"）

> 目标：让 `cargo clippy --all-targets -- -D warnings` **真正零 error**，把 TASK-23 的 A10 从"相对基线零新增"恢复成"绝对零告警"。
> 前置：TASK-23（P6）已收口。**只改测试代码，生产段一条 lint 不放宽。**
> **三道闸门**：① `git status` 干净；② 开工前 `cargo test` 全绿、`cargo clippy --all-targets -- -D warnings` 的 error 数 = **38**；③ 开工第一步 `grep -n` 复核本卡行号，漂移即停。

---

## 0. 事实底座（2026-11-04 实测）

### 0.1 债在哪：**两个文件、38 条，全在测试代码**

| target | error 条数 | 来源 | 性质 |
|---|---|---|---|
| `(lib test)` | **18** | `src-tauri/src/models.rs` 的 `#[cfg(test)] mod tests`（**起于 `:288`**，全文 465 行） | 单元测试 |
| `(test "models_forward")` | **20** | `src-tauri/tests/models_forward.rs`（**不含 `include!`，是独立集成测试 crate**） | 集成测试 |
| 合计 | **38** | — | — |

**计数口径**：`grep -o '\.unwrap()'` 计次 = 18 + 20 = 38；`grep -c` 计行，`models.rs` 只有 16。**clippy 报的 38 是"条数"不是"处数"，本卡一律用条数。**

### 0.2 生产段是干净的

```
grep -o '\.unwrap()' src-tauri/src/*.rs | wc -l        → 18   （全部落在 models.rs:288 之后）
sed -n '1,287p' src-tauri/src/models.rs | grep -c …    → 0    （生产段零 unwrap）
grep -o '\.unwrap()' src-tauri/tests/*.rs | wc -l      → 20   （只有 models_forward.rs 命中）
```

其余 **9 个**集成测试文件（`contracts.rs` / `engine_path.rs` / `causality.rs` / `dev_identity.rs` / `dev_lifecycle.rs` / `supervisor_stubs.rs` / `win32_failures.rs` / `agent_settings_forward.rs` / `annotations_draft_forward.rs`）**unwrap 为 0**，不要动。

### 0.3 触发源：三条并列 deny

`src-tauri/Cargo.toml:45-47`：

```toml
[lints.clippy]
unwrap_used = "deny"
expect_used = "deny"
panic = "deny"
```

**这三条对生产代码必须保持全强度**。本卡只在测试作用域内 allow。

### 0.4 一个必须写进判据的环境噪声

`cargo clippy --all-targets` 每个 target 会打一条**与代码无关**的 warning：

```
warning: error deleting lock file for incremental compilation session directory `…\target\debug\incremental\…lock`: 拒绝访问。 (os error 5)
```

这是本机文件锁问题（与 pytest 的 safe-delete hook 同族），**不是 lint**。所以验收不能写"零 warning"——永远做不到。正确判据见 §3。

---

## 1. 范围裁定

### 1.1 做

1. `src/models.rs`：在 `#[cfg(test)] mod tests` 块内**首行**加
   `#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]`
   （三条一起 allow；只 allow `unwrap_used` 不够，另外两条 deny 仍在）。
2. `src-tauri/tests/models_forward.rs`：文件**第一行**加同一条 inner attribute（集成测试文件本身就是 crate 根，`#![allow(...)]` 合法）。
3. 两处各配一行理由注释。

### 1.2 不做（红线）

- **不改任何 `.unwrap()` 本身**——一处都不改。本卡是"明确声明测试允许 panic"，不是"改写断言风格"。
- 不改 `Cargo.toml` 的 `[lints.clippy]`（那是全局放宽，被否）。
- 不改生产代码（`models.rs:1-287` 一个字节不动）。
- 不碰其余 8 个集成测试文件。
- 不加 `#[allow]` 到函数级或语句级——只允许模块级/文件级，保证"一眼可见的边界"。

---

## 2. 口径钉死

### 2.1 为什么 allow 在测试作用域**不是**放宽

| 主张 | 依据 |
|---|---|
| 三条 deny 对生产代码依然生效 | allow 只作用在 `#[cfg(test)] mod tests` 内 / 集成测试 crate 根，Rust lint 作用域语义；`models.rs:1-287` 一行不受影响 |
| 测试里 panic 是**失败信号**，不是生产风险 | `unwrap` 在测试中失败即测试失败，这是期望行为 |
| 为什么不用 `.expect()` | 撞 `expect_used = "deny"`，换完还是 38 条红 |
| 为什么不用 `unreachable!()` 改写 | **行为完全等价**（一样 panic），只是把"被 lint 管的 panic"换成"不被 lint 管的 panic"；18+20 处改写 = 480 行测试代码的回归风险，安全增益为 0；且审计者看到 allow 立刻知道"测试故意允许"，看到 let-else 还要逐处判断。**已裁定弃用** |

### 2.2 allow 的写法

```rust
// src/models.rs（在 mod tests 内首行）
#[cfg(test)]
mod tests {
    // 测试代码用 unwrap 直接暴露失败；三条 clippy deny 只针对生产路径。
    #![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
    ...
}
```

```rust
// src-tauri/tests/models_forward.rs（文件第一行）
// 集成测试：失败即 panic 是期望行为；三条 clippy deny 只针对生产路径。
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
```

> `#![...]` 是 **inner attribute**，必须在块/文件的最前（`mod tests` 内可放在其它 item 之前，但要在 `use` 之前）；`#[...]` 是 outer，别写错。

---

## 3. 验收

| # | 断言 | 判据 |
|---|---|---|
| A1 | **clippy 绝对零 error** | `cd src-tauri && cargo clippy --all-targets -- -D warnings; echo "exit=$?"` → **exit=0**，且同一条命令输出里 `grep -c "^error"` = **0** |
| A2 | **不再有 `unwrap_used` 诊断** | `cargo clippy --all-targets -- -D warnings 2>&1 \| grep -c "unwrap_used"` = **0** |
| A3 | **生产段零放宽 + allow 不扩散（双向机验）** | 正向：① `sed -n '1,287p' src-tauri/src/models.rs \| grep -c "allow(clippy"` = **0**；② `sed -n '1,287p' src-tauri/src/models.rs \| grep -c "\.unwrap()"` = **0**；③ `grep -rn "allow(clippy" src-tauri/src/*.rs` 的命中**只允许**出现在 `models.rs` 的 `mod tests` 内。反向：④ `grep -c "allow(clippy" src/models.rs` = **1** 且 `grep -c "allow(clippy" tests/models_forward.rs` = **1**——**allow 恰好各一处，不许第二个蔓延**（开工实测：两文件改前均为 **0**，所以"=1"是干净判据） |
| A4 | **测试全绿** | `cargo test` → **95 passed / 0 failed**（数字现场重取；与开工基线一致） |
| A5 | **改动面** | `git diff --stat src-tauri` 恰好 **2 files**，每个文件 **+2 行**（一条 attribute + 一行注释）；`git diff` 里不出现任何 `.unwrap()` 行的增删 |
| A6 | **环境噪声不误判** | 回报里必须区分：`error: used unwrap()`（代码）= 0；`warning: error deleting lock file … os error 5`（环境）允许存在，**不得**为消它改配置 |

> A1 的判据是 **exit code + `^error` 计数**，不是"零 warning"——后者被 §0.4 的环境噪声永久破坏，写成"零告警"就是一条永远不成立的门。

---

## 4. 红线

1. 只准改 2 个文件；出现第 3 个即停。
2. 一处 `.unwrap()` 都不许改写。
3. 不许动 `Cargo.toml` 的 `[lints.clippy]`。
4. 不许把 allow 下沉到函数/语句级。
5. `models.rs:1-287` 生产段零 diff。
6. 行号与实物不符按即停条款停止并显式说明，**不得自行改写本卡**。

---

## 5. 收口后

- A10 门恢复"绝对零"口径，后续所有卡的 A10 回到 `clippy --all-targets -- -D warnings` exit=0。
- TASK-23 §6 的 D1 销账；D4 保留（口径教训）。
