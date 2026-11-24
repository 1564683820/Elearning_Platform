# E-Learning 后端

英语学习小程序后端服务，基于 FastAPI + MySQL + Redis + Milvus。

## 快速开始

### 1. 配置环境变量

```bash
cp server/.env.example server/.env
```

首次配置时复制模板，再填写本机 MySQL 密码和独立的 `SECRET_KEY`、`AES_SECRET_KEY`、`JWT_SECRET`。

### 2. 启动基础设施

```bash
docker compose --env-file server/.env -p backend -f server/deploy/docker-compose.yml up -d redis milvus
```

启动前填写 `REDIS_PASSWORD`、`MINIO_ROOT_USER` 和 `MINIO_ROOT_PASSWORD`。以上命令从仓库根目录执行。另行启动 MySQL，并准备主库和单词库。

### 3. 安装依赖

```bash
pip install -r server/requirements.txt
```

### 4. 启动服务

```bash
cd server

# 开发模式（自动重载）
uvicorn app.main:app --reload --port 8000

# 生产模式
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5. 访问文档

启动后访问：http://localhost:8000/docs

## 项目结构

```
server/
├── app/
│   ├── main.py           ← FastAPI 入口
│   ├── core/config.py     ← 配置管理
│   ├── db/database.py     ← 数据库连接
│   ├── api/deps.py        ← 依赖注入
│   ├── models/            ← ORM 模型
│   ├── schemas/           ← Pydantic 模型
│   ├── routers/           ← API 路由
│   ├── services/          ← 业务逻辑
│   ├── utils/             ← 工具函数
│   └── tasks/             ← 后台任务
├── database/              ← 主库、隔离演示库迁移及配置
├── cloudfunctions/        ← 小程序和独立导入云函数
├── scripts/               ← 脚本
├── tests/                 ← 测试
├── deploy/                ← Docker、Compose 和部署配置
└── requirements.txt       ← 依赖
```

## API 概览

| 模块 | 路径前缀 | 说明 |
|------|----------|------|
| 认证 | `/api/v1/auth` | 登录、用户信息 |
| API Key | `/api/v1/apikeys` | 用户 Key 管理 |
| 单词 | `/api/v1/words` | 单词 CRUD |
| 收藏 | `/api/v1/favorites` | 收藏管理 |
| 训练 | `/api/v1/quiz` | 出题、答题 |
| 情景 | `/api/v1/scenario` | AI 情景生成 |
| 对话 | `/api/v1/chat` | AI 对话 |
| 翻译 | `/api/v1/translate` | 智能翻译 |
| 文档 | `/api/v1/documents` | 文档上传 |
| 统计 | `/api/v1/stats` | 学习数据 |
| 反馈 | `/api/v1/feedbacks` | 用户反馈 |

## 数据库迁移

从仓库根目录执行。主应用旧链存在缺失的 revision，执行迁移前应先检查链的完整性和数据库目标。隔离演示使用 [独立迁移链](../docs/教学任务工作台-启动与验收.md)。

```bash
python -m alembic -c server/database/alembic.ini history
```

## 注意事项

- 后端启动会自动建表并可能补充字段，启动前确认数据库目标
- `.env` 文件包含敏感信息，不要提交到版本库
- Milvus 首次启动需要等待约 30 秒才能就绪
