# Elearning 最小 Harness 建设

- Audit-ID：`harness-bootstrap-20260921`
- 类型：架构治理
- 日期：2026-09-21

## 目标与成功标准

- 在 `E:\Elearning` 建立独立工作区，以旧项目为只读源迁入可维护代码。
- 建立单一 Harness 入口，让 Agent 能识别后端、Web、小程序、生成物和高风险路径。
- 建立基于当前代码事实的项目地图、路由规则、系统化调试流程和统一命令入口。
- 验证 Harness 目录和 Skill frontmatter，并对可用的工程检查给出真实结果。

## 非目标

- 不重写现有业务模块。
- 不修改或清理旧项目；虚拟环境、生成物、上传文件、本地密钥和历史平台规则不迁入新目录。
- 不在本变更中统一 Python 依赖、新增完整测试/Lint/CI，或处理存量凭据。

## 关键决策

- `.harness/` 是新治理内容的唯一真源，根 `AGENTS.md` 只负责路由。
- 因项目当前主要在 Windows 上开发，统一命令入口采用 PowerShell `harness.ps1`；使用 Codex bundled Python 创建独立 `.venv`。
- 第一版仅提供一个系统化调试 Skill，不复制参考清单中的大量通用 Skill。

## 模块级变更

- 从旧项目迁入 `backend/`、`web-admin/`、`wechart/`、`cloudfunctions/`、`scripts/`、`docs/` 和经筛选的 `deploy/`。
- 新增根 `README.md`、`.gitignore`、`AGENTS.md` 和 `.harness/` 控制面。
- 新增 `harness.ps1` 和 `.harness/scripts/validate.ps1` 作为统一命令及自检入口。

## 验证与验收

- `./harness.ps1 lint`：通过，15 个必要文件、1 个 Skill。
- `./harness.ps1 test`：通过，独立 `.venv` 解析 180 个 Python 文件。
- `./harness.ps1 typecheck`：通过。
- `./harness.ps1 build`：通过，Vite 成功处理 407 个模块。
- FastAPI 导入冒烟：通过，装配 322 个路由。

## 风险与跳过项

- 当前没有正式单元测试、代码 Lint 或 CI，统一入口不能替代后续建设。
- Python 依赖在 `pyproject.toml` 与 `requirements.txt` 间漂移。
- `npm ci` 报告 17 个依赖漏洞（4 个 moderate、13 个 high），需单独评估升级，本次未运行可能产生破坏性升级的自动修复。
- 旧项目的明文部署环境文件和初始化脚本未迁入，但原有密钥仍应在原系统中单独轮换。

## 需求级踩坑

| Pitfall-Key | 路径（glob） | 教训 | 关联 Commit |
|---|---|---|---|
| api-base-paths-diverge | `web-admin/src/api/**`, `wechart/miniprogram/utils/api.js`, `backend/app/**` | API 前缀与主机在多端分散，改动契约必须全局搜索调用方。 | 待提交 |
| generated-assets-excluded | `web-admin/dist/**` | 重建工作区不迁入历史构建产物，必须由当前源码重新构建。 | 待提交 |
| dependency-manifests-drift | `backend/requirements.txt`, `backend/pyproject.toml` | 依赖变更要同时评估两个声明文件与 Docker 安装链路。 | 待提交 |

## Git 提交索引

- 待收口
