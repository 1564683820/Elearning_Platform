import asyncio
import json
import logging
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.frontend import FrontendMiddleware
from app.core.paths import SERVER_DIR, UPLOADS_DIR


class BigIntSafeJSONResponse(JSONResponse):
    """将超出 JS Number 安全范围 (2^53) 的大整数转为字符串。

    Snowflake 生成的 ID 可达 10^18 量级，JavaScript JSON.parse 会丢失精度。
    此编码器在序列化前将超出安全范围的整数转换为字符串，确保前后端 ID 一致。
    """
    MAX_SAFE = 2 ** 53

    _convert_count = 0  # 诊断计数器

    @staticmethod
    def _convert(obj):
        if isinstance(obj, dict):
            return {k: BigIntSafeJSONResponse._convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [BigIntSafeJSONResponse._convert(v) for v in obj]
        if isinstance(obj, int) and (obj > BigIntSafeJSONResponse.MAX_SAFE or obj < -BigIntSafeJSONResponse.MAX_SAFE):
            return str(obj)
        return obj

    def render(self, content) -> bytes:
        converted = self._convert(content)
        return json.dumps(
            converted,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")

# 配置根日志 — 确保所有 logger.info() 能输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    force=True,
)
from sqlalchemy import create_engine, text, inspect
from app.core.config import get_settings
from app.db.database import Base, WordBase, async_session as get_async_session
from app.utils.redis_client import close_redis
from app.services.ppt_theme_service import PPTThemeService

# 导入所有模型，确保 Base.metadata 包含所有表
from app.models import user, word, quiz, chat, stats  # noqa: F401
from app.models import class_models  # noqa: F401
from app.models import exam_models  # noqa: F401
from app.models import membership_models  # noqa: F401
from app.models import textbook_models  # noqa: F401
from app.models import ppt_models  # noqa: F401
from app.models import video_models  # noqa: F401
from app.models import collaboration_models  # noqa: F401
from app.models import invite_code  # noqa: F401
from app.models import teacher_memory  # noqa: F401
from app.models import agent_skill  # noqa: F401

# 导入路由
from app.api.v1.auth import router as auth_router, apikey_router
from app.api.v1.words import router as words_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.quiz import router as quiz_router
from app.api.v1.chat import router as chat_router
from app.api.v1.translate import router as translate_router
from app.api.v1.scenario import router as scenario_router
from app.api.v1.reading import router as reading_router
from app.api.v1.listening import router as listening_router
from app.api.v1.stats import router as stats_router
from app.api.v1.documents import router as documents_router
from app.api.v1.feedbacks import router as feedbacks_router
from app.api.v1.teacher import router as teacher_router
from app.api.v1.exam import router as exam_router, student_router as student_exam_router
from app.api.v1.membership import router as membership_router
from app.api.v1.textbook import router as textbook_router
from app.api.v1.ppt import router as ppt_router
from app.ppt_generator.pptx_editor.editor_routes import router as ppt_editor_router
from app.api.v1.knowledge_graph import router as kg_router
from app.api.v1.video import router as video_router
from app.api.v1.collaboration import router as collaboration_router
from app.api.v1.system_status import router as system_status_router
from app.api.v1.ai_chat import router as ai_chat_router
from app.api.v1.class_router import router as class_router
from app.api.v1.mistake_book import router as mistake_book_router
from app.api.v1.question_bank import router as question_bank_router
from app.api.v1.voice import router as voice_router
from app.api.v1.admin import router as admin_router
from app.api.v1.teaching_assistant import router as teaching_assistant_router
from app.api.v1.agent_skill import router as agent_skill_router


def _migrate_favorite_table(sync_engine):
    """为已有 favorite 表补充新增字段"""
    logger = logging.getLogger("migration")
    try:
        inspector = inspect(sync_engine)
        existing_columns = {c["name"] for c in inspector.get_columns("favorite")}
        add_cols = []
        if "word" not in existing_columns:
            add_cols.append("ADD COLUMN `word` VARCHAR(255) DEFAULT '' COMMENT '单词文本'")
        if "phonetic" not in existing_columns:
            add_cols.append("ADD COLUMN `phonetic` VARCHAR(255) DEFAULT '' COMMENT '音标'")
        if "meaning" not in existing_columns:
            add_cols.append("ADD COLUMN `meaning` VARCHAR(1024) DEFAULT '' COMMENT '释义'")
        if "content" not in existing_columns:
            add_cols.append("ADD COLUMN `content` TEXT COMMENT '文段内容'")
        if "passage_type" not in existing_columns:
            add_cols.append("ADD COLUMN `passage_type` VARCHAR(50) DEFAULT '' COMMENT '文段类型'")
        if add_cols:
            stmt = f"ALTER TABLE `favorite` {', '.join(add_cols)}"
            with sync_engine.connect() as conn:
                conn.execute(text(stmt))
                conn.commit()
            logger.info(f"[lifespan] favorite 表迁移完成: {len(add_cols)} 个新字段")
    except Exception as e:
        logger.warning(f"[lifespan] favorite 表迁移跳过: {e}")


def _migrate_lesson_ppt(sync_engine):
    """为已有 lesson_ppt 表补充新增字段"""
    logger = logging.getLogger("migration")
    try:
        inspector = inspect(sync_engine)
        existing_columns = {c["name"] for c in inspector.get_columns("lesson_ppt")}
        add_cols = []
        if "spec_lock" not in existing_columns:
            add_cols.append(
                "ADD COLUMN `spec_lock` JSON DEFAULT NULL "
                "COMMENT '设计规格锁定 Phase3.3（视觉风格/配色/字体/布局/节奏）'"
            )
        if add_cols:
            stmt = f"ALTER TABLE `lesson_ppt` {', '.join(add_cols)}"
            with sync_engine.connect() as conn:
                conn.execute(text(stmt))
                conn.commit()
            logger.info(f"[lifespan] lesson_ppt 表迁移完成: {len(add_cols)} 个新字段")
    except Exception as e:
        logger.warning(f"[lifespan] lesson_ppt 表迁移跳过: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表，关闭时释放资源"""
    settings = get_settings()
    # 启动：主库同步引擎自动建表
    sync_engine = create_engine(settings.SYNC_DATABASE_URL)
    Base.metadata.create_all(sync_engine)
    # 给已有表补充新增字段（供已有数据库使用）
    _migrate_favorite_table(sync_engine)
    _migrate_lesson_ppt(sync_engine)
    sync_engine.dispose()
    print(f"[lifespan] 主库表初始化完成 ({len(Base.metadata.tables)} 张表)")

    # 初始化 PPT 内置主题
    try:
        async with get_async_session() as db_session:
            await PPTThemeService.init_builtin_themes(db_session)
        print("[lifespan] PPT 内置主题初始化完成")
    except (Exception, asyncio.CancelledError) as e:
        print(f"[lifespan] PPT 内置主题初始化跳过: {e}")

    # 启动：单词库同步引擎自动建表
    sync_words_engine = create_engine(settings.SYNC_WORDS_DATABASE_URL)
    WordBase.metadata.create_all(sync_words_engine)
    sync_words_engine.dispose()
    print(f"[lifespan] 单词库表初始化完成 ({len(WordBase.metadata.tables)} 张表)")

    # 启动时预连接 Milvus 并加载所有集合到内存
    # ⚠️ get_milvus_client() 是同步调用（pymilvus REST 客户端），会阻塞事件循环。
    # 放到线程池执行并设置 15 秒超时，防止 Milvus 不可达时卡死整个服务器。
    try:
        from app.services.embedding_service import EmbeddingService
        await asyncio.wait_for(
            asyncio.to_thread(EmbeddingService.get_milvus_client),
            timeout=15.0,
        )
        print("[lifespan] Milvus 连接 + 集合加载完成")
    except asyncio.TimeoutError:
        print("[lifespan] Milvus 初始化超时 (不影响非向量功能)")
    except (Exception, asyncio.CancelledError) as e:
        print(f"[lifespan] Milvus 初始化失败 (不影响非向量功能): {e}")

    yield
    # 关闭：释放 Redis 连接（加超时保护，防止 shutdown 卡死）
    try:
        await asyncio.wait_for(close_redis(), timeout=5.0)
    except asyncio.TimeoutError:
        print("[lifespan] Redis 关闭超时，强制继续")
    except Exception as e:
        print(f"[lifespan] Redis 关闭异常: {e}")


app = FastAPI(
    title=get_settings().APP_NAME,
    version=get_settings().APP_VERSION,
    lifespan=lifespan,
    default_response_class=BigIntSafeJSONResponse,
)

# CORS — 开发环境使用具体 origin，生产环境自动适配
# 生产环境中 admin 前端与 API 同源，不需要 CORS 也能正常工作
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "https://dbgraph.bond",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 网页端与 H5 共用 API，独立加载各自的构建产物。
_CLIENT_DIR = SERVER_DIR.parent / "client"
app.add_middleware(FrontendMiddleware, web_dist=_CLIENT_DIR / "dist", h5_dist=_CLIENT_DIR / "h5" / "dist")

# 挂载上传目录（教材页面图片等静态资源）
_UPLOADS_BASE = UPLOADS_DIR
os.makedirs(_UPLOADS_BASE, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_UPLOADS_BASE), name="uploads")

# 全局异常处理
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"code": 1, "message": str(exc)})


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    import traceback
    tb = traceback.format_exc()
    print(f"[500 ERROR] {request.method} {request.url.path} | {type(exc).__name__}: {exc}\n{tb}", flush=True)
    logger = logging.getLogger("fastapi")
    logger.error("500 | %s %s | %s: %s", request.method, request.url.path, type(exc).__name__, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"code": -1, "message": "服务器内部错误"})


