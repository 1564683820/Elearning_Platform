"""
会员业务逻辑服务

涵盖: 套餐管理、订单创建、支付回调处理、兑换码系统、
过期检查降级、月度使用计数
"""
import uuid
import secrets
import string
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, or_, and_, func
from app.core.config import get_settings
from app.models.user import User
from app.models.membership_models import UserMembershipOrder, RedeemCode
from app.utils.redis_client import get_redis, RedisCache

settings = get_settings()

# ========== 套餐定义 ==========

PLANS = [
    {
        "id": "vip_student",
        "name": "VIP学生",
        "monthly_price": 19.90,
        "yearly_price": 168.00,
        "description": "训练无限制、点读无限制、视频演绎 20 次/月、去广告",
        "features": ["word_training", "textbook_reading", "ai_video", "no_ads"],
    },
    {
        "id": "vip_teacher",
        "name": "VIP教师",
        "monthly_price": 39.90,
        "yearly_price": 368.00,
        "description": "含学生权益 + 5 个班级 + PPT 30 次/月 + 出卷 20 次/月 + AI批卷",
        "features": ["word_training", "textbook_reading", "ai_video", "no_ads",
                     "create_class", "ai_ppt", "ai_exam", "ai_grade"],
    },
    {
        "id": "vip_teacher_pro",
        "name": "高级教师",
        "monthly_price": 69.90,
        "yearly_price": 668.00,
        "description": "全部无限制 + 班级不限 + 优先技术支持",
        "features": ["word_training", "textbook_reading", "ai_video", "no_ads",
                     "create_class", "ai_ppt", "ai_exam", "ai_grade"],
    },
]


