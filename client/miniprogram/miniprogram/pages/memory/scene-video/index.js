// 情景记忆视频播放页 — 展示视频+关联单词
const api = require('../../../utils/api.js');

Page({
  data: {
    videoUrl: '',          // 视频地址
    passage: '',           // 关联文段
    words: [],             // 关联单词列表
    createdAt: '',         // 创建时间
    status: '',            // 状态: completed/processing/failed
    statusText: '',        // 状态中文
    duration: '',          // 时长
    loading: true,
    isBookmarked: false,
    scenarioId: null        // 情景ID
  },

  onLoad(options) {
    // 接收上个页面传过来的情景ID
    if (options.scenarioId) {
      this.setData({ scenarioId: options.scenarioId });
      this.loadVideoInfo(options.scenarioId);
    } else {
      this.setData({ loading: false });
    }
  },

  // 加载视频信息
  async loadVideoInfo(scenarioId) {
    try {
      const data = await api.getVideoStatus(scenarioId);
      this.setData({
        videoUrl: data.video_url || '',
        passage: data.passage || '',
        words: data.words || [],
        createdAt: data.created_at || '',
        status: data.status || 'processing',
        statusText: this.getStatusText(data.status),
        duration: data.duration || '',
        loading: false
      });

      // 如果视频还在处理中，轮询状态
      if (data.status === 'processing') {
        this.pollStatus(scenarioId);
      }
    } catch (err) {
      console.error('加载视频信息失败', err);
      this.setData({ loading: false });
    }
  },

  // 轮询视频生成状态
  pollStatus(scenarioId) {
    this._pollTimer = setInterval(async () => {
      try {
        const data = await api.getVideoStatus(scenarioId);
        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(this._pollTimer);
          this.setData({
            videoUrl: data.video_url || '',
            status: data.status,
            statusText: this.getStatusText(data.status),
            duration: data.duration || ''
          });
        }
      } catch (err) {
        console.error('轮询视频状态失败', err);
        clearInterval(this._pollTimer);
      }
    }, 3000);
  },

  // 状态中文映射
  getStatusText(status) {
    const map = {
      completed: '已完成',
      processing: '生成中...',
      failed: '生成失败',
      pending: '等待中'
    };
    return map[status] || status;
  },

  // 开始播放
  onPlay() {
    // 可在此处记录观看行为
  },

  // 暂停播放
  onPause() {
    // 可在此处记录暂停行为
  },

  // 视频播放出错
  onVideoError() {
    wx.showToast({ title: '视频加载失败', icon: 'none' });
  },

  // 收藏/取消收藏
  async onBookmark() {
    if (this.data.isBookmarked) {
      try {
        await api.removeFavorite('scenario_video', this.data.scenarioId);
        this.setData({ isBookmarked: false });
        wx.showToast({ title: '已取消收藏', icon: 'none' });
      } catch (err) {
        console.error('取消收藏失败', err);
      }
    } else {
      try {
        await api.addFavorite({
          target_type: 'scenario_video',
          target_id: this.data.scenarioId
        });
        this.setData({ isBookmarked: true });
        wx.showToast({ title: '已收藏', icon: 'success' });
      } catch (err) {
        console.error('收藏失败', err);
      }
    }
  },

  // 点击单词
  onWordTap(e) {
    const word = e.currentTarget.dataset.word;
    wx.navigateTo({
      url: `/pages/memory/word/index?word=${encodeURIComponent(word)}`
    });
  },

  onUnload() {
    // 页面卸载时清除定时器
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
    }
  }
});