# 注册路由
app.include_router(auth_router, prefix="/api/v1")
app.include_router(apikey_router, prefix="/api/v1")
app.include_router(words_router, prefix="/api/v1")
app.include_router(favorites_router, prefix="/api/v1")
app.include_router(quiz_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(translate_router, prefix="/api/v1")
app.include_router(scenario_router, prefix="/api/v1")
app.include_router(reading_router, prefix="/api/v1")
app.include_router(listening_router, prefix="/api/v1")
app.include_router(stats_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(feedbacks_router, prefix="/api/v1")
app.include_router(teacher_router, prefix="/api/v1")
app.include_router(exam_router, prefix="/api/v1")
app.include_router(student_exam_router, prefix="/api/v1")
app.include_router(membership_router, prefix="/api/v1")
app.include_router(textbook_router, prefix="/api/v1")
app.include_router(ppt_router, prefix="/api/v1")
app.include_router(kg_router, prefix="/api/v1")
app.include_router(video_router, prefix="/api/v1")
app.include_router(collaboration_router, prefix="/api/v1")
app.include_router(system_status_router, prefix="/api/v1")
app.include_router(ai_chat_router, prefix="/api/v1")
app.include_router(class_router, prefix="/api/v1")
app.include_router(mistake_book_router, prefix="/api/v1")
app.include_router(question_bank_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(teaching_assistant_router, prefix="/api/v1")
app.include_router(agent_skill_router, prefix="/api/v1")
from app.api.v1.teaching_tasks import router as teaching_tasks_router
app.include_router(teaching_tasks_router, prefix="/api/v1")
app.include_router(ppt_editor_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"name": get_settings().APP_NAME, "version": get_settings().APP_VERSION}
