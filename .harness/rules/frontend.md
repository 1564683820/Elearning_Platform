# Web 前端规则

## 适用范围

适用于 `client/src/**`、`client/vite.config.ts` 和 `client/package.json`。

## 必须

- 生产源码仅在 `client/src/**` 修改，构建产物由 Vite 生成。
- HTTP 请求优先复用 `src/api/client.ts` 的客户端、鉴权和错误处理；流式或下载场景无法复用时也要保持同一 base path 与 Token 语义。
- 改变 API 路径、字段或认证行为时，追踪 `src/api/**` 和相关页面的所有调用点。
- 保持 TypeScript 类型明确；新增服务数据不以 `any` 规避契约。

## 禁止

- 禁止手改 `client/dist/**` 和 `client/tsconfig.tsbuildinfo`。
- 禁止新增硬编码的生产主机、Token 或密钥。
- 禁止绕过共享 API 层重复实现普通 JSON 请求，除非在变更说明中给出具体原因。

## 验证

- `task typecheck`
- 发布或 Vite 配置变更：`task build`
