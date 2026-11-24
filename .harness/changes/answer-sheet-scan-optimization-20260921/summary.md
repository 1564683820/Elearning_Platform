# 答题卡扫码批改优化

## 目标

参考 `E:\CodexSave\AnswerpaperScan` 的拍摄确认与识别置信思路，优化“电脑生成二维码、手机拍摄答题卡、自动批改”的完整链路。

## 变更

- 将二维码中的长期登录 Token 替换为默认 10 分钟有效、仅限当前试卷的扫描会话 Token。
- 普通 API、下载接口和 WebSocket 显式拒绝扫描会话 Token。
- 移动端统一走现有 OMR 扫描器，移除界面和请求中的“多模态批改”误导。
- 手机拍照上传前检查亮度、曝光、对比度和清晰度；不合格时保留相机并提示重拍。
- 摄像头优先使用后置高分辨率画面，裁剪后限制图片边长与 JPEG 质量。
- 上传接口只接受 JPEG、PNG、WebP，限制为 12MB/4000 万像素，并校验图片签名与声明类型后生成扩展名。
- 扫描与考号修正接口校验所选班级归属，防止通过篡改 `class_id` 跨班匹配花名册。
- 移动页面从当前 URL 推导 API 前缀，兼容 `/api/v1` 与 `/Elearning/api/v1` 部署。
- 电脑端二维码展示倒计时、过期遮罩与刷新入口；弹窗打开期间每 5 秒静默刷新批改结果。

## 兼容性

- 普通教师登录 Token 仍可调用扫描接口，便于桌面端和已有内部调用。
- 新扫描 Token 只能访问对应试卷的移动页、扫描批改及该试卷提交的考号修正。
- 扫描识别核心继续使用项目现有透视校正 OMR 实现，没有用参考项目的简化网格算法替换。

## 验证

- `./harness.ps1 test`：通过，180 个后端源码文件语法回归通过。
- `..\\.venv\\Scripts\\python.exe -m unittest tests.test_scan_session_security -v`：通过，2 个扫描令牌测试通过。
- FastAPI OpenAPI 导入检查：通过，289 个路径，3 个扫描相关路径均存在。
- `./harness.ps1 typecheck`：通过。
- `./harness.ps1 build`：通过，Vite 转换 407 个模块并生成生产包。
- `./harness.ps1 verify`：通过，Harness 结构、后端语法和 TypeScript 类型检查通过。
- 移动端内联 JavaScript 抽取后执行 `node --check -`：通过。
