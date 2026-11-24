// 教师端 — 我的 Tab
const app = getApp()
const api = require('../../../utils/api')

Page({
  data: {
    profile: null,
    loading: true,
    // 修改昵称
    showNicknameDialog: false,
    newNickname: '',
    // 修改密码
    showPwdDialog: false,
    oldPwd: '',
    newPwd: '',
    confirmPwd: '',
  },

  onShow() {
    this.loadProfile()
  },

  async loadProfile() {
    this.setData({ loading: true })
    try {
      const profile = await api.getUserProfile()
      this.setData({ profile })
    } catch (err) {
      console.error('加载个人信息失败', err)
    } finally {
      this.setData({ loading: false })
    }
  },

  // 修改头像
  changeAvatar() {
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: async (res) => {
        const tempPath = res.tempFilePaths[0]
        try {
          await api.updateUserProfile({ avatar_url: tempPath })
          wx.showToast({ title: '头像更新成功' })
          this.loadProfile()
        } catch (err) {
          wx.showToast({ title: '更新失败', icon: 'none' })
        }
      }
    })
  },

  // 修改昵称
  openNicknameEdit() {
    this.setData({
      showNicknameDialog: true,
      newNickname: this.data.profile?.nickname || '',
    })
  },

  closeNicknameEdit() {
    this.setData({ showNicknameDialog: false })
  },

  onNicknameInput(e) {
    this.setData({ newNickname: e.detail.value })
  },

  async saveNickname() {
    const name = this.data.newNickname.trim()
    if (!name) {
      wx.showToast({ title: '昵称不能为空', icon: 'none' })
      return
    }
    try {
      await api.updateUserProfile({ nickname: name })
      wx.showToast({ title: '昵称已更新' })
      this.closeNicknameEdit()
      this.loadProfile()
    } catch (err) {
      wx.showToast({ title: err.message || '更新失败', icon: 'none' })
    }
  },

  // 修改密码
  openPwdEdit() {
    this.setData({
      showPwdDialog: true,
      oldPwd: '',
      newPwd: '',
      confirmPwd: '',
    })
  },

  closePwdEdit() {
    this.setData({ showPwdDialog: false })
  },

  onOldPwdInput(e) {
    this.setData({ oldPwd: e.detail.value })
  },

  onNewPwdInput(e) {
    this.setData({ newPwd: e.detail.value })
  },

  onConfirmPwdInput(e) {
    this.setData({ confirmPwd: e.detail.value })
  },

  async savePassword() {
    const { oldPwd, newPwd, confirmPwd } = this.data
    if (!oldPwd || !newPwd) {
      wx.showToast({ title: '请填写完整', icon: 'none' })
      return
    }
    if (newPwd !== confirmPwd) {
      wx.showToast({ title: '两次密码不一致', icon: 'none' })
      return
    }
    if (newPwd.length < 6) {
      wx.showToast({ title: '密码至少6位', icon: 'none' })
      return
    }
    try {
      await api.callHttpAPI('/user/change-password', {
        old_password: oldPwd,
        new_password: newPwd,
      }, 'POST')
      wx.showToast({ title: '密码已修改' })
      this.closePwdEdit()
    } catch (err) {
      wx.showToast({ title: err.message || '修改失败', icon: 'none' })
    }
  },

  // 退出登录
  logout() {
    wx.showModal({
      title: '退出确认',
      content: '退出后需要重新登录，确认退出吗？',
      success: (res) => {
        if (res.confirm) {
          app.logout()
          wx.redirectTo({ url: '/pages/login/index' })
        }
      }
    })
  },

  // 切换到学生端
  switchToStudent() {
    app.switchToStudent()
  },

  // 我的班级
  goToMyClasses() {
    wx.switchTab({ url: '/pages/teacher/class/index' })
  },

  // 使用帮助
  goToHelp() {
    wx.showToast({ title: '功能开发中', icon: 'none' })
  },
})
