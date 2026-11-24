// 班级首页 — 显示学生加入的班级列表，支持加入新班级
const api = require('../../../utils/api.js');

Page({
  data: {
    classes: [],
    loading: true,
    showJoinModal: false,
    inviteCode: '',
    joinLoading: false,
  },

  _hasLoaded: false,  // 标记首次加载完成

  onLoad() {
    // data 中 loading 默认为 true，无需重复 setData
    this.loadClasses();
  },

  onShow() {
    // 已加载过的页面不做 loading 闪烁，用静默刷新
    // 分离窗口下避免 setData({loading:true}) 导致列表消失
    if (this._hasLoaded) {
      this.silentRefreshClasses();
    }
  },

  // 静默刷新列表（不显示 loading 状态）
  async silentRefreshClasses() {
    try {
      const result = await api.getMyClasses();
      const classes = (result && result.classes) || [];
      // 只有列表发生变化时才 setData，减少无意义通信
      const oldIds = (this.data.classes || []).map(c => c.id).sort().join(',');
      const newIds = classes.map(c => c.id).sort().join(',');
      if (oldIds !== newIds) {
        this.setData({ classes });
      }
    } catch (err) {
      console.error('静默刷新班级列表失败', err);
    }
  },

  // 加载班级列表
  async loadClasses() {
    try {
      const result = await api.getMyClasses();
      const classes = (result && result.classes) || [];
      // 合并 loading: false + classes 为一次 setData
      this.setData({ classes, loading: false });
      this._hasLoaded = true;
    } catch (err) {
      console.error('加载班级列表失败', err);
      this.setData({ loading: false });
      wx.showToast({ title: '加载班级失败', icon: 'none' });
    }
  },

  // 点击班级进入详情（3个Tab）
  onClassTap(e) {
    const classId = e.currentTarget.dataset.id;
    if (!classId) return;
    // 从缓存中查找班级名，避免 data-cls 传整个对象在分离窗口下的序列化开销
    const cls = (this.data.classes || []).find(c => c.id === classId);
    if (!cls) return;
    wx.navigateTo({
      url: `/pages/class/tabs/index?classId=${cls.id}&className=${encodeURIComponent(cls.name)}`,
    });
  },

  // 显示加入班级弹窗
  onShowJoinModal() {
    this.setData({
      showJoinModal: true,
      inviteCode: '',
    });
  },

  // 关闭加入班级弹窗
  onCloseJoinModal() {
    this.setData({ showJoinModal: false });
  },

  // 输入邀请码
  onInviteCodeInput(e) {
    this.setData({ inviteCode: e.detail.value });
  },

  // 提交加入班级
  async onJoinConfirm() {
    const code = this.data.inviteCode.trim();
    if (!code) {
      wx.showToast({ title: '请输入邀请码', icon: 'none' });
      return;
    }
    this.setData({ joinLoading: true });
    try {
      const result = await api.joinClass(code);
      wx.showToast({ title: '加入成功', icon: 'success' });
      this.setData({ showJoinModal: false, joinLoading: false });
      this.loadClasses();
    } catch (err) {
      this.setData({ joinLoading: false });
      wx.showToast({ title: err.message || '邀请码无效', icon: 'none' });
    }
  },

  // 阻止弹窗关闭冒泡
  preventClose() {},
});
