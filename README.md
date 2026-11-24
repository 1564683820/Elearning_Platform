# Elearning

Elearning 是一个包含 FastAPI 后端、React 管理端和微信小程序的英语学习平台。

## 项目结构

- `.harness/`：工程规则、Agent 角色、技能、项目地图和变更审计。
- `product/`：PRD、设计稿和需求变更。
- `server/`：FastAPI、数据库迁移、云函数和部署配置。
- `client/`：React + TypeScript + Vite 管理端。
- `client/miniprogram/`：微信小程序。用微信开发者工具导入此目录。
- `docs/`：仓库级文档和启动验收说明。
- `scripts/`：数据导入和内容生成工具，运行前需确认数据影响。

## 快速开始

在仓库根目录运行 `task setup` 安装依赖。配置 `server/.env` 并启动本地 MySQL 后，在两个 PowerShell 窗口分别启动服务。

后端：

```powershell
Set-Location "E:\Elearning\server"
& "..\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```powershell
Set-Location "E:\Elearning\client"
npm run dev
```

从仓库根目录也可运行 `task dev-backend` 和 `task dev-web`。其中 `dev-backend` 会先执行数据库连接检查。

### Go Task 开发命令

安装 Go Task v3 与 PowerShell 7（`pwsh`），并确保它们在 PATH 中。Windows 可运行 `winget install --id Task.Task --exact`，然后打开新终端，通过 `task --version` 和 `pwsh --version` 确认安装。

| 命令 | 启动范围 |
| --- | --- |
| `task --list` | 列出开发命令 |
| `task dev-web` | Web 管理端，访问 `http://localhost:5173/Elearning/` |
| `task dev-h5` | H5，先在 `client/` 执行 `npm ci`。入口为 `http://localhost:5174/h5/`，API 代理到同一后端 |
| `task dev` | 并行启动 Web 和 H5。H5 入口缺失时提前退出 |
| `task dev-backend` | FastAPI，按需在另一个终端启动 |

命令命名、联合启动范围和验收要求见[架构规则](.harness/rules/architecture.md#开发命令设计)。

## 验证

```powershell
task lint
task test
task typecheck
task build
task build-h5
task verify
```

`verify` 默认只运行无写入检查。生产构建需显式运行 `build`。

## 环境配置

1. 首次配置时，复制 `server/.env.example` 为 `server/.env`。
2. 在本机或部署平台配置数据库、Redis、Milvus、微信和 AI 服务凭据，并分别设置必填的 `SECRET_KEY`、`AES_SECRET_KEY` 和 `JWT_SECRET`。
3. 不要将 `.env`、Token、AppSecret 或生产数据提交到仓库。
4. 如需本地 Redis 和 Milvus，先在 `server/.env` 中填写 `REDIS_PASSWORD`、`MINIO_ROOT_USER` 和 `MINIO_ROOT_PASSWORD`，再从仓库根目录运行 `docker compose --env-file server/.env -p backend -f server/deploy/docker-compose.yml up -d redis milvus`。Compose 项目名沿用原值，现有数据卷可继续使用。

更详细的项目边界和任务路由见 [AGENTS.md](AGENTS.md) 与 [.harness/wiki/项目地图.md](.harness/wiki/项目地图.md)。

## 启动故障排查

根目录 `npm run dev` 启动 Web，访问 `http://localhost:5173/Elearning/`；另开终端运行 `task dev-backend`。

`task dev-backend` 会在启动前对主库和单词库执行只读连接检查。若提示 MySQL error 2003，先检查 MySQL 服务是否运行。Windows 安装的 `MySQL80` 可在管理员 PowerShell 中执行 `Start-Service MySQL80`。随后按 `.env.example` 在本机配置 `server/.env` 中的数据库连接。

后端现有生命周期会自动建表及补充字段，连接已有数据库前应确认数据库目标和迁移授权。

可先运行 `task check-database` 单独检查两个数据库。此命令只执行 `SELECT 1`，不启动应用、不建表、不迁移。错误 2003 表示服务或网络不可达，1045 表示认证失败，1049 表示库不存在。`.env.example` 中未列出的单词库名称可通过 `WORDS_DATABASE` 配置。

新工作区的上传目录是 `server/uploads/`。旧工作区如果仍有 `backend/uploads/` 且尚未创建 `server/uploads/`，应用会继续使用旧目录。
