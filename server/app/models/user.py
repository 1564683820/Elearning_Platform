"""
用户模块 Model — 对齐 DBplan 2.1

表清单:
  user          用户表
  user_api_key  用户 API Key 表（DBplan 扩展：支持多 Key）
  user_reminder 用户提醒设置表
"""
from sqlalchemy import (
    Column, BigInteger, SmallInteger, String, DateTime,
    func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


class User(Base):
    """用户表"""
    __tablename__ = "user"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    openid = Column(String(64), unique=True, nullable=False, comment="微信 openid")
    union_id = Column(String(64), default=None, comment="微信 unionid")
    account = Column(String(64), unique=True, nullable=False, default="", comment="登录账号(唯一)")
    username = Column(String(64), nullable=True, default=None, comment="用户名(显示用，不唯一)")
    password_hash = Column(String(128), default="", comment="密码哈希")
    nickname = Column(String(64), default="", comment="昵称")
    email = Column(String(128), default="", comment="邮箱")
    avatar_url = Column(String(512), default="", comment="头像 URL(CDN 地址)")
    stage = Column(SmallInteger, nullable=False, default=1, comment="学习阶段: 1=小学,2=初中,3=高中,4=四六级")
    api_key_encrypted = Column(String(256), default=None, comment="AES 加密后的 API Key")
    api_key_iv = Column(String(64), default=None, comment="AES 加密 IV")
    role = Column(String(16), default="student", comment="角色: student/teacher/admin")
    membership = Column(String(32), default="free", comment="会员类型: free/vip/pro")
    membership_expire = Column(DateTime, default=None, comment="会员到期时间")
    api_base_url = Column(String(256), default="https://api.openai.com/v1", comment="Base URL")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "comment": "用户表"},
    )


class UserApiKey(Base):
    """用户 API Key 表 — 支持多 Key 多模型（DBplan 扩展）"""
    __tablename__ = "user_api_keys"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, index=True, comment="用户ID")
    key_type = Column(String(32), nullable=False, comment="llm/multimodal/embedding")
    encrypted_key = Column(String(1024), nullable=False, comment="AES 加密后的 API Key")
    api_base = Column(String(512), default="", comment="自定义 API Base URL")
    model_name = Column(String(128), default="", comment="自定义模型名")
    is_valid = Column(SmallInteger, default=0, comment="是否验证通过 0/1")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "comment": "用户 API Key 表"},
    )


class UserReminder(Base):
    """用户提醒设置表"""
    __tablename__ = "user_reminders"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, unique=True, nullable=False, comment="用户ID")
    weekdays = Column(String(20), default="1,2,3,4,5", comment="周一到周日 1-7")
    remind_time = Column(String(8), default="08:00:00", comment="提醒时间")
    enabled = Column(SmallInteger, default=1, comment="是否启用 0/1")
