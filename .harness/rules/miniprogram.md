# 微信小程序与云函数规则

## 适用范围

适用于 `client/miniprogram/**` 和 `server/cloudfunctions/**`。

## 必须

- 修改前明确目标是小程序端、`server/cloudfunctions/miniprogram` 还是 `server/cloudfunctions/import-dict`，不得在两套云函数间凭名称猜测部署目标。
- 数据访问优先经 `client/miniprogram/miniprogram/utils/api.js`；改变 `USE_CLOUDBASE`、`BASE_URL` 或鉴权行为前必须确认目标环境。
- 页面修改保持 `.js/.json/.wxml/.wxss` 组合完整，并检查 `app.json` 的注册、分包和权限。
- 云函数依赖变更在函数自己的 `package.json` 管理，不依赖仓库根 `node_modules`。
- 涉及微信 API、隐私权限、支付或登录时，同时读取安全规则。

## 禁止

- 禁止提交 `project.private.config.json` 中新增的本机信息或任何真实密钥。
- 禁止在新代码中硬编码生产主机、环境 ID、Token 或支付凭据。
- 禁止未经用户确认上传、部署云函数或发布小程序。

## 验证

- `task lint`
- 微信开发者工具编译受影响项目。
- 对受影响页面或云函数执行定向回归，无法自动执行时在交付中标注。
