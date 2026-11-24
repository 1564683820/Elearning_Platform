// 答题卡二级页面 — 显示答题卡预览 + 保存图片 / 导出PDF
const api = require('../../../../utils/api')

Page({
  data: {
    examId: null,
    examTitle: '',
    questionCount: 0,
    optionCount: 0,
    imgSrc: '',      // 答题卡 PNG 图片临时路径
    pdfPath: '',     // 答题卡 PDF 临时路径
    loading: true,
    error: '',       // 加载失败时的错误信息
  },

  onLoad(options) {
    // 注意: Snowflake ID 超过 JS 安全整数范围，必须保留字符串形式
    const examId = options.examId || ''
    const examTitle = options.title || ''
    this.setData({ examId, examTitle })
    if (examId) {
      this.loadAnswerSheet(examId)
    } else {
      wx.showToast({ title: '参数错误', icon: 'none' })
    }
  },

  // 加载答题卡 — 下载 PNG 和 PDF
  async loadAnswerSheet(examId) {
    try {
      // 并行下载 PNG 和 PDF
      const [pngPath, pdfPath] = await Promise.all([
        api.exportAnswerSheetPng(examId).catch(() => null),
        api.exportAnswerSheetPdf(examId).catch(() => null),
      ])
      const hasImg = !!pngPath
      const hasPdf = !!pdfPath
      this.setData({
        imgSrc: pngPath || '',
        pdfPath: pdfPath || '',
        loading: false,
        error: hasImg ? '' : '答题卡生成失败，请重试',
      })
      if (!hasImg && !hasPdf) {
        wx.showToast({ title: '答题卡加载失败，请稍后重试', icon: 'none', duration: 3000 })
      } else if (!hasImg) {
        wx.showToast({ title: '图片加载失败，可尝试导出PDF', icon: 'none' })
      }
    } catch (err) {
      console.error('加载答题卡失败:', err)
      this.setData({
        loading: false,
        error: '加载答题卡失败，请检查网络后重试',
      })
      wx.showToast({ title: '加载失败', icon: 'none' })
    }
  },

  // 保存图片到相册
  saveImage() {
    const { imgSrc } = this.data
    if (!imgSrc) {
      wx.showToast({ title: '图片未就绪', icon: 'none' })
      return
    }
    wx.saveImageToPhotosAlbum({
      filePath: imgSrc,
      success() {
        wx.showToast({ title: '已保存到相册', icon: 'success' })
      },
      fail(err) {
        console.error('保存图片失败:', err)
        if (err.errMsg && err.errMsg.includes('auth deny')) {
          wx.showModal({
            title: '需要相册权限',
            content: '请在小程序设置中开启相册权限',
            success: (res) => {
              if (res.confirm) {
                wx.openSetting()
              }
            }
          })
        } else {
          // 降级：用预览方式让用户长按保存
          wx.previewImage({
            urls: [imgSrc],
            current: imgSrc,
            success() {
              wx.showToast({ title: '长按图片可保存到相册', icon: 'none' })
            }
          })
        }
      }
    })
  },

  // 导出 PDF
  exportPdf() {
    const { examId, pdfPath } = this.data
    if (pdfPath) {
      // 已经有缓存的 PDF，直接打开
      this._openPdf(pdfPath)
      return
    }
    // 没有缓存则下载
    wx.showLoading({ title: '生成PDF中...' })
    api.exportAnswerSheetPdf(examId)
      .then(tempFilePath => {
        wx.hideLoading()
        this.setData({ pdfPath: tempFilePath })
        this._openPdf(tempFilePath)
      })
      .catch(err => {
        wx.hideLoading()
        console.error('导出PDF失败:', err)
        wx.showToast({ title: 'PDF 导出失败', icon: 'none' })
      })
  },

  _openPdf(filePath) {
    wx.openDocument({
      filePath,
      fileType: 'pdf',
      success() {
        wx.showToast({ title: '可在右上角菜单中转发或打印', icon: 'none' })
      },
      fail(err) {
        console.error('打开PDF失败:', err)
        wx.showToast({ title: '打开失败', icon: 'none' })
      }
    })
  },
})
