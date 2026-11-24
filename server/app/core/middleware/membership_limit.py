"""
会员权限控制中间件

功能按会员等级控制接口访问，提供:
- require_feature(feature_name): 检查当前用户的会员等级能否访问指定功能
- 每次调用自动递增月度使用计数
"""
from datetime import datetime, date
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.utils.redis_client import get_redis, RedisCache

# ========== 会员等级定义 ==========

MEMBERSHIP_LEVELS = {
    "free": 0,
    "vip_student": 1,
    "vip_personal": 1,
    "vip_teacher": 2,
    "vip_teacher_pro": 3,
}

# ========== 功能权限矩阵 ==========
# 各功能允许的最低会员等级

FEATURE_LIMITS = {
    # 训练类
    "word_training": "free",           # 单词训练 - 免费用户限次
    "scenario_video": "vip_student",   # 情景记忆视频
    "textbook_reading": "free",        # 教材点读 - 免费用户 3 页/天
    "ai_video": "vip_student",         # AI 视频演绎

    # 教师类
    "create_class": "vip_teacher",     # 创建班级
    "ai_ppt": "vip_teacher",           # AI 备课 PPT
    "ai_exam": "vip_teacher",          # AI 出卷
    "ai_grade": "vip_teacher",         # AI 批卷

    # 通用
    "no_ads": "vip_student",           # 去广告
}

# ========== 月度使用次数限制 ==========

MONTHLY_LIMITS: dict[str, dict[str, int]] = {
    "scenario_video": {
        "free": 0,
        "vip_student": 5,
        "vip_personal": 5,
        "vip_teacher": 10,
        "vip_teacher_pro": 999999,
    },
    "ai_video": {
        "free": 2,
        "vip_student": 20,
        "vip_personal": 20,
        "vip_teacher": 50,
        "vip_teacher_pro": 999999,
    },
    "textbook_reading": {
        "free": 999999,
        "vip_student": 999999,
        "vip_personal": 999999,
        "vip_teacher": 999999,
        "vip_teacher_pro": 999999,
    },
    "word_training": {
        "free": 30,
        "vip_student": 999999,
        "vip_personal": 999999,
        "vip_teacher": 999999,
        "vip_teacher_pro": 999999,
    },
    "ai_ppt": {
        "free": 0,
        "vip_student": 0,
        "vip_personal": 0,
        "vip_teacher": 30,
        "vip_teacher_pro": 999999,
    },
    "ai_exam": {
        "free": 0,
        "vip_student": 0,
        "vip_personal": 0,
        "vip_teacher": 20,
        "vip_teacher_pro": 999999,
    },
    "create_class": {
        "free": 0,
        "vip_student": 0,
        "vip_personal": 0,
        "vip_teacher": 5,
        "vip_teacher_pro": 999999,
    },
}


# ========== 工具函数 ==========

def get_membership_level(membership: str) -> int:
    """获取会员等级数值"""
    return MEMBERSHIP_LEVELS.get(membership, 0)


async def check_feature_access(user: User, feature: str, db: AsyncSession) -> None:
    """
    检查用户能否访问指定功能:
    1. 会员等级是否满足要求
    2. 月度使用次数是否超限
    3. 过期会员自动降级
    """
    # 1. 检查会员是否过期
    user = await _refresh_expired_membership(user, db)

    # 2. 检查功能等级要求
    required_level_name = FEATURE_LIMITS.get(feature)
    if required_level_name:
        required_level = get_membership_level(required_level_name)
        user_level = get_membership_level(user.membership)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "membership_required",
                    "message": f"当前会员等级不足，需 {_plan_name(required_level_name)} 及以上才能使用此功能",
                    "required_plan": required_level_name,
                    "feature": feature,
                },
            )

    # 3. 检查月度次数限制（先检查，后递增，避免多计）
    monthly_limit = MONTHLY_LIMITS.get(feature, {}).get(user.membership)
    if monthly_limit is not None and monthly_limit < 999999:
        redis = await get_redis()
        cache = RedisCache(redis)
        today = date.today()
        month_key = f"usage:{feature}:{user.id}:{today.year}{today.month:02d}"
        current_str = await cache.get(month_key)
        current_usage = int(current_str) if current_str else 0
        if current_usage >= monthly_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "monthly_limit_exceeded",
                    "message": f"本月 {_feature_name(feature)} 次数已达上限 ({monthly_limit} 次)，请升级会员",
                    "limit": monthly_limit,
                    "feature": feature,
                },
            )
        # 通过检查后再递增
        await cache.incr_with_ttl(month_key, ttl=32 * 86400)


async def _refresh_expired_membership(user: User, db: AsyncSession) -> User:
    """检查会员是否过期，过期则自动降级为 free"""
    if user.membership != "free" and user.membership_expire:
        if user.membership_expire < datetime.now():
            user.membership = "free"
            user.membership_expire = None
            db.add(user)
            await db.commit()
    return user


def _plan_name(plan: str) -> str:
    """获取套餐中文名"""
    names = {
        "free": "免费版",
        "vip_student": "VIP学生",
        "vip_personal": "VIP个人",
        "vip_teacher": "VIP教师",
        "vip_teacher_pro": "高级教师",
    }
    return names.get(plan, plan)


def _feature_name(feature: str) -> str:
    """获取功能中文名"""
    names = {
        "word_training": "单词训练",
        "scenario_video": "情景记忆视频",
        "textbook_reading": "教材点读",
        "ai_video": "AI视频演绎",
        "create_class": "创建班级",
        "ai_ppt": "AI备课PPT",
        "ai_exam": "AI出卷",
        "ai_grade": "AI批卷",
        "no_ads": "去广告",
    }
    return names.get(feature, feature)


# ========== FastAPI 依赖 ==========

def require_feature(feature: str):
    """
    FastAPI 依赖工厂：在路由上添加会员功能权限检查

    用法:
    @router.post("/exam/generate")
    async def generate_exam(
        ...,
        _=Depends(require_feature("ai_exam")),
    ):
    """
    async def _dependency(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        await check_feature_access(user, feature, db)
        return user

    return _dependency
