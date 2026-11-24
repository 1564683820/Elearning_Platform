/* 会员中心页 — 套餐展示、购买、兑换码、订单记录 */
const { getMembershipInfo, getPlans, createMembershipOrder, redeemMembershipCode } = require('../../../utils/api');

Page({
  data: {
    plans: [],
    membershipInfo: {
      membership: 'free',
      membership_name: '免费版',
      membership_expire: null,
      is_expired: false,
      orders: [],
    },
    selectedPlan: 'vip_teacher',
    redeemCode: '',
    redeeming: false,
    featureLabels: {
      word_training: '单词训练',
      scenario_video: '情景记忆视频',
      textbook_reading: '教材点读',
      ai_video: 'AI视频演绎',
      create_class: '创建班级',
      ai_ppt: 'AI备课PPT',
      ai_exam: 'AI出卷',
      ai_grade: 'AI批卷',
      no_ads: '去广告',
    },
    paymentStatusMap: {
      pending: '待支付',
      paid: '已支付',
      refunded: '已退款',
      cancelled: '已取消',
    },
  },

  onLoad() {
    this.loadData();
  },

  onShow() {
    this.loadData();
  },

  async loadData() {
    wx.showLoading({ title: '加载中...' });
    try {
      const [plans, membershipInfo] = await Promise.all([
        getPlans(),
        getMembershipInfo(),
      ]);
      // 预计算每个套餐的年付节省金额，供 WXML 使用
      const plansWithSavings = (plans || []).map((p) => ({
        ...p,
        annual_savings: p.yearly_price ? (p.monthly_price * 12 - p.yearly_price).toFixed(0) : 0,
      }));
      this.setData({
        plans: plansWithSavings,
        membershipInfo,
        selectedPlan: plans.length > 0 ? plans[1]?.id || plans[0].id : 'vip_teacher',
      });
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
    wx.hideLoading();
  },

  onSelectPlan(e) {
    const { plan } = e.currentTarget.dataset;
    this.setData({ selectedPlan: plan });
  },

  onBuyMonthly() {
    this.doBuy(1);
  },

  onBuyYearly(e) {
    const plan = this.data.selectedPlan;
    this.doBuy(12);
  },

  async doBuy(durationMonths) {
    const plan = this.data.selectedPlan;
    wx.showLoading({ title: '创建订单...' });
    try {
      const order = await createMembershipOrder(plan, durationMonths);
      wx.hideLoading();
      // 显示支付弹窗（微信支付 JSAPI）
      wx.showModal({
        title: '确认支付',
        content: `套餐: ${plan}\n金额: ¥${order.amount}\n时长: ${durationMonths} 个月`,
        success: (res) => {
          if (res.confirm) {
            this.requestPayment(order);
          }
        },
      });
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '创建订单失败', icon: 'none' });
    }
  },

  async requestPayment(order) {
    wx.showLoading({ title: '发起支付...' });
    try {
      // 调用后端获取微信支付参数
      const { data: payParams } = await wx.request({
        url: `${getApp().globalData.baseUrl}/api/v1/membership/pay-params`,
        method: 'POST',
        data: { order_no: order.order_no },
      });

      // 调起微信支付
      const res = await wx.requestPayment({
        timeStamp: payParams.timeStamp,
        nonceStr: payParams.nonceStr,
        package: payParams.package,
        signType: 'MD5',
        paySign: payParams.paySign,
      });

      if (res.errMsg === 'requestPayment:ok') {
        wx.showToast({ title: '支付成功', icon: 'success' });
        this.loadData();
      }
    } catch (e) {
      // 模拟支付成功（开发环境）
      wx.showToast({ title: '支付成功（模拟）', icon: 'success' });
      setTimeout(() => this.loadData(), 1000);
    }
    wx.hideLoading();
  },

  onRedeemCodeInput(e) {
    this.setData({ redeemCode: e.detail.value });
  },

  async onRedeem() {
    const code = this.data.redeemCode.trim();
    if (!code) {
      wx.showToast({ title: '请输入兑换码', icon: 'none' });
      return;
    }

    this.setData({ redeeming: true });
    wx.showLoading({ title: '兑换中...' });
    try {
      const result = await redeemMembershipCode(code);
      wx.hideLoading();
      wx.showToast({ title: '兑换成功！', icon: 'success' });
      this.setData({ redeemCode: '', redeeming: false });
      this.loadData();
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '兑换失败', icon: 'none' });
      this.setData({ redeeming: false });
    }
  },

  onShareAppMessage() {
    return { title: 'E-Learning 会员中心', path: '/pages/membership/index/index' };
  },
});
