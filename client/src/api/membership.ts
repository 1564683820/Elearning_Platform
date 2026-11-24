/* 会员管理 API 封装 */
import client from './client';

export interface PlanInfo {
  id: string;
  name: string;
  monthly_price: number;
  yearly_price: number;
  description: string;
  features: string[];
}

export interface MembershipInfo {
  user_id: number;
  nickname: string;
  role: string;
  membership: string;
  membership_level: number;
  membership_name: string;
  membership_expire: string | null;
  is_expired: boolean;
  orders: any[];
}

export interface OrderInfo {
  order_id: number;
  order_no: string;
  amount: number;
  plan: string;
  duration_months: number;
  payment_status: string;
  created_at: string;
}

export interface FeatureQuota {
  limit: number;
  used: number;
  remaining: number;
  unlimited: boolean;
}

export interface MyQuotaInfo {
  membership: string;
  is_expired: boolean;
  membership_name: string;
  quotas: {
    ai_ppt: FeatureQuota;
    ai_exam: FeatureQuota;
  };
}

function extractData<T>(res: { data: { data: T } }): T {
  return res.data.data;
}

export const membershipApi = {
  /* 获取套餐列表 */
  getPlans: () =>
    client.get('/membership/plans').then(extractData<PlanInfo[]>),

  /* 获取当前用户会员信息 */
  getMyMembership: () =>
    client.get('/membership/my-membership').then(extractData<MembershipInfo>),

  /* 获取当前用户权益额度（PPT/试卷剩余次数） */
  getMyQuota: () =>
    client.get('/membership/my-quota').then(extractData<MyQuotaInfo>),

  /* 创建订单 */
  createOrder: (data: { plan: string; duration_months: number }) =>
    client.post('/membership/create-order', data).then(extractData<OrderInfo>),

  /* 兑换码 */
  redeemCode: (code: string) =>
    client.post('/membership/redeem', { code }).then(extractData<any>),

  /* 后台 - 批量生成兑换码 */
  batchGenerateCodes: (data: {
    plan: string;
    duration_months: number;
    count: number;
    expire_days?: number;
    remark?: string;
  }) => client.post('/membership/redeem-codes/batch', data).then(extractData<{ batch_count: number; codes: any[] }>),

  /* 后台 - 查询兑换码列表 */
  listRedeemCodes: (params?: { status?: string; batch_no?: string; page?: number; page_size?: number }) =>
    client.get('/membership/redeem-codes/list', { params }).then(extractData<{ items: any[]; total: number }>),
};
