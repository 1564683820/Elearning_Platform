# Teaching Agent 20261115

Audit-ID：`teaching-agent-20261115`。

## 目标、边界与假设

实施求职展示用 AI 教学工作台：“最近两次考试薄弱点 → 权限内教材检索 → 教案与练习 → 教师审核 → 既有班级试卷发布”。成功标准是可见任务状态、可追溯证据、可恢复执行、版本审核及幂等发布，且有相应验证证据。

不改旧项目 `E:\CodeBuddyprojects\Elearning`，不重新使用触发 `0xc0000022` 的解释器，不重写旧迁移、不操作生产数据或部署。当前工作区为 `E:\Elearning`，使用 bundled Python 建立的 `.venv`。

先前基线提交为 `4c4512a`，登记骨架为 `1d816d5`。基线提交前已将三处 API 密钥改为环境变量，忽略本地词典数据库、调试图片和本机 Agent 配置，未部署云函数或轮换凭据。

用户确认使用本机服务、现有云模型和独立数据库 `elearning_agent_dev` / `elearning_agent_words_dev`。本轮读取到 MySQL80 停止，启动失败原因是 Windows 服务权限，非自动审批拒绝。用户随后明确选择“先完成代码与独立验证”。因此在线环境和真实模型验收延期，不用替身结果冒充。

## 已实现

- 扩展任务产物、版本、审批、发布 ID、租约、错误及重试字段，新增 SQL outbox；公开 run/retry/cancel/artifact/approve/publish/events 接口。
- LangGraph 六节点与两轮校验修正；统计当前班级学生最近两次考试的已批改作答；复用 MemoryService 的教师偏好和 AIService。
- 检索前使用 SQL 文档权限集合过滤 Milvus，返回片段必须仍存在于当前原文；引用保存文档 ID、SHA-256 内容版本和有依据的页码，未知页码不猜测。
- 独立 Windows Worker 使用 Streams、事务 outbox、90秒租约、20秒心跳、过期认领、取消隔离和最多两次暂时性错误重试。
- SQL 节点检查点跳过成功节点；教师编辑增加版本并清除批准，MySQL 行锁下复用 ExamService 发布，顺序重复发布返回同一试卷。
- React 管理端增加任务列表、创建、SSE及断线快照、证据、教案和题目编辑、审核与发布。修复 Vite BASE_URL 与 Router basename 不一致及侧栏前缀重复高亮。
- 安装并固定 LangGraph 1.2.22、Pydantic 2.14.3、FastAPI 0.115.14；原 FastAPI 与新增 AnyIO 冲突已通过升级和回归解决。修复 MySQL/Redis 凭据含保留字符时连接串解析错误。
- 独立 Alembic 冻结链含48张主库表和6张单词库表，限定两个空的本机演示库；旧链仅新增0015 SQL，未原地改写历史文件。补合成数据、自编分页材料、索引脚本、只读检查、50条RAG样本、20个任务场景、启动说明、架构文章及6分钟录屏脚本。

## 实际验证（2026-11-15）

| 命令 | 结果 |
| --- | --- |
| `./harness.ps1 unit` | 退出0；99项通过，包括旧80项及新增19项。SQLite真实事务、ASGI HTTP、实际子进程 kill 后磁盘检查点恢复、租约隔离、Redis故障替身、版本冲突、重复发布和权限撤销 |
| `./harness.ps1 verify` | 退出0；Harness结构、188个应用文件语法、Web类型检查 |
| `./harness.ps1 build` | 退出0；Vite 410 modules，包含部署前缀修复 |
| `python-syntax.py backend/scripts` / `backend/alembic_agent` / `backend/evaluations` | 分别59、2、1个文件通过（后续新增的 crash probe 由 unit 子进程实际运行） |
| `python backend/tests/browser_teaching_tasks.py` | 退出0；无头Edge、合成HTTP fixture，创建/SSE/未保存时禁审核/编辑版本/发布/刷新/平板宽度通过，无pageerror；截图位于忽略目录 `backend/output/teaching-browser/` |
| 根目录 `python -m alembic -c backend/alembic-agent.ini upgrade head --sql` | 退出0；生成48196字节离线SQL，未连接数据库、未执行DDL |
| `python -m pip check` | 退出0；No broken requirements found |
| `git diff --cached --check` 与暂存内容高置信度密钥扫描 | 退出0；新Schema生成器的尾部空格已修复，未检出高置信度密钥 |
| `python backend/scripts/teaching_preflight.py`（进程内指定隔离库名） | 退出1，按预期报告两库、Redis、Milvus未就绪，LLM/Embedding密钥未配置；未输出凭据 |

99项中的实际 kill 测试使用磁盘 SQLite 与确定性工具。它证明节点状态跨进程保存，不能证明真实 MySQL 行锁、Redis consumer reclaim 或云模型的端到端行为。旧套件存在 SQLAlchemy/deprecation 警告，本轮没有通过隐藏警告获得通过结果。

## 偏差、跳过项和风险

- 当前是应用层 SQL 业务检查点及审核等待状态，没有接入 LangGraph 原生 Checkpointer/interrupt/resume；这是相对最初方案的明确差异。
- 未创建数据库、未在线执行迁移、未运行 seed/index、未调用付费模型、未部署、未录制真实链路视频。MySQL并发发布、真实Redis断连重投、登录/上传/学生提交/批改全链路仍待联调。
- 当前生成仅支持四选一；历史阅读/完形子题未展开统计。原文存在不等于语义相关，拒答阈值和教学质量需真实评测；50/20样本不代表已测出质量指标。
- 调用记录含模型、prompt版本、usage和耗时；供应商计费缺失时费用为null。第三方请求完成但检查点未提交时，重启可能重复计费。
- MySQL DDL非事务，独立基线拒绝占用库；不提供未授权的破坏性 downgrade。旧迁移链缺失0012仍未修复，不能对旧库直接执行 upgrade head。

实施清单：`docs/superpowers/plans/2026-11-15-teaching-agent.md`。
启动与验收：`docs/教学任务工作台-启动与验收.md`。
架构与文章初稿：`docs/教学Agent-架构与设计取舍.md`。

## 后续配置更新（2026-11-15）

用户要求参考 `E:\CodeBuddyprojects\Elearning` 的 `.env` 填入当前项目配置。只读解析旧项目 `backend/.env`，将54项受当前 Settings 支持的配置写入新建的 `E:\Elearning\backend\.env`；没有修改旧项目，没有显示或提交凭据。保留两个隔离演示库、独立 Redis 前缀和 Milvus 数据库名称，动画生成目录改为当前工作区 `data/Tu`。

配置经 Settings 解析及逐项读写一致性检查通过；`git check-ignore backend/.env` 确认本机文件被忽略。`./harness.ps1 check-teaching` 退出1：LLM/Embedding 密钥配置存在，两库、Redis与Milvus仍未连通。本次未调用模型、未启动服务、未创建数据库或执行迁移；配置存在不代表密钥有效或真实链路通过。
