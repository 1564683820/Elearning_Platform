"""
会员支付 API 路由

套餐列表 / 创建订单 / 支付回调 / 兑换码 / 会员信息
"""
import hashlib
import hmac
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.database import get_db
from app.api.deps import get_current_user, get_current_user_id, get_current_admin
from app.models.user import User
from app.services.membership_service import MembershipService
from app.core.middleware.membership_limit import (
    check_feature_access, MONTHLY_LIMITS, _plan_name,
)
from app.core.config import get_settings

router = APIRouter(prefix="/membership", tags=["会员"])


# ========== Request/Response Schemas ==========

class CreateOrderRequest(BaseModel):
    """创建订单请求"""
    plan: str = Field(..., description="套餐ID: vip_student/vip_teacher/vip_teacher_pro")
    duration_months: int = Field(default=1, ge=1, le=12, description="时长(月)")

class RedeemCodeRequest(BaseModel):
    """兑换码请求"""
    code: str = Field(..., description="16位兑换码")

class BatchGenerateCodesRequest(BaseModel):
    """批量生成兑换码请求(管理员)"""
    plan: str = Field(..., description="套餐ID")
    duration_months: int = Field(default=1, ge=1, le=12)
    count: int = Field(default=10, ge=1, le=1000)
    expire_days: int | None = Field(default=None, description="兑换码过期天数")
    remark: str = ""

class RedeemCodesQuery(BaseModel):
    """兑换码查询参数"""
    status: str | None = None
    batch_no: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ========== API Endpoints ==========

@router.get("/plans")
async def list_plans():
    """获取所有套餐列表"""
    return {"data": MembershipService.get_plans()}


@router.post("/create-order")
async def create_order(
    req: CreateOrderRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """创建会员订单（返回订单号和金额供前端发起支付）"""
    try:
        order = await MembershipService.create_order(
            db, user_id, req.plan, req.duration_months
        )
        return {"data": order}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/payment-callback")
async def payment_callback(
    order_no: str = Query(...),
    sign: str = Query(..., description="HMAC-SHA256 签名（使用 SECRET_KEY 签名 order_no）"),
    db: AsyncSession = Depends(get_db),
):
    """
    支付回调接口
    微信支付支付成功后，微信服务器会回调此接口。
    需要 order_no 和 sign 参数，sign = HMAC-SHA256(order_no, SECRET_KEY)
    """
    # 验证签名，防止伪造支付回调
    settings = get_settings()
    expected_sign = hmac.new(
        settings.SECRET_KEY.encode(),
        order_no.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sign, expected_sign):
        raise HTTPException(status_code=403, detail="签名验证失败")

    try:
        result = await MembershipService.handle_payment_callback(db, order_no)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/my-membership")
async def get_my_membership(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的会员信息"""
    info = await MembershipService.get_user_membership_info(db, user.id)
    return {"data": info}


@router.post("/redeem")
async def redeem_code(
    req: RedeemCodeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用户使用兑换码开通会员"""
    try:
        result = await MembershipService.redeem_code(db, user.id, req.code)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/usage/{feature}")
async def get_feature_usage(
    feature: str,
    user_id: int = Depends(get_current_user_id),
):
    """获取某功能本月的使用次数"""
    usage = await MembershipService.get_monthly_usage(user_id, feature)
    return {"data": usage}


@router.get("/my-quota")
async def get_my_quota(
    user: User = Depends(get_current_user),
):
    """获取当前用户的剩余权益额度（PPT 生成、试卷生成等）"""
    membership = user.membership or "free"
    is_expired = bool(
        user.membership_expire
        and user.membership_expire < datetime.now()
    )
    if is_expired:
        membership = "free"

    quotas = {}
    for feature in ("ai_ppt", "ai_exam"):
        limit = MONTHLY_LIMITS.get(feature, {}).get(membership, 0)
        usage_data = await MembershipService.get_monthly_usage(user.id, feature)
        used = usage_data["usage"]
        remaining = 999999 if limit >= 999999 else max(0, limit - used)
        quotas[feature] = {
            "limit": limit,
            "used": used,
            "remaining": remaining,
            "unlimited": limit >= 999999,
        }

    return {
        "data": {
            "membership": membership,
            "is_expired": is_expired,
            "membership_name": _plan_name(membership),
            "quotas": quotas,
        }
    }


# ========== 管理员接口 ==========

@router.post("/redeem-codes/batch")
async def batch_generate_codes(
    req: BatchGenerateCodesRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """批量生成兑换码（仅超级管理员）"""
    try:
        codes = await MembershipService.generate_redeem_codes(
            db, admin.id, req.plan, req.duration_months,
            req.count, req.expire_days, req.remark,
        )
        return {"data": {"batch_count": len(codes), "codes": codes}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/redeem-codes/list")
async def list_redeem_codes(
    status: str | None = None,
    batch_no: str | None = None,
    page: int = 1,
    page_size: int = 20,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """查询兑换码列表（仅超级管理员）"""
    result = await MembershipService.list_redeem_codes(
        db, admin.id, status, batch_no, page, page_size
    )
    return {"data": result}
