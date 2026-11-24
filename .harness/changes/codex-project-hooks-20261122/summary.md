# 项目级 Codex Hook

Audit-ID 为 `codex-project-hooks-20261122`。

## 决策

项目根目录的 [Hook 配置](../../../.codex/hooks.json) 只注册 `UserPromptSubmit` 和 `Stop`。前者提示架构和验证入口，记录当前 Git 状态。后者检查本轮变更，最多要求补查一次。用现有 Harness 命令完成按范围验收。模块化单体的依赖方向收录在 [架构规则](../../rules/architecture.md)。

参考了 Superpowers 的上下文注入方式和 ECC 的单独 Hook 配置，按 Codex 事件接口编写了本项目脚本。[Superpowers](https://github.com/obra/superpowers/blob/main/hooks/session-start) · [ECC](https://github.com/affaan-m/ECC/blob/main/hooks/hooks.json) · [Codex Hooks](https://learn.chatgpt.com/docs/hooks)

## 验证与边界

`./harness.ps1 verify` 通过。用临时 Git 仓库从含中文和空格的子路径运行了两条 Windows 配置命令，覆盖已有本地改动、无修改轮次、服务反向导入、一次修正上限、新迁移、修改已有迁移、暂存本机配置和 Python 语法错误。另在实际项目中复核现有服务均符合导入规则。

检查范围是本轮 Git 可见的工作区改动。已忽略且未暂存的文件不在范围内。Codex 客户端中的运行需要用户审阅并信任项目配置，本次以脚本和事件模拟验证为准。
