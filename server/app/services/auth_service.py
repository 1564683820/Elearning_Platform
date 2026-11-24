from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.user import User, UserApiKey
from app.models.invite_code import InviteCode
from app.schemas.common import (
    UserOut, UserUpdate, ApiKeyCreate, ApiKeyOut,
    InviteCodeRegisterRequest, LoginRequest,
)
from app.core.security import create_token, encrypt_text, decrypt_text, hash_password, verify_password
from app.utils.wechat import code2session
from app.core.config import get_settings
import httpx, logging

settings = get_settings()
logger = logging.getLogger(__name__)


class AuthService:

    @staticmethod
    async def invite_code_register(db: AsyncSession, body: InviteCodeRegisterRequest) -> dict:
        """邀请码注册：验证邀请码 → 创建用户 → 返回 JWT"""
        # 统一转为大写，避免用户输入小写导致匹配失败
        raw_code = body.invite_code.upper().strip() if body.invite_code else ""

        # 1. 查找并验证邀请码（按 code + is_used=0 + is_deleted=0）
        result = await db.execute(
            select(InviteCode).where(
                InviteCode.code == raw_code,
                InviteCode.is_used == 0,
                InviteCode.is_deleted == 0,
            )
        )
        invite = result.scalar_one_or_none()
        if not invite:
            raise ValueError("邀请码无效或已被使用")

        # 1b. 校验邀请码角色是否匹配
        if invite.role != body.role:
            role_label = "学生" if body.role == "student" else "教师"
            expected_label = "学生" if invite.role == "student" else "教师"
            raise ValueError(f"该邀请码仅限{expected_label}注册，不能用于{role_label}注册")

        # 2. 检查账号是否已存在
        result = await db.execute(
            select(User).where(User.account == body.account)
        )
        if result.scalar_one_or_none():
            raise ValueError("账号已被注册")

        display_name = body.username or body.account
        fake_openid = f"invite_{body.account}"
        result = await db.execute(
            select(User).where(User.openid == fake_openid)
        )
        if result.scalar_one_or_none():
            raise ValueError("该用户已存在")

        # 3. 创建用户（使用邀请码指定的角色，兼容 body.role 填写错误的情况）
        actual_role = invite.role
        user = User(
            openid=fake_openid,
            account=body.account,
            username=display_name,
            password_hash=hash_password(body.password),
            nickname=display_name,
            role=actual_role,
        )
        db.add(user)
        await db.flush()

        # 4. 标记邀请码已使用
        invite.is_used = 1
        invite.used_by = user.id
        invite.used_at = func.now()

        await db.refresh(user)
        logger.info("邀请码注册成功: account=%s, role=%s, user_id=%s, invite_id=%s",
                     body.account, actual_role, user.id, invite.id)
        token = create_token(user.id)
        return {"token": token, "user": UserOut.model_validate(user)}

    @staticmethod
    async def teacher_register(db: AsyncSession, body: InviteCodeRegisterRequest) -> dict:
        """教师注册（向后兼容）"""
        return await AuthService.invite_code_register(db, body)

    @staticmethod
    async def password_login(db: AsyncSession, body: LoginRequest, allowed_roles: list[str] | None = None) -> dict:
        """密码登录（支持角色校验）。

        Args:
            db: 数据库会话
            body: 登录请求（account + password）
            allowed_roles: 允许登录的角色列表。None 表示仅允许学生登录（向后兼容小程序端）；
                           传 ["teacher", "admin"] 则仅允许教师/管理者登录。

        Raises:
            ValueError: 账号密码错误、角色不匹配
        """
        result = await db.execute(
            select(User).where(User.account == body.account)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("账号或密码错误")

        if not user.password_hash:
            raise ValueError("账号或密码错误")

        if not verify_password(body.password, user.password_hash):
            raise ValueError("账号或密码错误")

        # 角色校验：如果指定了允许的角色列表，则校验用户角色
        if allowed_roles is not None:
            if user.role not in allowed_roles:
                role_labels = {"teacher": "教师", "admin": "管理者", "student": "学生"}
                allowed_labels = [role_labels.get(r, r) for r in allowed_roles]
                raise ValueError(f"该账号不是{'/'.join(allowed_labels)}，请使用正确的登录入口")

        logger.info("密码登录成功: account=%s, user_id=%s, role=%s", body.account, user.id, user.role)
        token = create_token(user.id)
        return {"token": token, "user": UserOut.model_validate(user)}

    @staticmethod
    async def teacher_login(db: AsyncSession, body: LoginRequest) -> dict:
        """教师/管理者专属登录：仅允许 role=teacher 或 role=admin 的账号登录"""
        return await AuthService.password_login(db, body, allowed_roles=["teacher", "admin"])

    @staticmethod
    async def admin_login(db: AsyncSession, body: LoginRequest) -> dict:
        """管理者专属登录：仅允许 role=admin 的账号登录"""
        return await AuthService.password_login(db, body, allowed_roles=["admin"])

    @staticmethod
    async def login(db: AsyncSession, code: str) -> dict:
        """微信登录：code → openid → 查找/创建用户 → 返回 JWT"""
        wx_data = await code2session(code)
        openid = wx_data.get("openid")
        if not openid:
            raise ValueError(f"微信登录失败: {wx_data.get('errmsg', '未知错误')}")

        # 查找用户
        result = await db.execute(select(User).where(User.openid == openid))
        user = result.scalar_one_or_none()

        # 不存在则创建
        if user is None:
            user = User(openid=openid, union_id=wx_data.get("unionid", ""))
            db.add(user)
            await db.flush()
            await db.refresh(user)

        token = create_token(user.id)
        return {"token": token, "user": UserOut.model_validate(user)}

    @staticmethod
    async def get_profile(db: AsyncSession, user_id: int) -> UserOut:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("用户不存在")
        return UserOut.model_validate(user)

    @staticmethod
    async def change_password(
        db: AsyncSession, user_id: int,
        old_password: str, new_password: str,
    ) -> None:
        """自助修改密码：验证旧密码 → 设置新密码"""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("用户不存在")
        if not user.password_hash:
            raise ValueError("该账号未设置密码，无法修改")
        if not verify_password(old_password, user.password_hash):
            raise ValueError("旧密码错误")
        user.password_hash = hash_password(new_password)
        await db.flush()

    @staticmethod
    async def update_profile(db: AsyncSession, user_id: int, data: UserUpdate) -> UserOut:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("用户不存在")
        update_data = data.model_dump(exclude_unset=True)
        # 防御性移除 role 字段：禁止通过普通 profile 更新接口修改角色
        update_data.pop("role", None)
        for k, v in update_data.items():
            setattr(user, k, v)
        await db.flush()
        await db.refresh(user)
        return UserOut.model_validate(user)


class ApiKeyService:

    @staticmethod
    async def list_keys(db: AsyncSession, user_id: int) -> list[ApiKeyOut]:
        result = await db.execute(
            select(UserApiKey).where(UserApiKey.user_id == user_id)
        )
        return [ApiKeyOut.model_validate(k) for k in result.scalars().all()]

    @staticmethod
    async def save_key(db: AsyncSession, user_id: int, data: ApiKeyCreate) -> ApiKeyOut:
        """保存或更新 API Key（加密存储）"""
        result = await db.execute(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.key_type == data.key_type,
            )
        )
        existing = result.scalar_one_or_none()

        encrypted = encrypt_text(data.encrypted_key)

        if existing:
            existing.encrypted_key = encrypted
            existing.api_base = data.api_base
            existing.model_name = data.model_name
            existing.is_valid = 0
            await db.flush()
            await db.refresh(existing)
            return ApiKeyOut.model_validate(existing)
        else:
            key = UserApiKey(
                user_id=user_id,
                key_type=data.key_type,
                encrypted_key=encrypted,
                api_base=data.api_base,
                model_name=data.model_name,
                is_valid=0,
            )
            db.add(key)
            await db.flush()
            await db.refresh(key)
            return ApiKeyOut.model_validate(key)

    @staticmethod
    async def test_key(db: AsyncSession, user_id: int, key_type: str) -> dict:
        """测试 API Key 连通性"""
        result = await db.execute(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.key_type == key_type,
            )
        )
        key_record = result.scalar_one_or_none()
        if not key_record:
            raise ValueError("未找到该类型的 API Key")

        api_key = decrypt_text(key_record.encrypted_key)
        api_base = key_record.api_base or settings.LLM_API_BASE

        # 调用模型列表接口验证
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{api_base}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    key_record.is_valid = 1
                    await db.flush()
                    return {"success": True, "message": "连接成功"}
                else:
                    key_record.is_valid = 0
                    await db.flush()
                    return {"success": False, "message": f"API 返回 {resp.status_code}"}
        except Exception as e:
            key_record.is_valid = 0
            await db.flush()
            return {"success": False, "message": str(e)}

    @staticmethod
    async def get_decrypted_key(db: AsyncSession, user_id: int, key_type: str) -> tuple[str, str] | None:
        """获取用户解密后的 API Key 和 api_base，用于调用 AI 服务"""
        result = await db.execute(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.key_type == key_type,
                UserApiKey.is_valid == 1,
            )
        )
        key_record = result.scalar_one_or_none()
        if not key_record:
            return None
        return decrypt_text(key_record.encrypted_key), key_record.api_base
