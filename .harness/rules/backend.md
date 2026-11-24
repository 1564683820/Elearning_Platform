# 后端规则

## 适用范围

适用于 `server/app/**`、`server/database/alembic/**`、`server/requirements.txt`、`server/pyproject.toml`、`server/deploy/Dockerfile` 和 `server/deploy/docker-compose.yml`。

## 必须

- 路由层负责 HTTP 解析、鉴权、调用与响应转换；可复用的业务逻辑放入 `app/services/**` 或已有领域模块。
- 新增路由必须在 `app/main.py` 组装，并保持 `/api/v1` 公开前缀。
- 数据库变更同步 ORM 模型、Pydantic Schema、服务和新 Alembic 迁移。
- 异步路径使用异步数据库/HTTP 调用；不在事件循环内执行可避免的阻塞 I/O。
- 依赖变更必须同时评估 `requirements.txt`、`pyproject.toml` 和 Docker 构建，并明确唯一安装真源。

## 禁止

- 禁止在源码中写入真实凭据、用户数据或生产口令。
- 禁止原地改写已应用迁移，禁止未授权执行数据修复/清理脚本。
- 禁止使用宽泛异常捕获吞掉故障；必须保留可诊断信息，同时避免向客户端暴露敏感内部信息。

## 验证

- `task test`
- 路由/契约变更追加 HTTP 定向验证。
- 数据库变更追加 Alembic upgrade/downgrade 验证，只能在可丢弃的测试库执行。
