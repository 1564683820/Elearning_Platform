# HTTP API 规则

## 适用范围

适用于 `server/app/api/**`、`server/app/routers/**`、`server/app/schemas/**`、`client/src/api/**` 和 `client/miniprogram/miniprogram/utils/api.js` 中的公开 HTTP 契约。

## 必须

- 公开接口继续使用 `/api/v1` 前缀，并在 FastAPI 中保留可用的 OpenAPI Schema。
- 请求与响应数据使用明确的 Pydantic Schema；新字段的可选性、默认值和错误语义必须明确。
- 变更路径、方法、鉴权、字段、状态码、分页或流式协议时，全局检索并同步 Web、小程序及其他调用方。
- 文件上传/下载和 SSE/流式请求必须保持已有鉴权、超时、中断和错误语义。
- 不兼容变更必须记录迁移方式，不能默默破坏存量客户端。

## 禁止

- 禁止只改后端而不检查调用方。
- 禁止在路由层重复大段业务逻辑或返回未约束的内部异常详情。
- 禁止声称客户端类型已自动同步；当前仓库未证实存在 OpenAPI 生成链路。

## 验证

- `task test`
- Web 调用变更：`task typecheck`
- 小程序调用变更：微信开发者工具定向编译与请求回归。
