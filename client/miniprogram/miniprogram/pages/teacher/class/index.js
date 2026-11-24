// 教师端 — 班级管理 Tab
const app = getApp()
const api = require('../../../utils/api')

Page({
  data: {
    classes: [],
    loading: true,
    showCreateDialog: false,
    newClassName: '',
    showDeleteDialog: false,
    deleteTarget: null,
    deleteConfirmName: '',
  },

  onShow() {
    this.loadClasses()
  },

  async loadClasses() {
    this.setData({ loading: true })
    try {
      // 使用教师端 API，与网页端共享同一份班级数据
      const result = await api.getTeacherClasses()
      const classList = result?.classes || result || []
      this.setData({ classes: classList })
    } catch (err) {
      console.error('加载班级列表失败', err)
      // 认证错误已由 callHttpAPI 统一处理跳转，不重复提示
      if (!err.message.includes('登录已过期')) {
        wx.showToast({ title: '加载班级失败', icon: 'none' })
      }
    } finally {
      this.setData({ loading: false })
    }
  },

  // 打开新建班级弹窗
  openCreate() {
    this.setData({ showCreateDialog: true, newClassName: '' })
  },

  closeCreate() {
    this.setData({ showCreateDialog: false })
  },

  async confirmCreate() {
    const name = this.data.newClassName.trim()
    if (!name) {
      wx.showToast({ title: '请输入班级名称', icon: 'none' })
      return
    }
    try {
      await api.callHttpAPI('/teacher/classes', { name }, 'POST')
      wx.showToast({ title: '班级创建成功' })
      this.closeCreate()
      this.loadClasses()
    } catch (err) {
      wx.showToast({ title: err.message || '创建失败', icon: 'none' })
    }
  },

  // 进入班级详情（学生列表）
  goToClass(e) {
    const { id, name } = e.currentTarget.dataset
    wx.navigateTo({
      url: `/pages/teacher/class/detail/index?classId=${id}&className=${encodeURIComponent(name)}`
    })
  },

  // 删除班级
  confirmDelete(e) {
    const cls = e.currentTarget.dataset.item
    this.setData({ showDeleteDialog: true, deleteTarget: cls, deleteConfirmName: '' })
  },

  closeDelete() {
    this.setData({ showDeleteDialog: false, deleteTarget: null })
  },

  onDeleteConfirmInput(e) {
    this.setData({ deleteConfirmName: e.detail.value })
  },

  async doDelete() {
    const target = this.data.deleteTarget
    if (this.data.deleteConfirmName !== target.name) {
      wx.showToast({ title: '班级名称不匹配', icon: 'none' })
      return
    }
    try {
      await api.callHttpAPI(`/teacher/classes/${target.id}`, {}, 'DELETE')
      wx.showToast({ title: '班级已删除' })
      this.closeDelete()
      this.loadClasses()
    } catch (err) {
      wx.showToast({ title: err.message || '删除失败', icon: 'none' })
    }
  },
})
