"""Regenerate the review index of SQL resources; not a SQL rewriting layer."""
import argparse
import ast
from collections import Counter
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TABLES = set('''dataset_registry label label_schema label_alias sample_label
preprocess_recipe preprocess_recipe_version project_recipe preprocess_run
training_run classification_model classification_evaluation classification_export
training_job experiment_dialogue model_registry inference_run sample_target
agent_session agent_session_scope dataset_intake agent_regression_plan study_draft
project project_trash project_resource agent_step_plan inference_draft inference_foreground_probe inference_restart_request'''.split())


def enforcement(path, function, sql):
    if any(part in path for part in ('/migrations.py', 'session_migrations.py')) or function in {'migrate', 'initialize', 'install_guards', 'recover_interrupted', '_recover_interrupted', '_existing_sources', 'cleanup'}:
        return '启动/结构维护；不作为会话发现入口', '迁移备份与重启用例'
    if path.endswith('projects.py'):
        return '可信项目上下文；显式项目管理/只读迁移预览', 'HTTP 绑定、迁移预览、历史迁移'
    if '/storage/recycle.py' in path:
        return '预览/执行先验 cube；依赖闭包再次校验项目', 'UUID 拒绝；完整删除回归'
    if '/experiments/' in path:
        return '会话绑定；归档/Study 由 project_resource 校验；草稿重验父资源', '归档与后台任务；逐步计划；分类/推理回归'
    if '/modeling/' in path or path.endswith('/tools/modeling.py') or path.endswith('/regression_plan.py'):
        return 'cube/schema/run/model/evaluation 父链校验；列表按当前项目筛选', '跨项目模型/run 拒绝；训练回归'
    if '/preprocess/' in path:
        return 'cube/annotation/run 父链校验；配方 builtin 或 project_recipe', '跨项目配方拒绝；模板只读；重启不改归属'
    if '/annotation/' in path:
        return 'Registry.get 或 LabelStore.require_project/require_label；缓存重验', '跨项目标注/标签；并发复用；颜色隔离'
    if '/agent/' in path:
        return 'ScopedToolRegistry + 服务域校验；列表/编号用项目内目录', 'D 编号、UUID 绕过、旧引用与确认'
    return 'HTTP 项目身份与业务父资源校验；不依赖前端隐藏', 'HTTP UUID、字段校验与全量回归'


def scan():
    result = []
    for path in sorted((ROOT/'src-python/spectrumagent').rglob('*.py')):
        tree = ast.parse(path.read_text('utf-8-sig'))
        functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            sql = ' '.join(node.value.split())
            if not re.search(r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER)\b', sql, re.I):
                continue
            tables = sorted(t for t in TABLES if re.search(r'\b'+t+r'\b', sql))
            if not tables:
                continue
            function = min((f for f in functions if f.lineno <= node.lineno <= f.end_lineno),
                           key=lambda f:f.end_lineno-f.lineno, default=None)
            name = function.name if function else '<module>'
            relative = path.relative_to(ROOT).as_posix()
            policy, test = enforcement(relative, name, sql)
            kind = '结构/维护' if re.search(r'\b(CREATE|ALTER|DROP)\b',sql,re.I) or '维护' in policy else '列表' if name in {'list','catalog','dataset_catalog','display_names','state','view','projects','known_sources'} and sql.upper().startswith('SELECT') else '编号读取/校验' if sql.upper().startswith('SELECT') else '写入'
            result.append((relative, node.lineno, name, tables, kind, policy, test, sql[:130]))
    return sorted(result)


