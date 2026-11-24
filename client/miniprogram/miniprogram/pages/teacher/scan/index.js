// 教师端 — 摄像头批卷核心页（批量拍照，每张立即独立识别）
const app = getApp()
const api = require('../../../utils/api')

Page({
  data: {
    examId: null,
    examTitle: '',
    classId: null,
    scanMode: 'server',
    cameraReady: false,
    scanning: false,           // 正在拍照中（快门按下到照片生成）
    // 批量队列：每张独立识别，不阻塞相机
    photoQueue: [],            // [{id, tempPath, timestamp, status: 'processing'|'success'|'error', ...result}]
    // 结果总览
    showResults: false,        // 是否显示结果汇总弹窗
    // 进度
    gradedCount: 0,
    totalStudents: 0,
    currentStudentName: '',
    // 队列统计数据（WXML 中不能使用箭头函数/filter）
    successCount: 0,
    processingCount: 0,
    errorCount: 0,
    unsubmittedCount: 0,
    // 错误提示
    errorMsg: '',
    showError: false,
    // 亮度检测
    brightnessWarning: '',
  },

  onLoad(options) {
    const { examId, examTitle, classId } = options
    this.setData({
      examId: String(examId || ''),
      examTitle: decodeURIComponent(examTitle || ''),
      classId: String(classId || '') || null,
    })
    this._cameraReady = false
    this._cameraCtx = null
    this._recognizing = {}     // 防止同一张照片重复识别
    this.loadProgress()
  },

  onShow() {
    this._cameraReady = true
  },

  onHide() {
    this._cameraReady = false
  },

  onUnload() {
    this._cameraReady = false
    this._cameraCtx = null
  },

  onCameraError(e) {
    console.error('摄像头错误:', e.detail)
    this._cameraReady = false
    setTimeout(() => { this._cameraReady = true }, 1500)
  },

  async loadProgress() {
    if (!this.data.examId) return
    try {
      const progress = await api.callHttpAPI(
        `/teacher/exam/${this.data.examId}/scan-progress`, {}, 'GET'
      )
      this.setData({
        gradedCount: progress?.graded_count || 0,
        totalStudents: progress?.total_students || 0,
      })
    } catch (err) {
      console.error('加载批改进度失败', err)
    }
  },

  // 切换扫描模式
  switchScanMode() {
    const newMode = this.data.scanMode === 'local' ? 'server' : 'local'
    this.setData({ scanMode: newMode, showError: false })
    wx.showToast({ title: newMode === 'server' ? '服务端扫描' : '本地扫描', icon: 'none' })
  },

  // ===================== 拍照（加入队列 + 立即识别） =====================
  onCapture() {
    if (this.data.scanning) return
    if (!this._cameraReady) {
      this.setData({ showError: true, errorMsg: '摄像头未就绪，请稍后再试' })
      return
    }
    this.setData({ scanning: true, showError: false })

    if (!this._cameraCtx) {
      this._cameraCtx = wx.createCameraContext()
    }
    this._cameraCtx.takePhoto({
      quality: 'high',
      success: (res) => {
        const id = Date.now() + '_' + Math.random().toString(36).slice(2, 6)
        const newItem = {
          id,
          tempPath: res.tempImagePath,
          timestamp: Date.now(),
          status: 'processing',    // processing | success | error
          exam_number: '',
          student_name: '',
          score: 0,
          max_score: 0,
          pending_count: 0,
          answers: [],
          wrong_questions: [],
          errorMsg: '',
          _raw: null,
        }
        const queue = [...this.data.photoQueue, newItem]
        this.setData({ scanning: false, photoQueue: queue, ...this._computeQueueStats(queue) })

        // 立即异步识别，不阻塞相机
        this.recognizePhoto(id)
      },
      fail: (err) => {
        this._cameraCtx = null
        this.setData({ scanning: false, showError: true, errorMsg: '拍照失败，请检查摄像头权限' })
      }
    })
  },

  // ===================== 单张照片独立识别（异步，不阻塞） =====================
  async recognizePhoto(photoId) {
    if (this._recognizing[photoId]) return
    this._recognizing[photoId] = true

    const item = this.data.photoQueue.find(p => p.id === photoId)
    if (!item) { delete this._recognizing[photoId]; return }

    try {
      const result = await api.scanGrade(this.data.examId, item.tempPath, this.data.classId)
      if (!result || !result.submission_id) {
        throw new Error('服务端未返回保存记录，请先核对成绩列表，避免重复提交')
      }

      // 映射服务端返回
      const answers = (result.answers || []).map(a => ({
        question_number: a.question_number,
        question_type: a.question_type || 'single',
        selected: a.student_answer ? [a.student_answer] : [],
        correct: a.correct_answer ? [a.correct_answer] : [],
        is_correct: a.is_correct,
        score: a.score || 0,
        max_score: a.max_score || 0,
        options: a.options || ['A', 'B', 'C', 'D'],
        status: a.status || (a.is_correct ? 'normal' : 'blank'),
        filled_circles: a.student_answer ? [a.student_answer] : [],
        expected_count: 1,
        _selectedText: a.student_answer || '',
        _correctText: a.correct_answer || '',
        _filledCirclesText: a.student_answer || '',
      }))

      const pendingCount = answers.filter(a =>
        ['light', 'multi', 'uncertain', 'all_filled', 'multi_excess', 'multi_short'].includes(a.status)
      ).length
      const score = result.total_score ?? 0
      const maxScore = result.max_score ?? 0
      const wrongQuestions = answers.filter(a => !a.is_correct).map(a => ({
        question_number: a.question_number,
        question_type: a.question_type,
        student_answer: Array.isArray(a.selected) ? a.selected.join(',') : a.selected,
        correct_answer: Array.isArray(a.correct) ? a.correct.join(',') : a.correct,
        question_score: a.score,
        status: a.status,
      }))

      this._updatePhotoItem(photoId, {
        status: 'success',
        exam_number: result.exam_number || '',
        student_name: result.student_name || '',
        student_id: result.student_id || null,
        submission_id: result.submission_id,
        _submitted: true, // scan-grade 已在服务端保存，不再调用 /scan 二次覆盖。
        score,
        max_score: maxScore,
        pending_count: pendingCount,
        answers,
        wrong_questions: wrongQuestions,
        _raw: result,
      })
      this.loadProgress()
    } catch (err) {
      console.error('识别失败 photoId=', photoId, err)
      this._updatePhotoItem(photoId, {
        status: 'error',
        errorMsg: err.message || '识别失败',
      })
    }
    delete this._recognizing[photoId]
  },

  // 根据当前队列计算统计数据（WXML 中无法执行 filter/箭头函数）
  _computeQueueStats(queue) {
    const successCount = queue.filter(p => p.status === 'success').length
    const processingCount = queue.filter(p => p.status === 'processing').length
    const errorCount = queue.filter(p => p.status === 'error').length
    const unsubmittedCount = queue.filter(p => p.status === 'success' && !p._submitted).length
    return { successCount, processingCount, errorCount, unsubmittedCount }
  },

  // 线程安全地更新队列中的某张照片
  _updatePhotoItem(photoId, updates) {
    const queue = this.data.photoQueue.map(p => {
      if (p.id === photoId) return { ...p, ...updates }
      return p
    })
    this.setData({ photoQueue: queue, ...this._computeQueueStats(queue) })
  },

  // ===================== 队列操作 =====================
  // 移除某张照片
  onRemovePhoto(e) {
    const photoId = e.currentTarget.dataset.id
    const queue = this.data.photoQueue.filter(p => p.id !== photoId)
    this.setData({ photoQueue: queue, ...this._computeQueueStats(queue) })
  },

  // 预览某张照片
  onPreviewPhoto(e) {
    const photoId = e.currentTarget.dataset.id
    const urls = this.data.photoQueue.map(p => p.tempPath)
    const idx = this.data.photoQueue.findIndex(p => p.id === photoId)
    if (idx >= 0) wx.previewImage({ current: urls[idx], urls })
  },

  // 重试失败的识别
  onRetrySingle(e) {
    const photoId = e.currentTarget.dataset.id
    // 先重置状态为 processing
    this._updatePhotoItem(photoId, { status: 'processing', errorMsg: '' })
    // 重新识别
    this.recognizePhoto(photoId)
  },

  // ===================== 完成拍照 → 显示结果汇总 =====================
  onFinishCapture() {
    const queue = this.data.photoQueue
    if (queue.length === 0) {
      wx.showToast({ title: '请先拍照', icon: 'none' })
      return
    }
    const processing = queue.filter(p => p.status === 'processing').length
    if (processing > 0) {
      wx.showToast({ title: `还有${processing}张正在识别中...`, icon: 'none', duration: 1500 })
    }
    this.setData({ showResults: true })
  },

  // 返回拍照
  onResetBatch() {
    this.setData({
      showResults: false,
    })
  },

  // 清空队列重新开始
  onRetakeAll() {
    const queue = this.data.photoQueue
    const processing = queue.filter(p => p.status === 'processing').length
    const msg = processing > 0
      ? `还有${processing}张正在识别中，确定清空全部${queue.length}张照片吗？`
      : `确定清空已拍的${queue.length}张照片吗？`
    wx.showModal({
      title: '重新拍摄',
      content: msg,
      success: (res) => {
        if (res.confirm) {
          this._recognizing = {}
          this.setData({ photoQueue: [], showResults: false, successCount: 0, processingCount: 0, errorCount: 0, unsubmittedCount: 0 })
        }
      }
    })
  },

  // ===================== 查看详情 =====================
  onViewResultDetail(e) {
    const photoId = e.currentTarget.dataset.id
    const item = this.data.photoQueue.find(p => p.id === photoId)
    if (!item || item.status !== 'success') return

    const scanResult = {
      exam_number: item.exam_number,
      student_id: item.student_id,
      student_name: item.student_name,
      score: item.score,
      max_score: item.max_score,
      pending_count: item.pending_count,
      answers: item.answers,
      wrong_questions: item.wrong_questions,
    }
    wx.navigateTo({
      url: '/pages/teacher/scan/result/index?data=' + encodeURIComponent(JSON.stringify(scanResult))
    })
  },

  // scan-grade 已保存结果，此入口仅刷新服务端成绩，不能重复覆盖答案。
  async submitAllResults() {
    await this.loadProgress()
    wx.showToast({ title: '识别成功的成绩已自动保存', icon: 'none' })
  },

  // ===================== 兼容旧版方法 =====================
  retryScan() {
    this.setData({ showError: false, errorMsg: '' })
  },

  goToManualInput() {
    wx.showToast({ title: '手动输入模式（待实现）', icon: 'none' })
  },

  goToResult() {
    // 兼容旧版：如果有 scanResult 则跳详情，否则打开结果汇总
    if (this.data.photoQueue.length > 0) {
      this.onFinishCapture()
    }
  },

  // ===================== 答题卡模板 =====================
  goToAnswerSheet() {
    const { examId } = this.data
    const items = ['空白答题卡（通用模板）']
    if (examId) {
      items.push('当前考试答题卡（PDF）')
      items.push('当前考试答题卡（图片预览）')
    }
    wx.showActionSheet({
      itemList: items,
      success: (res) => {
        if (res.tapIndex === 0) this.downloadBlankAnswerSheet()
        else if (res.tapIndex === 1 && examId) this.downloadExamAnswerSheet(examId)
        else if (res.tapIndex === 2 && examId) this.previewExamAnswerSheetImage(examId)
      },
      fail: () => {}
    })
  },

  downloadBlankAnswerSheet() {
    wx.showLoading({ title: '加载中...' })
    const header = { Authorization: `Bearer ${api.getAuthToken()}` }
    wx.downloadFile({
      url: `${api.BASE_URL}/teacher/exam/answer-sheet-template-pdf`, header, timeout: 30000,
      success: (dlRes) => {
        wx.hideLoading()
        wx.openDocument({ filePath: dlRes.tempFilePath, fileType: 'pdf' })
      },
      fail: () => { wx.hideLoading(); wx.showToast({ title: '下载失败', icon: 'none' }) }
    })
  },

  downloadExamAnswerSheet(examId) {
    wx.showLoading({ title: '生成中...' })
    const header = { Authorization: `Bearer ${api.getAuthToken()}` }
    wx.downloadFile({
      url: `${api.BASE_URL}/teacher/exam/${examId}/answer-sheet-pdf`, header, timeout: 60000,
      success: (dlRes) => {
        wx.hideLoading()
        wx.openDocument({ filePath: dlRes.tempFilePath, fileType: 'pdf' })
      },
      fail: () => { wx.hideLoading(); wx.showToast({ title: '下载失败', icon: 'none' }) }
    })
  },

  previewExamAnswerSheetImage(examId) {
    wx.showLoading({ title: '生成图片中...' })
    const header = { Authorization: `Bearer ${api.getAuthToken()}` }
    wx.downloadFile({
      url: `${api.BASE_URL}/teacher/exam/${examId}/answer-sheet-png`, header, timeout: 60000,
      success: (dlRes) => {
        wx.hideLoading()
        if (dlRes.statusCode !== 200) { wx.showToast({ title: '图片生成失败', icon: 'none' }); return }
        wx.previewImage({ urls: [dlRes.tempFilePath], current: dlRes.tempFilePath })
      },
      fail: () => { wx.hideLoading(); wx.showToast({ title: '下载失败', icon: 'none' }) }
    })
  },
})
