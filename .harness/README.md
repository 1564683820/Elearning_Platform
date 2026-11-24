# Elearning Harness

本目录是项目面向编码 Agent 的唯一 Harness 真源，用于把项目事实、强制约束、标准流程和需求级经验分开管理。

## 目录职责

- `.agent/`：任务理解、路由和编排角色。
- `wiki/`：当前项目事实和导航，不保存强制流程。
- `rules/`：可判断的工程红线和验证要求。
- `skill/`：特定任务的标准操作流程。
- `changes/`：重要需求的目标、决策、验证、风险和可复用踩坑。

根 `AGENTS.md` 指向本目录的 `AGENTS.md`。当前代码与配置优先于 Wiki，Wiki 优先于历史 Change Audit。项目中原有的多平台规则目录仅作为历史或平台资料，不是 Harness 真源；新增治理内容必须落在本目录并由根入口路由。

## 演进原则

当前版本只建立项目真实需要的最小控制面。只有当某类任务反复出现并形成稳定流程时才新增 Skill。只有机器能够稳定判断时才增加 Hook。

## 项目级 Codex Hook

项目通过 [hooks.json](../.codex/hooks.json) 注册两个事件。Codex 审阅并信任配置后，发送请求时加载项目规则并记录本轮基线，交付前检查本轮 Git 可见的文件改动。Windows 使用 PATH 上的 `python`，其他系统使用 `python3`，需要 Python 3.10+ 和 Git。

交付检查覆盖 `server/app/` 的 Python 语法、服务层反向依赖 HTTP 路由、暂存的本机配置、Git 可见的生成物以及已进入 HEAD 的两套 Alembic 迁移脚本。发现问题时提醒修正一次。Hook 适用于本地 Codex 会话，工程验收仍按 [验证规则](rules/verification.md) 手动运行对应命令。

基线仅在本机临时目录记录 Git 文件路径、状态、大小和修改时间。已经被 Git 忽略且未暂存的文件不在检查范围。
