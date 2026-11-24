"""管理者端 API — 账号管理 / 费用统计 / API Key 管理 / 浏览统计"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.db.database import get_db
from app.api.deps import get_current_admin
from app.models.user import User, UserApiKey
from app.models.membership_models import UserMembershipOrder
from app.models.stats import UserDailyStat, LearningBehaviorLog
from app.models.invite_code import InviteCode
from app.models.class_models import Class, ClassTeacher, ClassStudent
from app.services.teacher_service import TeacherService
from app.schemas.common import ResponseData
from app.core.security import hash_password
from datetime import datetime, date, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)
import secrets
import string

router = APIRouter(prefix="/admin", tags=["管理者端"])


# ──────────────────────────────────────────────
# 账号管理
# ──────────────────────────────────────────────

@router.get("/users", response_model=ResponseData)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[str] = Query(None, description="筛选角色: student/teacher/admin"),
    search: Optional[str] = Query(None, description="搜索用户名或昵称"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """获取用户列表（分页 + 筛选）"""
    conditions = []
    if role:
        conditions.append(User.role == role)
    if search:
        conditions.append(
            User.username.like(f"%{search}%") | User.nickname.like(f"%{search}%")
        )

    # 总数
    count_q = select(func.count()).select_from(User)
    if conditions:
        count_q = count_q.where(and_(*conditions))
    total = (await db.execute(count_q)).scalar() or 0

    # 列表
    q = select(User).order_by(User.created_at.desc())
    if conditions:
        q = q.where(and_(*conditions))
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    items = []
    for u in rows:
        items.append({
            "id": u.id,
            "openid": u.openid,
            "account": u.account or "",
            "username": u.username or "",
            "nickname": u.nickname or "",
            "role": u.role or "student",
            "membership": u.membership or "free",
            "stage": u.stage,
            "email": u.email or "",
            "created_at": u.created_at.isoformat() if u.created_at else "",
            "membership_expire": u.membership_expire.isoformat() if u.membership_expire else "",
        })

    return ResponseData(data={
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    })


@router.post("/users", response_model=ResponseData)
async def create_user(
    body: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """创建新账号（学生/教师）"""
    account = body.get("account", "").strip()
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    role = body.get("role", "student")
    nickname = body.get("nickname", username or account)

    if not account and not username:
        raise ValueError("账号或用户名不能为空")
    if not password:
        raise ValueError("密码不能为空")
    if role not in ("student", "teacher", "admin"):
        raise ValueError("无效的角色")

    # 如果没传 account，用 username 作为 account（向后兼容）
    if not account:
        account = username

    # 检查账号是否已存在
    result = await db.execute(select(User).where(User.account == account))
    if result.scalar_one_or_none():
        raise ValueError("账号已被占用")

    fake_openid = f"{role}_{account}"
    result = await db.execute(select(User).where(User.openid == fake_openid))
    if result.scalar_one_or_none():
        raise ValueError("该用户已存在")

    user = User(
        openid=fake_openid,
        account=account,
        username=username or account,
        password_hash=hash_password(password),
        nickname=nickname,
        role=role,
        stage=body.get("stage", 1),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return ResponseData(data={
        "id": user.id,
        "account": user.account,
        "username": user.username,
        "nickname": user.nickname,
        "role": user.role,
    })


@router.delete("/users/batch", response_model=ResponseData)
async def batch_delete_users(
    body: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """批量删除用户（按 ID 列表）"""
    user_ids = body.get("user_ids", [])
    if not user_ids or not isinstance(user_ids, list):
        raise ValueError("请提供要删除的用户 ID 列表")

    # 防止管理者删自己
    if admin.id in user_ids:
        raise ValueError("不能删除当前登录的管理者账号")

    # 查询要删除的用户
    result = await db.execute(select(User).where(User.id.in_(user_ids)))
    users = result.scalars().all()
    if not users:
        raise ValueError("未找到要删除的用户")

    deleted_count = len(users)
    for u in users:
        await db.delete(u)

    await db.flush()
    return ResponseData(data={
        "deleted_count": deleted_count,
        "message": f"成功删除 {deleted_count} 个用户",
    })


@router.put("/users/{user_id}", response_model=ResponseData)
async def update_user(
    user_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """更新用户信息（昵称/角色/阶段/密码等）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("用户不存在")

    # 可更新字段
    updatable = ["nickname", "role", "stage", "membership", "email"]
    for field in updatable:
        if field in body:
            setattr(user, field, body[field])

    # 可选更新密码
    new_pwd = body.get("password", "").strip()
    if new_pwd:
        user.password_hash = hash_password(new_pwd)

    await db.flush()
    return ResponseData(data={"message": "更新成功"})


