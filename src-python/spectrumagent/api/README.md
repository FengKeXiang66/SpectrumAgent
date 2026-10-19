# 数据接入API v1

`spectrumagent.app.create_app(paths, identity)` 包装原地基工厂，复用原鉴权。
本模块不修改backend源码、封版exe、安装器、资源树与原握手协议。
4.6的dev-only Python入口将使用此工厂；release运行时仍待后续打包里程碑接入。

端点与所有信封的Pydantic JSON Schema在openapi.json，测试逐字比对生成结果。
除health外须Bearer token。所有datasets响应（401除外）带本代boot_id/pid身份头；
前端不接触token，不直接HTTP访问sidecar，由Rust请求并核对身份。

POST /api/v1/datasets/import 请求：path（绝对文件/目录）、raw（默认false）、
data_path（可选绝对路径，只用于单头文件配对）。文件与目录响应均为
datasets:[{id,dataset,existing}]、summary:{total,imported,existing}。
只登记引用和元数据，源数据不写入、不复制、不移动。

目录任意深度递归，不跟随目录符号链接以免环路；相同实际路径去重。
.hdr始终校验；.json/.txt有同基名数据或含数据头字段才作为伴随头，忽略README等无关文本。
所有候选均先解析/大小校验，错误全部汇总为400 IMPORT_BATCH_INVALID，任何失败均不登记。
同基名以相对于导入目录的父路径+头文件名消歧；已有记录在同一事务更新显示名。

SQLite仅持久登记台账（id、规范化头路径、默认raw、元数据JSON），不保存立方体内容。
UNIQUE(header_key,raw)+BEGIN IMMEDIATE使跨线程重试保持幂等；解析在事务外的FastAPI工作线程中进行。
GET /{id}返回既有记录；波段/区域按登记的默认raw读取，body.raw可覆盖此次读取而不改登记。
元数据与源头不一致时返回SOURCE_CHANGED，禁止默默把旧台账解释为新维度。

POST /{id}/band/{i} 和 POST /{id}/region 请求为
{l0,l1,s0,s1,raw?}，索引左闭右开；默认0..32，调用方应按源尺寸给出边界。
JSON响应最多65536个数值，过大显式400；NaN/Inf/复数不静默损失转换。
GET /{id}/preview?band=0 返回PNG base64，等比例步进采样至最长边<=512，
shape逻辑索引(lines,samples,bands)，PNG宽=samples、高=lines；只在采样平面内灰度归一化。

错误信封沿用DataError：{error,detail,context}；文件/头/大小/区域/请求错误为400，
未知登记id为404，未鉴权为401。错误不包含token。schema与零/空值语义由测试钉住。
