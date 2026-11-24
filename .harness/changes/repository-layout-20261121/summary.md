# repository-layout-20261121

## 目标与范围

将仓库归入 `.harness/`、`product/`、`server/` 和 `client/`，保留根目录 `docs/` 和 `scripts/`。本次调整涉及源码、配置与文件系统路径。公开 URL、业务逻辑和数据库迁移链内容保持原样。

## 实施顺序

- [x] 迁移 Agent、技能、后端、两套数据库迁移、部署配置和两个前端应用，按部署单元归位云函数。
- [x] 更新 Harness、Git 忽略规则、Web 静态托管、Alembic、Docker、小程序配置、根级脚本与维护文档。
- [x] 验证统一入口、后端单测、Web 构建、两端 Node 回归、两套迁移目录解析和 Docker Compose 配置。

## 验收与数据边界

根目录统一命令能解析新路径，Web 管理端产物可由 FastAPI 找到，小程序配置和接口测试能解析各自依赖目录。已有本机上传文件继续使用原路径，仓库中新工作区使用 `server/uploads/`。已有数据库和云资源只做本地配置检查。

## 验证结果

- `./harness.ps1 verify` 退出码 0。Harness 检查和 TypeScript 检查通过，解析了 189 个应用 Python 文件。
- `./harness.ps1 unit` 退出码 0，99 项通过。在 Windows 沙箱外重跑解决了 asyncio 回环连接被沙箱阻断的问题。
- `node --test --test-reporter=dot client/admin/tests/*.test.cjs` 和小程序对应命令均退出码 0，分别通过 11 项和 62 项。小程序回归覆盖项目文件和两个源码根路径的解析。
- 在 `client/admin/` 运行本地 Vite 的 `build --outDir <临时目录>`，退出码 0。FastAPI 进程内检查验证了健康接口、Web 首页、静态文件读取和原有上传目录，未进入应用启动生命周期。
- `docker compose -p backend -f server/deploy/docker-compose.yml -f server/deploy/docker-compose.app.yml config --no-env-resolution --quiet` 和 `bash -n server/deploy/docker-deploy.sh` 均退出码 0。
- 演示链 `heads` 返回 `agent_0001`，`upgrade head --sql` 退出码 0。主应用链 `heads` 因已有的 `0012` revision 缺失而退出码 1。对照 Git 检查了全部 32 个迁移文件的内容，以及迁移后的 822 个已跟踪文件路径。
- 根 `scripts/` Python 语法检查退出码 0。额外扫描整个 `server/` 时，旧版 PPT Agent 的 `strategist.py` 第 189 行存在未闭合字符串，在迁移前的 Git 版本中复现。

## 未覆盖范围

本机 Docker 引擎不可用，未执行构建镜像或运行容器。未执行微信开发者工具编译、云函数部署、真实数据库迁移和外部服务联调。

## Web 目录扁平化

将 Web 工程从 `client/admin/` 上移到 `client/`，源码位于 `client/src/`，构建产物位于 `client/dist/`。保留 `client/miniprogram/` 作为微信开发者工具入口。根 npm 命令、Harness、FastAPI 静态目录、Docker 构建、测试依赖和运行说明已同步。

- `./harness.ps1 verify`、`node --test --test-reporter=dot client/tests/*.test.cjs client/miniprogram/tests/*.test.cjs` 均退出码 0。Node 共通过 73 项。
- Vite 临时目录构建、`npm --prefix client run dev -- --version`、Compose 配置校验和 `git diff --check` 均退出码 0。导入 FastAPI 后确认静态目录指向 `client/dist/`，且可找到现有首页文件。
- 本轮未构建 Docker 镜像或执行微信开发者工具编译。
