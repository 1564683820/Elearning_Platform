# Startup repair 2026-11-14

## 目标及范围

恢复本地启动入口和开发 API 转发，定位后端启动阻塞；不改变业务行为、不执行数据库迁移。

## 根因证据

- 根目录 package.json 没有 dev 脚本；Web 在子目录中可以启动。
- Axios 使用 /Elearning/api/v1，但 Vite 原先只代理 /api，导致请求未送达后端。
- 项目 backend/.env 不存在。本机 MySQL80 已安装但停止；沙箱外只读连接确认 127.0.0.1:3306 拒绝连接（10061）。
- Python 独立环境可用，FastAPI 应用导入成功。

## 修复

- 增加根目录 dev、dev:web、dev:backend 脚本。
- Vite 增加 /Elearning/api 代理，去掉 /Elearning 后转发至本机后端，支持 WebSocket。
- Harness 后端启动前增加两个数据库的只读 SELECT 1 检查，输出脱敏错误及配置指引。
- README 补充启动与数据库排查方法。

## 验证及未完成项

- Vite 配置加载及代理 rewrite 回归通过。
- `./harness.ps1 verify` 退出码 0：Harness、180 个后端文件语法及 TypeScript 检查通过。
- `npm --prefix web-admin run build` 退出码 0：407 个模块生产构建通过。
- Python 环境与 FastAPI 导入通过。
- 数据库预检正确报告 MySQL error 2003。
- 尝试启动 MySQL80，Windows 拒绝服务控制访问；服务仍停止，未进行建表、迁移或业务数据操作。
- 后端完整启动、登录和业务验收被数据库服务/本机配置阻塞。

## 本轮复查与修复

- 再次复现 `dev-backend` 退出：MySQL error 2003；沙箱外确认 `MySQL80` 为 Stopped/Manual，且 `backend/.env` 缺失。
- 尝试启动服务被 Windows 服务控制权限拒绝；没有执行数据库创建、迁移或业务写入。
- 新增 `./harness.ps1 check-database` 独立只读预检入口，按连接失败、认证失败和库不存在分别提供操作指引；不输出底层异常中的凭据。
- 后端导入成功（323 条路由）；`verify` 通过。新增预检回归覆盖两库只读检查、资源释放和错误脱敏，结果见本轮交付。
- `./.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_startup_preflight.py -v`：3 项通过；`./harness.ps1 verify`：退出码 0（181 个后端源文件语法、Harness 结构和 Web 类型检查）。
- `./harness.ps1 check-database`：退出码 1，准确报告 MySQL error 2003 及管理员启动指引；真实数据库连接仍未恢复。
- 沙箱内 Vite HTTP 探测超时，改在沙箱外运行 `npm --prefix web-admin run dev -- --host 127.0.0.1 --port 5175 --strictPort` 后，首页返回 HTTP 200，包含当前 `/src/main.tsx` 入口。保留该前端开发服务器供用户查看。
- 未执行后端生命周期、登录和业务端到端验证：仍缺本机数据库服务与连接配置，且生命周期含自动建表/字段迁移。
