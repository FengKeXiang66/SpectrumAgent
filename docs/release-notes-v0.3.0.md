# v0.3.0 release notes（草稿）

里程碑B（TASK-07 12.5–12.7）标注JSON与训练MAT自动化验收完成，发布由科祥统一执行。当前产品配置仍为0.1.3，未打v0.3.0 tag、未推送或创建Release。验收记录见milestone07/evidence/12.7/acceptance-map.md。

## 用户可感知变化

- 多边形顶点、区域边界、来源和置信度保存在标注JSON主文档中；草稿持久化，重开后从JSON恢复画布。原有确认区域、不确定、擦除、撤销和保存流程继续可用。
- 草稿修改带revision校验，多处同时编辑时旧版本会收到冲突提示，需重新读取；不再用后写静默覆盖前写。
- 确认标注版本生成四件套：标注JSON、label map、类表和样本谱。JSON重放与计算位图逐像素一致，旧三件套版本继续可回看。
- 新“确认版本并生成训练MAT”入口在确认前显示预计体积，超过2GiB需再次确认；对话HUMAN_CHECK卡片使用同一个体积闸。
- 训练MAT存原始DN及项目原始类下标，并带行列、源dtype/字节序、波长和溯源元数据；不烤入预处理结果。MAT是导出物，平台内部计算仍使用原始cube及确认版label map。
- 跨类重叠必须先处理，可删除区域、改类、擦除或标不确定。画布可用REST冲突位置，助手只接收数量与文字。
- 助手可读取草稿摘要、在人工批准后确认版本并生成MAT、查询导出摘要；沿用编排地基的澄清、工具步骤与错误处理。工具结果来自确定性服务，LLM不产生数值或几何。
- MAT生成失败保留已确认版本，提示失败原因，可在service层重建。覆写版本立即失效旧MAT，避免导出已被替换的标签；成功后重新生成。

## 已知限制

- 草稿不能直接运行预处理，须先确认出标注版本；不提供版本恢复为草稿。
- draft_add_region/draft_select_candidates、gesture引用与candidates端点仍等待手势联调段，SLIC候选选择语义待定。本版不提供“让LLM画几何”。
- API key只在sidecar进程内存持有，重启后需重新输入；默认不预置厂商。真实云端验证由科祥使用自己的key执行。
- 固定IPC响应上限8MiB，大MAT通过API/脚本消费；本版无应用内大文件下载UI。大RLE草稿同样受限，尚未定义分页/截断。
- 同步MAT生成的合成固定尺寸性能门通过；真实NAS数据耗时、物理谱值与完整安装态UI尚待本机冒烟，自动化结果不替代它们。

## 发布前缓测与版本纪律

安装/首跑、真实NAS PE cube→分割→标注→真实DeepSeek对话确认→MAT生成/API下载→版本回看及S05全链路UI，连同签名/SmartScreen、干净机、长路径和reboot，均由科祥按smoke-checklist.md执行并留记录。

**tag时唯一版本号来源的修改为src-tauri/tauri.conf.json的version→0.3.0**；打包、安装验证、tag/推送/Release及manifest归档由科祥执行。12.7不改tauri.conf.json，不改docs/release_manifest.md；v0.3.0 manifest条目留待实际tag和安装包哈希复算后回填，不补造发布信息。