# ──────────────────────────────────────────────
# 费用管理
# ──────────────────────────────────────────────

@router.get("/statistics/fees", response_model=ResponseData)
async def fee_statistics(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """费用统计总览"""
    today = date.today()
    if not start_date:
        start_date = (today - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = today.isoformat()

    # 会员订单统计
    q = select(UserMembershipOrder).where(
        UserMembershipOrder.created_at >= start_date,
        UserMembershipOrder.created_at <= end_date + " 23:59:59",
        UserMembershipOrder.status == "paid",
    )
    orders = (await db.execute(q)).scalars().all()

    total_revenue = sum((o.amount or 0) for o in orders)
    order_count = len(orders)

    # 按套餐类型统计
    plan_stats = {}
    for o in orders:
        plan = o.plan_id or "unknown"
        if plan not in plan_stats:
            plan_stats[plan] = {"count": 0, "amount": 0}
        plan_stats[plan]["count"] += 1
        plan_stats[plan]["amount"] += o.amount or 0

    # 会员分布
    vip_count = (await db.execute(
        select(func.count()).select_from(User).where(User.membership.in_(["vip", "pro"]))
    )).scalar() or 0
    free_count = (await db.execute(
        select(func.count()).select_from(User).where(User.membership == "free")
    )).scalar() or 0

    return ResponseData(data={
        "total_revenue": total_revenue,
        "order_count": order_count,
        "period": {"start": start_date, "end": end_date},
        "by_plan": plan_stats,
        "membership_distribution": {
            "vip_total": vip_count,
            "free_total": free_count,
        },
    })


@router.get("/statistics/fees/detail", response_model=ResponseData)
async def fee_detail(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """费用明细：所有付费订单"""
    count_q = select(func.count()).select_from(UserMembershipOrder)
    total = (await db.execute(count_q)).scalar() or 0

    q = (select(UserMembershipOrder)
         .order_by(UserMembershipOrder.created_at.desc())
         .offset((page - 1) * page_size).limit(page_size))
    orders = (await db.execute(q)).scalars().all()

    # 关联用户信息
    user_ids = [o.user_id for o in orders]
    if user_ids:
        users_map_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        users_map = {u.id: u for u in users_map_result.scalars().all()}
    else:
        users_map = {}

    items = []
    for o in orders:
        u = users_map.get(o.user_id)
        items.append({
            "id": o.id,
            "user_id": o.user_id,
            "username": u.username if u else "",
            "nickname": u.nickname if u else "",
            "plan_id": o.plan_id,
            "amount": o.amount or 0,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else "",
        })

    return ResponseData(data={
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    })


# ──────────────────────────────────────────────
# API Key 管理
# ──────────────────────────────────────────────

@router.get("/apikeys", response_model=ResponseData)
async def list_all_apikeys(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """查看所有用户的 API Key 配置情况"""
    count_q = select(func.count()).select_from(UserApiKey)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(UserApiKey)
        .order_by(UserApiKey.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    keys = (await db.execute(q)).scalars().all()

    # 关联用户
    user_ids = list(set(k.user_id for k in keys))
    if user_ids:
        users_map_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        users_map = {u.id: u for u in users_map_result.scalars().all()}
    else:
        users_map = {}

    # 汇总：每个用户的 Key 配置情况
    user_key_stats = {}
    for k in keys:
        uid = k.user_id
        if uid not in user_key_stats:
            u = users_map.get(uid)
            user_key_stats[uid] = {
                "user_id": uid,
                "username": u.username if u else "",
                "nickname": u.nickname if u else "",
                "keys": {},
            }
        user_key_stats[uid]["keys"][k.key_type] = {
            "id": k.id,
            "api_base": k.api_base or "",
            "model_name": k.model_name or "",
            "is_valid": bool(k.is_valid),
        }

    return ResponseData(data={
        "items": list(user_key_stats.values()),
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    })


# ──────────────────────────────────────────────
# 浏览统计
# ──────────────────────────────────────────────

@router.get("/statistics/usage", response_model=ResponseData)
async def usage_statistics(
    days: int = Query(7, ge=1, le=365, description="统计近 N 天"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """浏览/使用统计 — 小程序端 + 教师端"""
    since_date = (date.today() - timedelta(days=days - 1))

    # 1. 各角色用户总数
    role_counts = {}
    for role_name in ("student", "teacher", "admin"):
        cnt = (await db.execute(
            select(func.count()).select_from(User).where(User.role == role_name)
        )).scalar() or 0
        role_counts[role_name] = cnt

    # 2. 小程序用户：角色为 student 且有学习日志的用户数
    student_ids_q = select(User.id).where(User.role == "student")
    student_ids = (await db.execute(student_ids_q)).scalars().all()

    # 近 N 天活跃学生
    active_students_q = (
        select(func.count(func.distinct(LearningBehaviorLog.user_id)))
        .where(
            LearningBehaviorLog.user_id.in_(student_ids),
            LearningBehaviorLog.created_at >= since_date,
        )
    )
    active_students = (await db.execute(active_students_q)).scalar() or 0

    # 近 N 天学生学习总时长（分钟）
    duration_q = (
        select(func.sum(LearningBehaviorLog.session_duration))
        .where(
            LearningBehaviorLog.user_id.in_(student_ids),
            LearningBehaviorLog.created_at >= since_date,
        )
    )
    total_duration_sec = (await db.execute(duration_q)).scalar() or 0

    # 3. 教师端活跃用户
    teacher_ids_q = select(User.id).where(User.role.in_(["teacher", "admin"]))
    teacher_ids = (await db.execute(teacher_ids_q)).scalars().all()

    # 教师端：通过最近登录统计（用 User.updated_at 近似）
    active_teachers = 0
    if teacher_ids:
        active_t = await db.execute(
            select(func.count()).select_from(User).where(
                User.id.in_(teacher_ids),
                User.updated_at >= since_date,
            )
        )
        active_teachers = active_t.scalar() or 0

    # 4. 每日趋势（近 N 天）
    daily_trend = []
    for i in range(days):
        d = since_date + timedelta(days=i)
        d_next = d + timedelta(days=1)

        # 该日学习人数
        student_logs = await db.execute(
            select(func.count(func.distinct(LearningBehaviorLog.user_id)))
            .where(
                LearningBehaviorLog.user_id.in_(student_ids),
                LearningBehaviorLog.created_at >= d,
                LearningBehaviorLog.created_at < d_next,
            )
        )
        active_count = student_logs.scalar() or 0

        # 该日学习总时长
        daily_duration = await db.execute(
            select(func.sum(LearningBehaviorLog.session_duration))
            .where(
                LearningBehaviorLog.user_id.in_(student_ids),
                LearningBehaviorLog.created_at >= d,
                LearningBehaviorLog.created_at < d_next,
            )
        )
        dur_min = (daily_duration.scalar() or 0) // 60

        daily_trend.append({
            "date": d.isoformat(),
            "active_students": active_count,
            "total_minutes": dur_min,
        })

    return ResponseData(data={
        "total_users": {
            "student": role_counts.get("student", 0),
            "teacher": role_counts.get("teacher", 0),
            "admin": role_counts.get("admin", 0),
        },
        "recent_activity": {
            "active_students_ndays": active_students,
            "active_teachers_ndays": active_teachers,
            "total_study_minutes_ndays": total_duration_sec // 60,
            "period_days": days,
        },
        "daily_trend": daily_trend,
    })


# ──────────────────────────────────────────────
# 邀请码管理
# ──────────────────────────────────────────────


def _generate_invite_code(length: int = 8) -> str:
    """生成随机大写字母数字组合邀请码"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@router.get("/invite-codes", response_model=ResponseData)
async def list_invite_codes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[str] = Query(None, description="筛选角色: student/teacher"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """获取邀请码列表（分页，支持角色筛选，默认不显示已删除的）"""
    conditions = [InviteCode.is_deleted == 0]
    if role and role in ("student", "teacher"):
        conditions.append(InviteCode.role == role)

    count_q = select(func.count()).select_from(InviteCode)
    if conditions:
        count_q = count_q.where(and_(*conditions))
    total = (await db.execute(count_q)).scalar() or 0

    q = select(InviteCode)
    if conditions:
        q = q.where(and_(*conditions))
    q = q.order_by(InviteCode.created_at.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    # 关联创建者和使用者的用户名
    user_ids = set()
    for ic in rows:
        user_ids.add(ic.created_by)
        if ic.used_by:
            user_ids.add(ic.used_by)
    users_map = {}
    if user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(list(user_ids)))
        )
        users_map = {u.id: u.username or u.nickname for u in users_result.scalars().all()}

    role_labels = {"student": "学生", "teacher": "教师"}
    items = []
    for ic in rows:
        items.append({
            "id": ic.id,
            "code": ic.code,
            "role": ic.role,
            "role_label": role_labels.get(ic.role, ic.role),
            "is_used": bool(ic.is_used),
            "used_by": ic.used_by,
            "used_by_name": users_map.get(ic.used_by) if ic.used_by else "",
            "used_at": ic.used_at.isoformat() if ic.used_at else "",
            "created_by": ic.created_by,
            "created_by_name": users_map.get(ic.created_by, ""),
            "created_at": ic.created_at.isoformat() if ic.created_at else "",
        })

    return ResponseData(data={
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    })


@router.post("/invite-codes", response_model=ResponseData)
async def create_invite_code(
    body: dict = {},
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """批量生成邀请码，count 指定数量（默认1，最多50），role 指定角色（student/teacher，默认student）"""
    count = max(1, min(body.get("count", 1), 50))
    role = body.get("role", "student")
    if role not in ("student", "teacher"):
        raise ValueError("角色无效，只能为 student 或 teacher")

    codes = []
    for _ in range(count):
        # 生成唯一邀请码（最多重试10次防碰撞）
        for _ in range(10):
            code = _generate_invite_code()
            existing = await db.execute(
                select(InviteCode).where(InviteCode.code == code)
            )
            if not existing.scalar_one_or_none():
                break
        else:
            raise ValueError("生成邀请码失败，请重试")

        invite = InviteCode(
            code=code,
            role=role,
            created_by=admin.id,
        )
        db.add(invite)
        await db.flush()
        await db.refresh(invite)

        role_label = "学生" if role == "student" else "教师"
        codes.append({
            "id": invite.id,
            "code": invite.code,
            "role": invite.role,
            "role_label": role_label,
            "created_at": invite.created_at.isoformat() if invite.created_at else "",
        })

    logger.info("管理员 %s 批量创建 %d 个%s邀请码", admin.username, count, "学生" if role == "student" else "教师")

    if count == 1:
        return ResponseData(data=codes[0])
    return ResponseData(data={"count": count, "codes": codes})


@router.post("/invite-codes/{invite_id}/refresh", response_model=ResponseData)
async def refresh_invite_code(
    invite_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """刷新邀请码（生成新码替换旧码，仅限未使用的）"""
    result = await db.execute(select(InviteCode).where(InviteCode.id == invite_id))
    invite = result.scalar_one_or_none()
    if not invite:
        raise ValueError("邀请码不存在")
    if invite.is_used:
        raise ValueError("已使用的邀请码不能刷新，请生成新的")

    # 重新生成码值
    for _ in range(10):
        new_code = _generate_invite_code()
        existing = await db.execute(
            select(InviteCode).where(InviteCode.code == new_code)
        )
        if not existing.scalar_one_or_none():
            break
    else:
        raise ValueError("刷新邀请码失败，请重试")

    old_code = invite.code
    invite.code = new_code
    await db.flush()

    logger.info("管理员 %s 刷新邀请码: %s -> %s", admin.username, old_code, new_code)

    return ResponseData(data={
        "id": invite.id,
        "code": invite.code,
    })


@router.post("/invite-codes/batch-delete", response_model=ResponseData)
async def batch_delete_invite_codes(
    body: dict = {},
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """批量删除邀请码（软删除，标记 is_deleted=1）"""
    ids = body.get("ids", [])
    if not ids or not isinstance(ids, list):
        raise ValueError("请提供要删除的邀请码ID列表")

    now = datetime.utcnow()
    for invite_id in ids:
        result = await db.execute(select(InviteCode).where(InviteCode.id == invite_id))
        invite = result.scalar_one_or_none()
        if invite:
            invite.is_deleted = 1
            invite.deleted_at = now
            logger.info("管理员 %s 删除邀请码 %s (%s)", admin.username, invite.code, invite_id)

    await db.flush()
    return ResponseData(data={"deleted_count": len(ids)})


# ──────────────────────────────────────────────
# 班级管理
# ──────────────────────────────────────────────


@router.get("/classes", response_model=ResponseData)
async def list_all_classes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    teacher_id: Optional[int] = Query(None, description="按教师ID筛选"),
    search: Optional[str] = Query(None, description="按班级名称搜索"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """获取所有班级列表（分页，支持按教师筛选和名称搜索）"""
    conditions = []

    if teacher_id:
        # 按教师筛选：先查出该教师管理的班级ID
        ct_ids = (await db.execute(
            select(ClassTeacher.class_id).where(ClassTeacher.teacher_id == teacher_id)
        )).scalars().all()
        if not ct_ids:
            return ResponseData(data={
                "items": [], "total": 0,
                "page": page, "page_size": page_size, "total_pages": 0,
            })
        conditions.append(Class.id.in_(ct_ids))

    if search:
        conditions.append(Class.name.like(f"%{search}%"))

    # 总数
    count_q = select(func.count()).select_from(Class)
    if conditions:
        count_q = count_q.where(and_(*conditions))
    total = (await db.execute(count_q)).scalar() or 0

    # 列表
    q = select(Class).order_by(Class.created_at.desc())
    if conditions:
        q = q.where(and_(*conditions))
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    # 获取创建者用户名
    creator_ids = list(set(c.created_by for c in rows))
    creators_map = {}
    if creator_ids:
        cr = await db.execute(select(User).where(User.id.in_(creator_ids)))
        creators_map = {u.id: u.username or u.nickname for u in cr.scalars().all()}

    # 获取每个班级的所有教师
    class_teachers_map = {}
    if rows:
        class_ids = [c.id for c in rows]
        ct_rows = (await db.execute(
            select(ClassTeacher).where(ClassTeacher.class_id.in_(class_ids))
        )).scalars().all()
        teacher_ids = set(ct.teacher_id for ct in ct_rows)
        teacher_map = {}
        if teacher_ids:
            tr = await db.execute(select(User).where(User.id.in_(list(teacher_ids))))
            teacher_map = {u.id: u.username or u.nickname for u in tr.scalars().all()}
        for ct in ct_rows:
            class_teachers_map.setdefault(ct.class_id, []).append(
                {"teacher_id": ct.teacher_id, "teacher_name": teacher_map.get(ct.teacher_id, "")}
            )

    items = []
    for c in rows:
        items.append({
            "id": c.id,
            "name": c.name,
            "description": c.description or "",
            "invite_code": c.invite_code,
            "created_by": c.created_by,
            "created_by_name": creators_map.get(c.created_by, ""),
            "stage": c.stage,
            "student_count": c.student_count,
            "is_active": c.is_active,
            "teachers": class_teachers_map.get(c.id, []),
            "created_at": c.created_at.isoformat() if c.created_at else "",
        })

    return ResponseData(data={
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    })


@router.get("/teachers/{teacher_id}/classes", response_model=ResponseData)
async def list_teacher_classes(
    teacher_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """获取指定教师的所有班级"""
    stmt = (
        select(Class)
        .join(ClassTeacher, ClassTeacher.class_id == Class.id)
        .where(ClassTeacher.teacher_id == teacher_id)
        .order_by(Class.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    items = []
    for c in rows:
        items.append({
            "id": c.id,
            "name": c.name,
            "description": c.description or "",
            "invite_code": c.invite_code,
            "stage": c.stage,
            "student_count": c.student_count,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else "",
        })

    return ResponseData(data=items)


@router.delete("/classes/{class_id}", response_model=ResponseData)
async def admin_delete_class(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """管理者删除班级"""
    try:
        await TeacherService.delete_class(db, class_id, admin.id, is_admin=True)
        return ResponseData(data={"message": "班级已删除"})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