class MembershipService:
    """会员业务逻辑"""

    # ==================== 套餐管理 ====================

    @staticmethod
    def get_plans():
        """获取所有套餐列表"""
        return PLANS

    # ==================== 订单 ====================

    @staticmethod
    async def create_order(
        db: AsyncSession,
        user_id: int,
        plan: str,
        duration_months: int,
        pay_type: str = "wxpay",
    ) -> dict:
        """
        创建会员订单
        pay_type: wxpay(微信支付) / redeem(兑换码)
        """
        # 查找套餐
        plan_info = None
        for p in PLANS:
            if p["id"] == plan:
                plan_info = p
                break
        if not plan_info:
            raise ValueError(f"无效套餐: {plan}")

        # 计算金额
        price = plan_info["monthly_price"]
        if duration_months == 12:
            price = plan_info["yearly_price"] / 12  # 年付优惠
        amount = round(Decimal(str(price)) * duration_months, 2)

        # 生成订单号
        order_no = f"MP{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"

        # 计算到期时间
        expire_at = datetime.now() + timedelta(days=30 * duration_months)

        order = UserMembershipOrder(
            user_id=user_id,
            plan=plan,
            order_no=order_no,
            amount=amount,
            duration_months=duration_months,
            payment_status="pending",
            pay_type=pay_type,
            expire_at=expire_at,
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)

        return {
            "order_id": order.id,
            "order_no": order_no,
            "amount": float(amount),
            "plan": plan,
            "duration_months": duration_months,
            "payment_status": "pending",
            "created_at": order.created_at.isoformat() if order.created_at else "",
        }

    @staticmethod
    async def handle_payment_callback(
        db: AsyncSession,
        order_no: str,
        payment_result: str = "success",
    ) -> dict:
        """
        处理支付回调
        - 微信支付支付成功后会调用此接口
        - 更新订单状态为 paid
        - 更新用户的会员等级和到期时间
        """
        # 查询订单
        result = await db.execute(
            select(UserMembershipOrder).where(
                UserMembershipOrder.order_no == order_no
            ).with_for_update()
        )
        order = result.scalar_one_or_none()
        if not order:
            raise ValueError(f"订单不存在: {order_no}")

        if order.payment_status == "paid":
            return {"status": "already_paid", "order_no": order_no}
        if order.payment_status != "pending" or payment_result != "success":
            raise ValueError("订单状态不允许开通会员")

        # 更新订单状态
        now = datetime.now()
        order.payment_status = "paid"
        order.paid_at = now
        # 更新用户会员等级
        final_expire = await MembershipService._apply_membership_to_user(
            db, order.user_id, order.plan, now + timedelta(days=30 * order.duration_months)
        )
        order.expire_at = final_expire
        # 订单状态和用户权益同一事务提交，失败由 get_db 回滚。
        await db.commit()

        return {
            "status": "success",
            "order_no": order_no,
            "user_id": order.user_id,
            "plan": order.plan,
            "expire_at": order.expire_at.isoformat() if order.expire_at else "",
        }

    @staticmethod
    async def _apply_membership_to_user(
        db: AsyncSession,
        user_id: int,
        plan: str,
        new_expire_at: datetime,
    ) -> datetime:
        """
        为用户应用会员等级（支持续费叠加），由调用者统一提交事务。
        """
        result = await db.execute(select(User).where(User.id == user_id).with_for_update())
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("用户不存在，无法开通会员")

        current_expire = user.membership_expire
        now = datetime.now()

        # 如果已有会员且未过期，则续费叠加时长
        if current_expire and current_expire > now:
            final_expire = current_expire + (new_expire_at - now)
        else:
            final_expire = new_expire_at

        user.membership = plan
        user.membership_expire = final_expire
        db.add(user)
        await db.flush()
        return final_expire

    # ==================== 兑换码 ====================

    @staticmethod
    async def generate_redeem_codes(
        db: AsyncSession,
        admin_id: int,
        plan: str,
        duration_months: int,
        count: int,
        expire_days: Optional[int] = None,
        remark: str = "",
    ) -> list[dict]:
        """
        批量生成兑换码
        count: 生成数量 (1-1000)
        expire_days: 兑换码过期天数 (None=永不过期)
        """
        if count < 1 or count > 1000:
            raise ValueError("生成数量范围为 1-1000")
        if plan not in ["vip_student", "vip_teacher", "vip_teacher_pro"]:
            raise ValueError(f"无效套餐: {plan}")

        batch_no = f"BATCH{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
        expire_at = None
        if expire_days:
            expire_at = datetime.now() + timedelta(days=expire_days)

        codes = []
        for _ in range(count):
            # 生成唯一兑换码
            code = _generate_unique_code()
            codes.append(RedeemCode(
                code=code,
                plan=plan,
                duration_months=duration_months,
                status="active",
                created_by=admin_id,
                batch_no=batch_no,
                expire_at=expire_at,
                remark=remark,
            ))

        db.add_all(codes)
        await db.commit()

        return [
            {
                "code": c.code,
                "plan": c.plan,
                "duration_months": c.duration_months,
            }
            for c in codes
        ]

    @staticmethod
    async def redeem_code(
        db: AsyncSession,
        user_id: int,
        code_str: str,
    ) -> dict:
        """
        用户使用兑换码
        返回兑换结果
        """
        # 查询兑换码
        result = await db.execute(
            select(RedeemCode).where(RedeemCode.code == code_str.strip()).with_for_update()
        )
        code_record = result.scalar_one_or_none()

        if not code_record:
            raise ValueError("无效的兑换码")

        if code_record.status == "used":
            raise ValueError("兑换码已被使用")
        if code_record.status == "expired":
            raise ValueError("兑换码已过期")
        if code_record.status == "disabled":
            raise ValueError("兑换码已停用")
        if code_record.status != "active":
            raise ValueError("兑换码状态不可兑换")

        # 检查兑换码是否过期
        if code_record.expire_at and code_record.expire_at < datetime.now():
            code_record.status = "expired"
            await db.commit()
            raise ValueError("兑换码已过期")

        # 标记兑换码已使用
        code_record.status = "used"
        code_record.used_by = user_id
        code_record.used_at = datetime.now()

        # 计算到期时间
        expire_at = datetime.now() + timedelta(days=30 * code_record.duration_months)
        # 为用户开通会员
        final_expire = await MembershipService._apply_membership_to_user(
            db, user_id, code_record.plan, expire_at
        )
        await db.commit()

        return {
            "status": "success",
            "plan": code_record.plan,
            "duration_months": code_record.duration_months,
            "expire_at": final_expire.isoformat(),
        }

    @staticmethod
    async def list_redeem_codes(
        db: AsyncSession,
        admin_id: int,
        status_filter: Optional[str] = None,
        batch_no: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """查询兑换码列表（管理员）"""
        query = select(RedeemCode).where(RedeemCode.created_by == admin_id)

        if status_filter:
            query = query.where(RedeemCode.status == status_filter)
        if batch_no:
            query = query.where(RedeemCode.batch_no == batch_no)

        # 总数
        count_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0

        # 分页
        query = query.order_by(RedeemCode.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        records = result.scalars().all()

        return {
            "items": [
                {
                    "id": r.id,
                    "code": r.code,
                    "plan": r.plan,
                    "duration_months": r.duration_months,
                    "status": r.status,
                    "batch_no": r.batch_no,
                    "used_by": r.used_by,
                    "used_at": r.used_at.isoformat() if r.used_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in records
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ==================== 用户会员信息 ====================

    @staticmethod
    async def get_user_membership_info(
        db: AsyncSession,
        user_id: int,
    ) -> dict:
        """获取用户当前会员信息"""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("用户不存在")

        # 获取订单历史
        orders_result = await db.execute(
            select(UserMembershipOrder)
            .where(UserMembershipOrder.user_id == user_id)
            .order_by(UserMembershipOrder.created_at.desc())
            .limit(10)
        )
        orders = orders_result.scalars().all()

        return {
            "user_id": user.id,
            "nickname": user.nickname,
            "role": user.role,
            "membership": user.membership,
            "membership_level": _get_level_number(user.membership),
            "membership_name": _plan_name(user.membership),
            "membership_expire": user.membership_expire.isoformat() if user.membership_expire else None,
            "is_expired": _is_membership_expired(user),
            "orders": [
                {
                    "id": o.id,
                    "plan": o.plan,
                    "amount": float(o.amount),
                    "payment_status": o.payment_status,
                    "pay_type": o.pay_type,
                    "paid_at": o.paid_at.isoformat() if o.paid_at else None,
                    "created_at": o.created_at.isoformat() if o.created_at else "",
                }
                for o in orders
            ],
        }

    # ==================== 月度使用计数 ====================

    @staticmethod
    async def get_monthly_usage(
        user_id: int,
        feature: str,
    ) -> dict:
        """获取用户某功能本月已使用次数"""
        redis = await get_redis()
        cache = RedisCache(redis)
        now = datetime.now()
        month_key = f"usage:{feature}:{user_id}:{now.year}{now.month:02d}"
        count = await cache.get(month_key)
        return {
            "feature": feature,
            "usage": int(count) if count else 0,
            "year_month": f"{now.year}{now.month:02d}",
        }

    # ==================== 过期检查 ====================

    @staticmethod
    async def check_expired_memberships(
        db: AsyncSession,
        dry_run: bool = False,
    ) -> dict:
        """
        检查所有过期会员并自动降级
        返回处理统计
        """
        now = datetime.now()
        three_days_later = now + timedelta(days=3)

        # 查询已过期的会员
        result = await db.execute(
            select(User).where(
                and_(
                    User.membership != "free",
                    User.membership_expire.isnot(None),
                    User.membership_expire < now,
                )
            )
        )
        expired_users = result.scalars().all()

        # 查询即将到期的会员（3天内）
        expiring_result = await db.execute(
            select(User).where(
                and_(
                    User.membership != "free",
                    User.membership_expire.isnot(None),
                    User.membership_expire > now,
                    User.membership_expire < three_days_later,
                )
            )
        )
        expiring_users = expiring_result.scalars().all()

        downgraded = 0
        if not dry_run:
            for user in expired_users:
                user.membership = "free"
                user.membership_expire = None
                db.add(user)
            await db.commit()
            downgraded = len(expired_users)

        return {
            "expired_count": len(expired_users),
            "downgraded_count": downgraded,
            "expiring_in_3_days": len(expiring_users),
            "dry_run": dry_run,
        }


# ========== 辅助函数 ==========

def _generate_unique_code() -> str:
    """生成唯一兑换码: 大写字母+数字 16 位"""
    chars = string.ascii_uppercase + string.digits
    # 分组格式: XXXX-XXXX-XXXX-XXXX
    raw = "".join(secrets.choice(chars) for _ in range(16))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def _get_level_number(membership: str) -> int:
    """获取会员等级数值"""
    levels = {
        "free": 0,
        "vip_student": 1,
        "vip_personal": 1,
        "vip_teacher": 2,
        "vip_teacher_pro": 3,
    }
    return levels.get(membership, 0)


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


def _is_membership_expired(user: User) -> bool:
    """检查会员是否已过期"""
    if user.membership == "free":
        return False
    if not user.membership_expire:
        return False
    return user.membership_expire < datetime.now()
