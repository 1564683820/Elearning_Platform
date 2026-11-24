# 部署资料

本目录只保留可审查的部署示例，不包含旧项目的 `.env.production`、明文凭据或会自动改变主机的一键初始化脚本。

## 文件

- `docker-deploy.sh`：Docker 部署参考脚本，执行前必须逐行审查。
- `Dockerfile`：从仓库根目录构建，使用 `server/`、网页端 `client/dist/` 和 H5 `client/h5/dist/`。
- `docker-compose.yml` 和 `docker-compose.app.yml`：基础设施和应用的 Compose 配置，统一使用 `-p backend` 保留原项目的数据卷。
- `nginx.conf.example`：Nginx 反向代理示例。
- `supervisor.conf`：Supervisor 进程配置示例。

## 部署前置条件

1. 参考 `server/.env.example` 配置部署环境。Compose 示例从 `server/.env` 注入运行时配置，保持该文件在 Git 和镜像之外。
2. 在 `server/.env` 填写 MySQL、Redis、MinIO 和应用签名与加密密钥，并按需配置微信与 AI 服务。手动执行 Compose 时，从仓库根目录传入 `--env-file server/.env`。MinIO 和 Milvus 使用同一组 `MINIO_ROOT_USER`、`MINIO_ROOT_PASSWORD`，Redis 和应用使用同一个 `REDIS_PASSWORD`。
3. 核对 `client/src/api/`、`client/vite.config.ts` 和 `client/miniprogram/miniprogram/utils/api.js` 的 API 前缀与目标域名。
4. 在可丢弃的测试库验证 Alembic 迁移，再制定生产变更窗口和回滚方案。
5. 运行 `task verify`、`task build` 和 `task build-h5`，并完成登录、权限、上传、支付及小程序调用的定向回归。

## H5 部署验收

- 通过同域 HTTPS 提供 `/h5/` 和 `/Elearning/`。两个前端沿用 `/Elearning/api/v1/`，现有 `/api/v1/` 仍供原调用方使用。
- 在目标站点直接打开 `/h5/?session=<会话ID>` 和 `/h5/exams/<试卷ID>/records`，验证登录、刷新、返回原页面及缺失静态资源的 404。为更新后的页面保留 `index.html` 重新验证缓存，哈希静态文件可长期缓存。
- 验证 `/Elearning/api/v1/teaching-assistant/chat/stream` 可逐段返回、教师原件及答题卡上传可完成。沿用 Nginx 的流式代理设置。
- 正式答题卡和照片分别挂载到 `PAPER_FIXED_CARD_LAYOUT_DIR`、`PAPER_SCAN_DIR`。试卷原件和问答附件目录也需使用持久卷。配置及样张登记见[试卷开发方案](../../docs/plans/features/2026-11-22-H5试卷功能开发方案.md)。

## 安全边界

- 本目录中的脚本不得由 Agent 未经确认直接在生产主机执行。
- 各环境使用独立生成的凭据。轮换 `JWT_SECRET` 会使现有令牌失效，轮换 `AES_SECRET_KEY` 前需为已加密的 API Key 制定迁移方案。
- 部署平台 Secret 是凭据真源；文档、Shell 脚本和 Docker 镜像不是凭据存储位置。
