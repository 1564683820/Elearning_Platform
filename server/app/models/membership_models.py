"""
会员模块 ORM Model
表: user_membership_order, redeem_code
"""
from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, DateTime, DECIMAL, Integer, Text,
    func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


class UserMembershipOrder(Base):
    """会员订单表"""
    __tablename__ = "user_membership_order"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, index=True, comment="用户ID")
    plan = Column(String(32), nullable=False, comment="套餐: vip_student/vip_teacher/vip_teacher_pro")
    order_no = Column(String(64), unique=True, nullable=False, comment="商户订单号")
    amount = Column(DECIMAL(8, 2), nullable=False, comment="支付金额(元)")
    duration_months = Column(Integer, nullable=False, comment="时长(月)")
    payment_status = Column(String(16), default="pending", comment="pending/paid/refunded/cancelled")
    pay_type = Column(String(16), default="wxpay", comment="wxpay/redeem")
    paid_at = Column(DateTime, default=None, comment="支付时间")
    expire_at = Column(DateTime, default=None, comment="会员到期时间")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "comment": "会员订单表"},
    )


class RedeemCode(Base):
    """兑换码表"""
    __tablename__ = "redeem_code"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    code = Column(String(32), unique=True, nullable=False, comment="兑换码")
    plan = Column(String(32), nullable=False, comment="对应套餐")
    duration_months = Column(Integer, nullable=False, default=1, comment="时长(月)")
    status = Column(String(16), default="active", comment="active/used/expired/disabled")
    created_by = Column(BigInteger, nullable=False, comment="创建人ID")
    batch_no = Column(String(64), default=None, comment="批次号")
    used_by = Column(BigInteger, default=None, comment="使用者ID")
    used_at = Column(DateTime, default=None, comment="使用时间")
    expire_at = Column(DateTime, default=None, comment="兑换码过期时间")
    remark = Column(String(256), default="", comment="备注")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "comment": "兑换码表"},
    )