def document():
    rows = scan()
    counts = Counter(t for row in rows for t in row[3])
    content = '''# 项目作用域资源清单

生成：`python scripts/audit_project_resources.py --write`。检查：`python scripts/audit_project_resources.py --check`。

这是逐条 SQL 审查索引，不把字符串次数当成独立权限入口数。每行给出文件、函数、访问类型、处理边界和验收组。编号读取不一定重复添加 WHERE：已经校验的 cube/run/model 可以向其子表传递边界。

## 动态查询和文件资源（静态 SQL 扫描的补充）

| 入口 | 处理方式 | 验收 |
|---|---|---|
| ProjectMiddleware | 会话路径从 agent_session 取身份；原生页面从持久化选择取身份；结构化请求及路径引用校验 | HTTP 原生/会话绑定不同、跨项目 UUID |
| ScopedToolRegistry.invoke/_check | 先绑定会话项目，后校验引用，最后处理授权和调用；模型不能指定其他项目 | cube、recipe、model 绕过用例 |
| DatasetRegistry / CurrentWorkspace / dataset_catalog / authorization.capture | 项目内列表、计数与 D 编号；Registry.get 拦截直取及缓存 | 项目内目录、D1、全量范围 |
| ExperimentService.get/folder / ExperimentArchive.folders | 新归档持久化 project_resource；无索引旧归档只归默认项目；原始产物不改写 | NPZ 归档隔离、跨会话、产物直取 |
| Study.prepare / folder / submit | 草稿、归属及确认同事务提交；旧草稿/归档按可信会话补索引；默认项目也拒绝无归属编号；确认与结果读取均校验 | test_study_project_lifecycle：非默认项目、恢复、冲突、回滚；Study 评价回归 |
| InferenceDialogue / inference_flow | 已执行及已关闭草稿只读；新请求经会话绑定暂存，修订号及令牌防旧按钮重放；明确新建才重置草稿 | test_inference_draft_lifecycle：新建、微调、历史文件不变；前端只读卡片 |
| RecipeStore / recipe drafts | builtin 公共模板只读；自建配方按 project_recipe；重启不收编取消关联的配方 | 配方 UUID、重启、模板只读 |
| Modeling / Evaluations / TrainingJobs | run 的 cube 数组及模型父链归属；缓存任务回执、导出、取消均校验 | 模型 UUID、任务与部署回归 |
| RecycleStore | 入口验证 cube，展开删除依赖后再次检查项目 | 删除影响清单与隔离测试 |
| ReferenceBook | SRC/C/DEL 内部引用记录签发项目；不能跨项目重放 | 源引用重放拒绝 |
| 线程与 SSE | 每次生成器推进绑定会话项目；提交线程捕获上下文；队列按任务会话重绑 | 切项目后后台归档仍归原项目 |
| 启动恢复 | 仅内部 maintenance 上下文跨项目恢复；不向模型/HTTP 暴露开关 | 重启中断恢复与历史读取 |

具体验收函数见 `tests/test_project_scopes.py`；历史功能由全量 Python、Node、Rust 测试覆盖。静态扫描不能替代新增入口的人工边界审查；增加资源类型应同时更新 projects.owned、此表及绕过测试。

## 表统计

| 表 | 涉及文件 | SQL 字符串数 |
|---|---:|---:|
'''
    for table, count in sorted(counts.items()):
        files = {r[0] for r in rows if table in r[3]}
        content += f'| `{table}` | {len(files)} | {count} |\n'
    content += '\n## 逐条访问位置\n\n| 文件:行 / 函数 | 表 | 类型 | 处理方式 | 验收组 | SQL 摘要 |\n|---|---|---|---|---|---|\n'
    for path, line, name, tables, kind, policy, test, sql in rows:
        content += f'| `{path}:{line}` · `{name}` | {", ".join(tables)} | {kind} | {policy} | {test} | `{sql.replace("|"," ")}` |\n'
    return content


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT/'docs/project-scope-inventory.md'
    expected = document()
    if args.write:
        path.write_text(expected, encoding='utf-8')
    elif not path.is_file() or path.read_text('utf-8') != expected:
        raise SystemExit('资源清单已过期；请重新生成并审查。')
    print(f'资源清单：{len(scan())} 条 SQL；已'+('生成' if args.write else '核对'))
