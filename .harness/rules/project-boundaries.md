# 项目边界规则

## 适用范围

适用于整个仓库的代码、配置、数据和文档修改。

## 必须

- 修改前检查 Git 状态，识别目标文件中的用户现有修改。
- 生产 Web 功能改在 `client/src/**`，后端改在 `server/app/**`，小程序改在 `client/miniprogram/miniprogram/**`。
- 跨端能力要追踪真实调用链，不得仅凭目录名或历史文档推断。
- 修改数据结构时新建 Alembic 迁移，并保持 ORM、Schema、API 和调用方一致。

## 禁止

- 禁止手工修改 `client/dist/**`、`**/node_modules/**`、`**/__pycache__/**` 或 `*.tsbuildinfo`。
- 禁止将 `prototype/**`、`Create_Figma_Design_temp/**` 或 `figma_design_extracted/**` 当作生产代码直接修改，除非用户明确指定。
- 禁止未经确认运行 `scripts/**` 中的导入、清理、迁移或生成脚本。
- 禁止删除、格式化或批量移动各级 `data/**` 和 `uploads/**` 内容，除非获得针对精确目标的授权。
- 禁止原地改写已使用的 `server/database/alembic/versions/**` 迁移。

## 验证

- `task lint`
- 再按受影响端执行 `.harness/rules/verification.md` 中的命令。
