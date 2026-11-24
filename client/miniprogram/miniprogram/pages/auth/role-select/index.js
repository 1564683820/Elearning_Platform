// 角色选择页 — 首次登录选择身份
const api = require('../../../utils/api.js');

Page({
  data: {
    selectedRole: ''     // student / teacher / personal
  },

  // 选择角色
  onSelectRole(e) {
    const role = e.currentTarget.dataset.role;
    this.setData({ selectedRole: role });
  },

  // 确认选择
  async onConfirm() {
    const role = this.data.selectedRole;
    if (!role) {
      wx.showToast({ title: '请选择一个角色', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '保存中...' });

    try {
      // 更新用户角色
      await api.updateUserProfile({ role: role });
      wx.hideLoading();

      // 同步到全局数据
      const app = getApp();
      app.globalData.userRole = role;

      wx.showToast({ title: '设置成功', icon: 'success' });

      // 根据角色跳转
      if (role === 'teacher') {
        wx.redirectTo({ url: '/pages/teacher/class/index' });
      } else {
        wx.switchTab({ url: '/pages/home/index' });
      }
    } catch (err) {
      wx.hideLoading();
      console.error('角色选择失败', err);
      wx.showToast({ title: '设置失败，请重试', icon: 'none' });
    }
  },

  // 跳过选择
  onSkip() {
    wx.switchTab({ url: '/pages/home/index' });
  }
});