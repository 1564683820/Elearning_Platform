// 教师端 — Excel花名册导入
const api = require('../../../../utils/api')

Page({
  data: {
    classId: null,
    className: '',
    importing: false,
    importResult: null,
    errorMsg: '',
    createdAccountCount: 0,
  },

  onLoad(options) {
    this.setData({
      classId: parseInt(options.classId),
      className: decodeURIComponent(options.className || ''),
    })
  },

  // 选择 Excel 文件
  chooseFile() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['xlsx', 'xls'],
      success: (res) => {
        const file = res.tempFiles[0]
        if (file.size > 5 * 1024 * 1024) {
          wx.showToast({ title: '文件过大（限5MB）', icon: 'none' })
          return
        }
        this.uploadFile(file.path)
      },
      fail: () => {
        wx.showToast({ title: '未选择文件', icon: 'none' })
      }
    })
  },

  async uploadFile(filePath) {
    this.setData({ importing: true, errorMsg: '', importResult: null })
    try {
      // 使用 wx.uploadFile 上传
      const result = await new Promise((resolve, reject) => {
        const header = {}
        const token = api.getAuthToken()
        if (token) header['Authorization'] = `Bearer ${token}`

        wx.uploadFile({
          url: `${api.BASE_URL}/teacher/classes/${this.data.classId}/students/upload-excel`,
          filePath,
          name: 'file',
          header,
          timeout: 60000,
          success(res) {
            try {
              const data = JSON.parse(res.data)
              if (data.code === 0) resolve(data.data)
              else reject(new Error(data.message || '导入失败'))
            } catch (e) {
              reject(new Error('响应解析失败'))
            }
          },
          fail: reject
        })
      })

      const items = result?.items || []
      const createdCount = items.filter(i => i.created_account).length

      this.setData({
        importing: false,
        importResult: result,
        createdAccountCount: createdCount,
      })
      wx.showToast({ title: `导入成功，共导入 ${result?.imported || 0} 名，自动创建 ${createdCount} 个账号` })
    } catch (err) {
      this.setData({
        importing: false,
        errorMsg: err.message || '导入失败，请检查格式',
      })
    }
  },

  // 查看学生列表
  viewStudents() {
    wx.navigateTo({
      url: `/pages/teacher/class/detail/index?classId=${this.data.classId}&className=${encodeURIComponent(this.data.className)}`
    })
  },

  // 返回班级
  goBack() {
    wx.navigateBack()
  },
})
