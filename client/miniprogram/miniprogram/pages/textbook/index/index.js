// 教材点读页 — 底部Tab: 点读 / 教材上传
const app = getApp();
const api = require('../../../utils/api');

Page({
  data: {
    // 底部Tab
    activeTab: 0,               // 0=点读, 1=教材
    tabItems: [
      { key: 'read', label: '点读' },
      { key: 'upload', label: '教材' },
    ],

    // ===== 点读 Tab 数据 =====
    loading: false,
    networkError: false,
    errorMsg: '',
    currentStep: 0,            // 0=版本, 1=年级, 2=学期, 3=单元
    breadcrumb: [],
    versions: [],
    grades: [],
    semesters: [],
    units: [],
    selectedVersion: '',
    selectedGrade: '',
    selectedSemester: '',
    semesterLabels: {
      '上': '上学期', '下': '下学期',
      'first': '上学期', 'second': '下学期',
      '上册': '上学期', '下册': '下学期'
    },

    // ===== 教材上传 Tab 数据 =====
    uploading: false,
    uploadProgress: 0,
    parseStage: '',             // '' / 'uploading' / 'parsing' / 'done' / 'error'
    parseProgress: 0,           // 解析进度百分比
    parseProgressText: '',      // 解析进度详情文本（如 "解析中 5/15 页"）
    uploadStatus: '',           // '' / 'uploading' / 'done' / 'error'
    uploadedTextbooks: [],      // 已上传教材列表

    // ===== 批量处理 =====
    showBatchMenu: false,       // 是否显示批量操作菜单
    batchItem: null,            // 当前选中的教材项
    batchProcessing: false,     // 是否正在批量处理中
    batchProgressText: '',      // 处理进度文本
    batchProgressTitle: '',     // 处理进度标题
    batchProgressPct: 0,        // 处理进度百分比
  },

  onLoad() {
    this.loadVersions();
    this._loadUploadedList();
  },

  // ===== 底部Tab切换 =====
  onTabChange(e) {
    const idx = e.currentTarget.dataset.index;
    this.setData({ activeTab: idx });
  },

  // ======================================================================
  //  点读 Tab：教材多级选择
  // ======================================================================

  _getErrorType(err) {
    const msg = (err && (err.message || err.errMsg || '')) || '';
    return msg.includes('request:fail') || msg.includes('timeout') || msg.includes('network')
      ? 'network'
      : 'api';
  },

  _handleError(err, context) {
    const errorType = this._getErrorType(err);
    const isNetwork = errorType === 'network';
    const msg = (err && (err.message || err.errMsg || '')) || '操作失败，请重试';
    this.setData({
      networkError: isNetwork,
      errorMsg: isNetwork ? '网络连接失败，已加载默认数据' : (msg || context + '失败')
    });
    if (isNetwork) {
      wx.showToast({ title: '网络异常，已使用默认数据', icon: 'none', duration: 2000 });
    } else {
      wx.showToast({ title: context + '失败: ' + msg, icon: 'none', duration: 2000 });
    }
    setTimeout(() => {
      if (this.data.networkError) {
        this.setData({ networkError: false, errorMsg: '' });
      }
    }, 3000);
  },

  loadVersions() {
    this.setData({ loading: true, networkError: false, errorMsg: '' });
    api.getTextbookVersions()
      .then(versions => {
        if (versions && versions.length > 0) {
          this.setData({ versions, breadcrumb: [], selectedVersion: '' });
        } else {
          this.setData({ versions: ['PEP'], breadcrumb: [], networkError: false });
          wx.showToast({ title: '暂无教材数据，已使用默认版本', icon: 'none', duration: 2000 });
        }
      })
      .catch(err => {
        this._handleError(err, '加载教材版本');
        this.setData({ versions: ['PEP'], breadcrumb: [] });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },

  onSelectVersion(e) {
    const version = e.currentTarget.dataset.version;
    this.setData({
      selectedVersion: version,
      loading: true,
      networkError: false,
      errorMsg: '',
      breadcrumb: [version]
    });
    api.getTextbookGrades(version)
      .then(grades => {
        if (grades && grades.length > 0) {
          grades.sort((a, b) => parseInt(a) - parseInt(b));
          this.setData({ grades, currentStep: 1 });
        } else {
          this.setData({ grades: ['3', '4', '5', '6'], currentStep: 1 });
          wx.showToast({ title: '暂无年级数据，已使用默认年级', icon: 'none', duration: 2000 });
        }
      })
      .catch(err => {
        this._handleError(err, '加载年级列表');
        this.setData({ grades: ['3', '4', '5', '6'], currentStep: 1 });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },

  onSelectGrade(e) {
    const grade = e.currentTarget.dataset.grade;
    const version = this.data.selectedVersion;
    this.setData({
      selectedGrade: grade,
      loading: true,
      networkError: false,
      errorMsg: '',
      breadcrumb: [version, `三-六年级${grade}`]
    });
    api.getTextbookSemesters(version, grade)
      .then(semesters => {
        const semesterList = semesters && semesters.length ? semesters : ['上', '下'];
        if (!semesters || !semesters.length) {
          wx.showToast({ title: '暂无学期数据，已使用默认学期', icon: 'none', duration: 2000 });
        }
        this.setData({ semesters: semesterList, currentStep: 2 });
      })
      .catch(err => {
        this._handleError(err, '加载学期列表');
        this.setData({ semesters: ['上', '下'], currentStep: 2 });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },

  onSelectSemester(e) {
    const semester = e.currentTarget.dataset.semester;
    this.loadUnits(semester);
  },

  loadUnits(semester) {
    const { selectedVersion: version, selectedGrade: grade } = this.data;
    this.setData({ loading: true, selectedSemester: semester, networkError: false, errorMsg: '' });
    api.getTextbookUnits(version, grade, semester)
      .then(units => {
        this.setData({ units: units || [], currentStep: 3 });
        if (!units || !units.length) {
          wx.showToast({ title: '该教材暂无单元数据', icon: 'none', duration: 2000 });
        }
      })
      .catch(err => {
        this._handleError(err, '加载单元列表');
        this.setData({ units: [], currentStep: 3 });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  },

  onRetry() {
    this.loadVersions();
  },

  onSelectUnit(e) {
    const unit = e.currentTarget.dataset.unit;
    const { selectedVersion: version, selectedGrade: grade, selectedSemester: semester } = this.data;
    wx.navigateTo({
      url: `/pages/textbook/reader/index?version=${version}&grade=${grade}&semester=${semester}&unit=${unit}`
    });
  },

  goBack(e) {
    const step = parseInt(e.currentTarget.dataset.step);
    this.setData({ currentStep: step, breadcrumb: this.data.breadcrumb.slice(0, step) });
  },

  // ======================================================================
  //  教材 Tab：上传教材文档
  // ======================================================================

  /** 加载已上传的教材列表 */
  _loadUploadedList() {
    api.getTextbookUploads({ page: 1, pageSize: 50 }).then(data => {
      const items = (data.items || []).map(item => ({
        id: item.id,
        name: item.filename || '未知文件',
        size: item.file_size ? (item.file_size / 1024 / 1024).toFixed(1) + ' MB' : '0 MB',
        date: item.created_at ? item.created_at.slice(0, 10) : '',
        status: item.parse_status === 2 ? 'complete' : item.parse_status === 1 ? 'processing' : item.parse_status === 3 ? 'error' : 'pending',
        parse_status: item.parse_status,
        total_pages: item.total_pages,
        parsed_pages: item.parsed_pages,
        error_msg: item.error_msg || '',
        grade: item.grade || '',
        semester: item.semester || '',
        animDone: item.animDone || false,
        audioDone: item.audioDone || false,
        animCount: item.animCount || 0,
        audioCount: item.audioCount || 0,
      }));
      this.setData({ uploadedTextbooks: items });
    }).catch(err => {
      console.warn('加载上传列表失败', err);
    });
  },

  /** 选择文件并上传 */
  onUploadTap() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['pdf'],
      success: (res) => {
        const file = res.tempFiles[0];
        if (!file.name.endsWith('.pdf')) {
          wx.showToast({ title: '仅支持 PDF 格式', icon: 'none' });
          return;
        }
        this._doUpload(file);
      },
      fail: () => {
        // 用户取消选择
      }
    });
  },

  /** 执行上传 */
  async _doUpload(file) {
    this.setData({
      uploading: true, uploadProgress: 15, uploadStatus: 'uploading',
      parseStage: 'uploading', parseProgress: 0, parseProgressText: '',
    });

    try {
      // 调用真实上传 API
      const result = await api.uploadTextbook({
        filePath: file.path || file.tempFilePath,
        textbookVersion: 'PEP',
        grade: '3',
        semester: '上',
      });
      this.setData({ uploadProgress: 60 });

      const uploadId = result.upload_id;
      // 进入解析阶段
      this.setData({ parseStage: 'parsing' });
      // 轮询解析状态
      const pollResult = await this._pollParseStatus(uploadId);
      this.setData({
        uploadProgress: 100, uploading: false, uploadStatus: 'done',
        parseStage: pollResult ? 'done' : 'parsing',
      });

      wx.showToast({ title: pollResult ? '解析完成' : '上传成功，解析中', icon: 'success' });
      // 刷新列表
      this._loadUploadedList();
      setTimeout(() => {
        this.setData({ uploadStatus: '', parseStage: '', parseProgressText: '' });
      }, 2000);
    } catch (err) {
      console.error('上传失败', err);
      this.setData({ uploading: false, uploadStatus: 'error', parseStage: 'error' });
      wx.showToast({ title: err.message || '上传失败，请重试', icon: 'none' });
    }
  },

  /** 轮询解析状态 — 展示解析页数进度 */
  _pollParseStatus(uploadId) {
    let finished = false;
    return new Promise((resolve) => {
      const timer = setInterval(async () => {
        try {
          const detail = await api.getTextbookUploadDetail(uploadId);
          const status = detail.parse_status;
          const totalPages = detail.total_pages || 0;
          const parsedPages = detail.parsed_pages || 0;
          // 计算解析进度百分比（60%–90% 区间）
          let parsePct = 60;
          if (totalPages > 0) {
            parsePct = 60 + Math.min(30, Math.round((parsedPages / totalPages) * 30));
          }
          const progressText = totalPages > 0
            ? `${parsedPages}/${totalPages} 页`
            : '解析中...';
          this.setData({
            uploadProgress: parsePct,
            parseProgress: parsePct,
            parseProgressText: progressText,
          });
          if (status === 2) {
            // 解析完成
            this.setData({ uploadProgress: 90, parseStage: 'done' });
            clearInterval(timer);
            finished = true;
            resolve(true);
          } else if (status === 3) {
            // 解析失败
            clearInterval(timer);
            finished = true;
            wx.showToast({ title: detail.error_msg || '解析失败', icon: 'none' });
            resolve(false);
          }
        } catch (e) {
          // 轮询出错继续
        }
      }, 2000);
      // 120秒超时（大 PDF 解析可能较慢）
      setTimeout(() => {
        if (!finished) {
          clearInterval(timer);
          resolve(false);
        }
      }, 120000);
    });
  },

  /** 删除已上传教材 */
  onDeleteUpload(e) {
    const { id, name } = e.currentTarget.dataset;
    wx.showModal({
      title: '确认删除',
      content: `确定删除「${name || '该教材'}」吗？关联的解析数据也将被清除。`,
      success: (res) => {
        if (res.confirm) {
          api.deleteTextbookUpload(id).then(() => {
            const list = this.data.uploadedTextbooks.filter(item => item.id !== id);
            this.setData({ uploadedTextbooks: list });
            wx.showToast({ title: '已删除', icon: 'success' });
          }).catch(err => {
            wx.showToast({ title: err.message || '删除失败', icon: 'none' });
          });
        }
      }
    });
  },

  /** 点击已上传教材项：已完成 → 打开批量操作菜单，未完成 → 查看状态 */
  onTapUploadItem(e) {
    const item = e.currentTarget.dataset.item;
    if (!item) return;
    if (item.parse_status === 2) {
      // 解析完成 → 打开批量操作菜单
      this.setData({
        showBatchMenu: true,
        batchItem: item,
      });
    } else {
      // 未完成 → 查看状态详情
      this._checkUploadStatus(item);
    }
  },

  /** 查看上传状态详情 */
  async _checkUploadStatus(item) {
    if (!item || !item.id) return;
    wx.showLoading({ title: '查询中...' });
    try {
      const detail = await api.getTextbookUploadDetail(item.id);
      wx.hideLoading();
      if (detail.parse_status === 2) {
        // 已变为完成 → 刷新列表
        this._loadUploadedList();
        wx.showToast({ title: '解析已完成', icon: 'success' });
      } else if (detail.parse_status === 3) {
        wx.showToast({ title: detail.error_msg || '解析失败', icon: 'none' });
      } else if (detail.parse_status === 1) {
        wx.showToast({ title: '正在解析中，请稍候...', icon: 'none' });
      } else {
        wx.showToast({ title: '等待解析中', icon: 'none' });
      }
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '查询失败', icon: 'none' });
    }
  },

  /** 关闭批量操作菜单 */
  onCloseBatchMenu() {
    this.setData({ showBatchMenu: false, batchItem: null });
  },

  /** 批量操作：查看阅读（跳转到阅读器） */
  async onBatchView() {
    const item = this.data.batchItem;
    if (!item || !item.id) return;
    this.onCloseBatchMenu();
    wx.showLoading({ title: '查询中...' });
    try {
      const detail = await api.getTextbookUploadDetail(item.id);
      if (detail.parse_status !== 2) {
        wx.hideLoading();
        wx.showToast({ title: '教材未解析完成', icon: 'none' });
        return;
      }
      let firstUnit = '1';
      try {
        const units = await api.getTextbookUnits(detail.textbook_version, detail.grade, detail.semester);
        if (units && units.length > 0) {
          firstUnit = units[0].unit_number;
        }
      } catch (_) {}
      wx.hideLoading();
      wx.navigateTo({
        url: `/pages/textbook/reader/index?version=${detail.textbook_version}&grade=${detail.grade}&semester=${detail.semester}&unit=${firstUnit}&upload_id=${item.id}`,
      });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '查询失败', icon: 'none' });
    }
  },

  /** 批量操作：删除教材 */
  onBatchDelete() {
    const item = this.data.batchItem;
    if (!item || !item.id) return;
    this.onCloseBatchMenu();
    wx.showModal({
      title: '确认删除',
      content: `确定删除「${item.name || '该教材'}」吗？关联的解析数据也将被清除。`,
      success: (res) => {
        if (res.confirm) {
          api.deleteTextbookUpload(item.id).then(() => {
            const list = this.data.uploadedTextbooks.filter(i => i.id !== item.id);
            this.setData({ uploadedTextbooks: list });
            wx.showToast({ title: '已删除', icon: 'success' });
          }).catch(err => {
            wx.showToast({ title: err.message || '删除失败', icon: 'none' });
          });
        }
      }
    });
  },

  /** 批量操作：合成音频 */
  onBatchTTS() {
    const item = this.data.batchItem;
    if (!item || !item.id) return;
    this.onCloseBatchMenu();

    this.setData({
      batchProcessing: true,
      batchProgressTitle: '音频合成中...',
      batchProgressText: '正在逐页合成 TTS 音频...',
      batchProgressPct: 10,
    });

    api.batchTextbookTTS(item.id)
      .then(res => {
        const total = res.total || 0;
        const succeeded = res.succeeded || 0;
        const failed = res.failed || 0;
        this.setData({
          batchProcessing: false,
          batchProgressPct: 100,
        });
        wx.showToast({
          title: `音频合成完成: ${succeeded}/${total} 页成功`,
          icon: 'none',
          duration: 3000,
        });
        this._loadUploadedList();
      })
      .catch(err => {
        this.setData({ batchProcessing: false });
        wx.showToast({ title: err.message || '批量合成失败', icon: 'none' });
      });
  },

  /** 批量操作：教材动态化（直接触发 AI 微动图生成，内置场景分析） */
  onBatchAnimation() {
    const item = this.data.batchItem;
    if (!item || !item.id) return;
    this.onCloseBatchMenu();

    this.setData({
      batchProcessing: true,
      batchProgressTitle: '教材动态化中...',
      batchProgressText: '正在生成角色级微动图（后台异步处理）...',
      batchProgressPct: 30,
    });

    // AnimationService.create_animation_task 已内置 AI 场景分析+角色动画+背景微动
    api.batchTextbookAnimation(item.id)
      .then(res => {
        const total = res.total || 0;
        const fired = res.fired || 0;
        this.setData({
          batchProcessing: false,
          batchProgressPct: 100,
          showBatchMenu: false,
        });
        wx.showToast({
          title: `已触发 ${fired}/${total} 页动画生成（后台异步处理）`,
          icon: 'none',
          duration: 3000,
        });
        this._loadUploadedList();
      })
      .catch(err => {
        this.setData({ batchProcessing: false });
        wx.showToast({ title: err.message || '动态化处理失败', icon: 'none' });
      });
  },
});
