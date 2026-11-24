from typing import Optional
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.security import decode_token
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)


def _parse_user_id(payload: dict) -> int:
    """JWT subjects must fit the positive signed BIGINT used by User.id."""
    subject = payload.get('sub')
    if (not isinstance(subject, str) or not subject.isascii()
            or not subject.isdecimal() or len(subject) > 19):
        raise ValueError('无效的 Token')
    user_id = int(subject)
    if not 0 < user_id <= 2 ** 63 - 1:
        raise ValueError('无效的 Token')
    return user_id


def _require_user_id(payload: dict) -> int:
    try:
        return _parse_user_id(payload)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='无效的 Token', headers={'WWW-Authenticate': 'Bearer'}) from error


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 JWT Token 解析当前用户"""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='未提供有效的认证凭据', headers={'WWW-Authenticate': 'Bearer'})
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("purpose"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="受限会话 Token 不能访问普通接口",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = _require_user_id(payload)
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    return user


async def get_current_user_id(
    user: User = Depends(get_current_user),
) -> int:
    """仅返回用户ID，轻量级依赖"""
    return user.id


async def get_current_teacher(
    user: User = Depends(get_current_user),
) -> User:
    """验证当前用户是教师或管理员角色"""
    if user.role not in ("teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅教师可执行此操作",
        )
    return user


async def get_current_admin(
    user: User = Depends(get_current_user),
) -> User:
    """验证当前用户是管理者角色，校验 role=admin"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理者可执行此操作",
        )
    return user


from dataclasses import dataclass


@dataclass
class CurrentTeacher:
    """当前教师身份信息"""
    id: int
    is_admin: bool
    account: str = ""


@dataclass
class ExamScanPrincipal:
    """Teacher identity carried by either a normal login token or an exam scan token."""

    teacher_id: int
    token: str
    exam_id: int | None = None
    expires_at: int | None = None
    is_scan_session: bool = False


async def get_current_teacher_id(
    teacher: User = Depends(get_current_teacher),
) -> int:
    """返回当前教师用户的 ID"""
    return teacher.id


async def get_exam_scan_principal(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)),
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ExamScanPrincipal:
    """Authenticate the mobile scan flow without granting a scan token general API access."""
    token_str = credentials.credentials if credentials is not None else token
    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="扫描会话不存在或已失效",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token_str)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="扫描会话已过期，请重新扫描二维码",
            headers={"WWW-Authenticate": "Bearer"},
        )

    purpose = payload.get("purpose")
    if purpose not in (None, "exam_scan"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的扫描会话")

    user_id = _require_user_id(payload)

    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅教师可执行此操作")

    scoped_exam_id = None
    if purpose == "exam_scan":
        try:
            scoped_exam_id = int(payload["exam_id"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="扫描会话缺少试卷范围")

    return ExamScanPrincipal(
        teacher_id=int(user_id),
        token=token_str,
        exam_id=scoped_exam_id,
        expires_at=int(payload["exp"]) if payload.get("exp") is not None else None,
        is_scan_session=purpose == "exam_scan",
    )


async def get_current_teacher_id_download(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)),
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> int:
    """移动端批卷页认证：优先用 Header，fallback 到 Query 参数"""
    token_str = None
    if credentials is not None:
        token_str = credentials.credentials
    elif token:
        token_str = token

    if token_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token_str)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("purpose"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="受限会话 Token 不能访问下载接口",
        )
    user_id = _require_user_id(payload)
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    if user.role not in ("teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅教师可执行此操作",
        )
    return int(user_id)


async def get_current_teacher_info(
    teacher: User = Depends(get_current_teacher),
) -> CurrentTeacher:
    """返回当前教师身份信息（含 admin 标记 + 账号）"""
    return CurrentTeacher(id=teacher.id, is_admin=teacher.role == "admin", account=teacher.account)


async def get_current_user_id_download(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)),
    token: Optional[str] = Query(None),
) -> int:
    """文件下载场景的认证：优先用 Header，fallback 到 Query 参数

    支持 window.open('/documents/123/download?token=xxx') 下载。
    """
    token_str = None
    if credentials is not None:
        token_str = credentials.credentials
    elif token:
        token_str = token

    if token_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token_str)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("purpose"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="受限会话 Token 不能访问下载接口",
        )
    return _require_user_id(payload)


async def get_current_user_id_ws(token: str) -> int:
    """WebSocket 场景下从 JWT Token 解析用户 ID（轻量，不查数据库）

    仅解析 payload 中的 sub(user_id)，不验证用户是否仍存在。
    如果需完整验证，请使用 get_current_user + Depends。
    """
    payload = decode_token(token)
    if payload is None:
        raise ValueError("无效的认证凭据")
    if payload.get("purpose"):
        raise ValueError("受限会话 Token 不能建立 WebSocket 连接")
    return _parse_user_id(payload)
