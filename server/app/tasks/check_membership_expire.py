"""
会员到期检查定时任务

执行: 每天凌晨 0 点
功能:
1. 检查已过期的会员，自动降级为 free
2. 检查 3 天内到期的会员，推送到期提醒
"""
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from app.db.database import get_db
from app.models.user import User
from app.services.membership_service import MembershipService


async def run_membership_expiry_check(dry_run: bool = False) -> dict:
    """
    执行会员过期检查
    可外部调用（定时任务 / 手动触发）

    Args:
        dry_run: True 时仅统计不执行降级

    Returns:
        处理结果统计
    """
    async for db in get_db():
        result = await MembershipService.check_expired_memberships(db, dry_run=dry_run)
        return result


async def check_and_downgrade_expired():
    """
    定时任务入口：检查并降级过期会员
    由 APScheduler/Celery 定时调用（每天 0:00）
    """
    result = await run_membership_expiry_check(dry_run=False)
    print(f"[{datetime.now()}] 会员过期检查完成: {result}")


async def get_expiring_users(threshold_days: int = 3) -> list[dict]:
    """
    获取即将到期用户（用于推送提醒）

    Args:
        threshold_days: 到期阈值(天)

    Returns:
        即将到期用户列表
    """
    now = datetime.now()
    threshold = now + timedelta(days=threshold_days)

    async for db in get_db():
        result = await db.execute(
            select(User).where(
                and_(
                    User.membership != "free",
                    User.membership_expire.isnot(None),
                    User.membership_expire > now,
                    User.membership_expire < threshold,
                )
            )
        )
        users = result.scalars().all()
        return [
            {
                "id": u.id,
                "nickname": u.nickname,
                "membership": u.membership,
                "membership_expire": u.membership_expire.isoformat() if u.membership_expire else None,
            }
            for u in users
        ]
