from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.api.deps import get_current_user, get_current_user_id, get_current_admin
from app.models.user import User
from app.models.class_models import Class, ClassStudent
from app.services.auth_service import AuthService, ApiKeyService
from sqlalchemy import select, func
from app.models.quiz import UserQuizLog
from app.models.word import UserWordProgress
from app.schemas.common import (
    ResponseData, LoginRequest, LoginResponse, UserOut, UserUpdate, ProfileOut,
    PasswordChangeRequest,
    ApiKeyCreate, ApiKeyOut, ApiKeyTestRequest,
    InviteCodeRegisterRequest, AdminUserUpdate,
)

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=ResponseData[LoginResponse])
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """学生端登录：传 account+password 密码登录（仅限学生角色），或传 code 微信登录"""
    if body.account:
        # 学生端密码登录：仅允许 student 角色
        result = await AuthService.password_login(db, body, allowed_roles=["student"])
    else:
        result = await AuthService.login(db, body.code)
    return ResponseData(data=result)


@router.post("/teacher/login", response_model=ResponseData[LoginResponse])
async def teacher_login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """教师/管理者端登录：仅允许 teacher 或 admin 角色登录"""
    if not body.account:
        raise HTTPException(status_code=400, detail="教师端仅支持账号密码登录")
    result = await AuthService.teacher_login(db, body)
    return ResponseData(data=result)


@router.post("/admin/login", response_model=ResponseData[LoginResponse])
async def admin_login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """管理者端登录：仅允许 admin 角色登录"""
    if not body.account:
        raise HTTPException(status_code=400, detail="管理者端仅支持账号密码登录")
    result = await AuthService.admin_login(db, body)
    return ResponseData(data=result)


@router.post("/register", response_model=ResponseData[LoginResponse])
async def register(
    body: InviteCodeRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """邀请码注册（学生/教师通用，需填写邀请码）"""
    result = await AuthService.invite_code_register(db, body)
    return ResponseData(data=result)


@router.get("/profile", response_model=ResponseData[ProfileOut])
async def get_profile(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取当前用户信息（含学习统计和班级信息）"""
    # 阶段映射 — 分为四个阶段：小学/初中/高中/四六级
    PHASE_MAP = {
        1: "小学", 2: "初中",
        3: "高中", 4: "四六级",
    }
    phase = PHASE_MAP.get(user.stage, "四六级")

    # 统计学习天数
    from app.models.stats import UserDailyStat
    stat_result = await db.execute(
        select(func.count()).select_from(UserDailyStat)
        .where(UserDailyStat.user_id == user.id)
    )
    study_days = stat_result.scalar() or 0

    # 统计单词量和训练次数
    word_result = await db.execute(
        select(func.count()).select_from(UserWordProgress)
        .where(UserWordProgress.user_id == user.id)
    )
    total_words = word_result.scalar() or 0

    quiz_result = await db.execute(
        select(func.count()).select_from(UserQuizLog)
        .where(UserQuizLog.user_id == user.id)
    )
    total_training = quiz_result.scalar() or 0

    # 学生角色：获取所属班级
    classes = []
    if user.role in ("student", "personal"):
        cls_result = await db.execute(
            select(Class, ClassStudent.joined_at)
            .join(ClassStudent, ClassStudent.class_id == Class.id)
            .where(ClassStudent.student_id == user.id, Class.is_active == 1)
            .order_by(ClassStudent.joined_at.desc())
        )
        for cls, joined_at in cls_result.all():
            classes.append({
                "id": cls.id,
                "name": cls.name,
                "joined_at": joined_at.isoformat() if joined_at else "",
                "student_count": cls.student_count or 0,
            })

    return ResponseData(data=ProfileOut(
        id=user.id,
        name=user.nickname or "",
        nickname=user.nickname or "",
        email=user.email or "",
        avatar_url=user.avatar_url or "",
        role=user.role or "",
        phase=phase,
        stage=user.stage,
        studyDays=study_days,
        totalWords=total_words,
        totalTraining=total_training,
        membership=user.membership or "free",
        classes=classes,
    ))


@router.put("/profile", response_model=ResponseData[UserOut])
async def update_profile(
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """更新用户信息"""
    result = await AuthService.update_profile(db, user_id, body)
    return ResponseData(data=result)


@router.put("/password", response_model=ResponseData)
async def change_password(
    body: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """修改密码（需验证旧密码）"""
    try:
        await AuthService.change_password(db, user_id, body.old_password, body.new_password)
        return ResponseData(message="密码已更新")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===== API Key 管理 =====

apikey_router = APIRouter(prefix="/apikeys", tags=["API Key"])


@apikey_router.get("/", response_model=ResponseData[list[ApiKeyOut]])
async def list_apikeys(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取用户 API Key 列表"""
    result = await ApiKeyService.list_keys(db, user_id)
    return ResponseData(data=result)


@apikey_router.post("/", response_model=ResponseData[ApiKeyOut])
async def save_apikey(
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """保存/更新 API Key"""
    result = await ApiKeyService.save_key(db, user_id, body)
    return ResponseData(data=result)


@apikey_router.post("/test", response_model=ResponseData[dict])
async def test_apikey(
    body: ApiKeyTestRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """测试 API Key 连通性"""
    result = await ApiKeyService.test_key(db, user_id, body.key_type)
    return ResponseData(data=result)
