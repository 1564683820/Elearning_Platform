// 教师端 — 学生管理（查看学生、邀请码、移除学生）
const app = getApp();
const { getMyClasses, getTeacherStudents, removeStudentFromClass, regenerateInviteCode } = require('../../../utils/api');

Page({
  data: {
    className: '',
    classId: '',
    inviteCode: '',
    students: [],
    regenerating: false,
  },

  onLoad(options) {
    // 从教师工作台跳转时携带 classId 和 className
    if (options.classId) {
      this.setData({
        classId: options.classId,
        className: decodeURIComponent(options.className || ''),
      });
      this.loadStudents(options.classId);
    }
  },

  onShow() {
    // 如果没有 classId（直接进入），尝试加载第一个班级
    if (!this.data.classId) {
      this.loadFirstClass();
    }
  },

  async loadFirstClass() {
    try {
      const result = await getMyClasses();
      const classList = result.classes || [];
      if (classList.length > 0) {
        const cls = classList[0];
        this.setData({ classId: cls.id, className: cls.name });
        await this.loadStudents(cls.id);
      }
    } catch (err) {
      console.error('加载班级数据失败', err);
    }
  },

  async loadStudents(classId) {
    try {
      const students = await getTeacherStudents(classId);
      this.setData({ students: students || [] });
      // 从班级详情获取邀请码
      const result = await getMyClasses();
      const classList = result.classes || [];
      const cls = classList.find(c => c.id === classId);
      if (cls) {
        this.setData({ inviteCode: cls.invite_code || '' });
      }
    } catch (err) {
      console.error('加载学生数据失败', err);
    }
  },

  copyInvite() {
    wx.setClipboardData({
      data: this.data.inviteCode,
      success: () => wx.showToast({ title: '已复制邀请码', icon: 'none' }),
    });
  },

  // 刷新/重新生成邀请码
  onRegenerateInvite() {
    const that = this;
    wx.showModal({
      title: '重新生成邀请码',
      content: '重新生成后，旧的邀请码将立即失效，学生需要使用新的邀请码加入班级。确定要重新生成吗？',
      confirmText: '确认生成',
      confirmColor: '#2D7D46',
      success: async (res) => {
        if (res.confirm) {
          that.setData({ regenerating: true });
          wx.showLoading({ title: '生成中...', mask: true });
          try {
            const result = await regenerateInviteCode(that.data.classId);
            const newCode = result.data?.invite_code || result.invite_code || '';
            that.setData({ inviteCode: newCode });
            wx.hideLoading();
            wx.showToast({ title: '邀请码已更新', icon: 'success' });
          } catch (err) {
            wx.hideLoading();
            console.error('生成邀请码失败', err);
            wx.showToast({ title: '生成失败，请重试', icon: 'none' });
          } finally {
            that.setData({ regenerating: false });
          }
        }
      },
    });
  },

  confirmRemove(e) {
    const studentId = e.currentTarget.dataset.id;
    wx.showModal({
      title: '确认移除',
      content: '确定将该学生从班级移除吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await removeStudentFromClass(this.data.classId, studentId);
            wx.showToast({ title: '已移除' });
            this.loadStudents(this.data.classId);
          } catch (err) {
            wx.showToast({ title: '移除失败', icon: 'none' });
          }
        }
      },
    });
  },
});
