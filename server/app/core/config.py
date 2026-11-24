from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache
from sqlalchemy.engine import URL

from app.core.paths import SERVER_DIR

_ENV_FILE = SERVER_DIR / ".env"


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "E-Learning API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str = Field(min_length=1, repr=False)

    # MySQL — 主库（用户/班级/教材/试卷等）
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_DATABASE: str = "elearningtest"
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = Field(default="", repr=False)

    def mysql_connection_kwargs(self) -> dict[str, str | int]:
        return {
            "host": self.MYSQL_HOST,
            "port": self.MYSQL_PORT,
            "user": self.MYSQL_USER,
            "password": self.MYSQL_PASSWORD,
        }

    def _mysql_url(self, driver: str, database: str) -> str:
        return URL.create(driver, username=self.MYSQL_USER, password=self.MYSQL_PASSWORD,
            host=self.MYSQL_HOST, port=self.MYSQL_PORT, database=database,
            query={'charset': 'utf8mb4'}).render_as_string(hide_password=False)

    @property
    def DATABASE_URL(self) -> str:
        return self._mysql_url('mysql+aiomysql', self.MYSQL_DATABASE)

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return self._mysql_url('mysql+pymysql', self.MYSQL_DATABASE)

    # MySQL — 单词专用库
    WORDS_DATABASE: str = "elearnword"

    @property
    def WORDS_DATABASE_URL(self) -> str:
        return self._mysql_url('mysql+aiomysql', self.WORDS_DATABASE)

    @property
    def SYNC_WORDS_DATABASE_URL(self) -> str:
        return self._mysql_url('mysql+pymysql', self.WORDS_DATABASE)

    # Redis
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = Field(default="", repr=False)
    REDIS_PREFIX: str = "elearn:"

    @property
    def REDIS_URL(self) -> str:
        return URL.create('redis', username='' if self.REDIS_PASSWORD else None,
                          password=self.REDIS_PASSWORD or None, host=self.REDIS_HOST,
                          port=self.REDIS_PORT, database='0').render_as_string(hide_password=False)

    # Milvus
    MILVUS_HOST: str = "127.0.0.1"
    MILVUS_PORT: int = 19530
    MILVUS_DATABASE: str = "elearningtest_v2"

    # AI - LLM
    LLM_API_BASE: str = "https://api.siliconflow.cn/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"

    # AI - 多模态批卷
    MULTIMODAL_API_BASE: str = "https://api.siliconflow.cn/v1"
    MULTIMODAL_API_KEY: str = ""
    MULTIMODAL_MODEL: str = "Qwen/Qwen2.5-VL-7B-Instruct"

    # AI - Embedding
    EMBEDDING_API_BASE: str = "https://api.siliconflow.cn/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
    EMBEDDING_DIM: int = 1024

    # 安全
    AES_SECRET_KEY: str = Field(min_length=1, repr=False)
    JWT_SECRET: str = Field(min_length=1, repr=False)
    JWT_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"
    SCAN_SESSION_EXPIRE_MINUTES: int = 10

    # 教师注册邀请码
    TEACHER_INVITE_CODE: str = Field(default="", repr=False)

    # 微信
    WX_APPID: str = ""
    WX_APP_SECRET: str = ""

    # 微信支付
    WX_PAY_MCHID: str = ""        # 商户号
    WX_PAY_API_KEY: str = ""      # API v3 密钥
    WX_PAY_NOTIFY_URL: str = "https://api.example.com/api/v1/membership/payment-callback"  # 支付回调地址

    # CDN / 对象存储（教材点读资源）
    CDN_BASE_URL: str = ""  # CDN 基础 URL（留空 = 本地服务器直连，生产环境设为 CDN 地址如 https://cdn.elearning.com）
    CDN_BUCKET: str = "textbook"  # 对象存储 Bucket 名

    # 视频合成
    VIDEO_OUTPUT_DIR: str = "./output/video"  # 视频合成临时输出目录

    # 腾讯云 COS 对象存储
    COS_SECRET_ID: str = ""
    COS_SECRET_KEY: str = ""
    COS_REGION: str = "ap-guangzhou"
    COS_BUCKET: str = "textbook"

    # TTS 配置
    TTS_PROVIDER: str = "volc"    # TTS 提供商: volc, openai, azure, siliconflow
    TTS_API_KEY: str = ""         # TTS API Key（如区分于 LLM Key）
    TTS_VOICE: str = "BV001_streaming"  # 默认 Speaker ID（v3 豆包大模型）
    TTS_PERSIST_DIR: str = ""     # TTS 永久缓存目录（空=自动设为 uploads/textbook/tts）
    # 火山引擎 TTS（v3 豆包大模型语音合成 API）
    VOLC_APP_ID: str = ""          # 应用ID（纯数字，从语音控制台应用列表获取）
    VOLC_TTS_ACCESS_KEY: str = ""  # API 访问密钥 Access Key（控制台 → 访问控制 → API 访问密钥获取，AKLT 开头）

    # 火山引擎端到端实时语音（Realtime API）
    # 复用 VOLC_APP_ID 和 VOLC_TTS_ACCESS_KEY 作为 App-ID 和 Access-Key
    VOLC_REALTIME_APP_ID: str = ""       # 默认为 VOLC_APP_ID，可单独指定
    VOLC_REALTIME_ACCESS_KEY: str = ""   # 默认为 VOLC_TTS_ACCESS_KEY，可单独指定

    # 微动图生成（硅基流动 Z-Image-Turbo 阿里通义）
    ANIMATION_PROVIDER: str = "siliconflow"  # 动图生成提供商: openai, siliconflow, stability
    ANIMATION_MODEL: str = "Tongyi-MAI/Z-Image-Turbo"  # Z-Image-Turbo 阿里通义 6B 文生图
    ANIMATION_API_BASE: str = "https://api.siliconflow.cn/v1"
    ANIMATION_API_KEY: str = ""
    ANIMATION_BATCH_SIZE: int = 10  # 批量生成微动图时累计动图张数上限（非页数，角色+背景+整页）
    ANIMATION_LOCAL_DIR: str = ""  # 动图本地保存目录（空=自动设为项目根 data/Tu/）

    # MinerU PDF → Markdown 精准解析 API（SaaS, api.mineru.net）
    MINERU_API_KEY: str = ""                # MinerU 平台 Token（JWT）
    MINERU_API_BASE: str = "https://mineru.net/api/v4"  # v4 精准解析 API 端点
    MINERU_PROXY: str = ""                  # MinerU CDN 下载代理（如 socks5://127.0.0.1:10800），留空=直连

    # AI 视频生成（阿里云百炼 通义万相）
    VIDEO_PROVIDER: str = "bailian"  # 视频生成提供商: bailian, volc, tencent
    VIDEO_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    VIDEO_API_KEY: str = ""
    VIDEO_MODEL: str = "wan2.7-t2v"  # 通义万相文生视频模型

    model_config = {
        "env_file": _ENV_FILE,
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "hide_input_in_errors": True,
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
