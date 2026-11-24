// 视频观看页 — 播放器 + 角色信息 + 字幕 + 收藏分享
const api = require('../../../utils/api.js');

Page({
  data: {
    videoId: null,
    videoInfo: null,
    loading: true,
    scriptIndex: -1,
    danmuList: [],
    _pollTimer: null,
  },

  onLoad(options) {
    if (options.videoId) {
      this.setData({ videoId: String(options.videoId) });
      this.loadVideo(String(options.videoId));
    } else {
      this.setData({ loading: false });
    }
  },

  async loadVideo(videoId) {
    try {
      const data = await api.getVideoDetail(videoId);
      this.setData({
        videoInfo: data,
        loading: false,
      });
      // 如果生成中，轮询状态
      if (data.status === 'pending' || data.status === 'processing') {
        this.startPolling(videoId);
      }
    } catch (err) {
      console.error('加载视频失败', err);
      this.setData({ loading: false });
    }
  },

  // 轮询视频生成状态
  startPolling(videoId) {
    this._pollTimer = setInterval(async () => {
      try {
        const status = await api.getVideoTaskStatus(videoId);
        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(this._pollTimer);
          this._pollTimer = null;
          // 重新加载完整信息
          this.loadVideo(videoId);
        }
      } catch (err) {
        console.error('轮询状态失败', err);
        clearInterval(this._pollTimer);
        this._pollTimer = null;
      }
    }, 3000);
  },

  // 播放事件
  onPlay() {
    api.logLearningBehavior('video_play', { video_id: this.data.videoId });
  },

  onPause() {
    api.logLearningBehavior('video_pause', { video_id: this.data.videoId });
  },

  onVideoError() {
    wx.showToast({ title: '视频加载失败', icon: 'none' });
  },

  // 收藏
  async onFavorite() {
    const videoId = this.data.videoId;
    try {
      const result = await api.toggleVideoFavorite(videoId);
      const videoInfo = { ...this.data.videoInfo };
      videoInfo.favorite_count = result.favorited ? 1 : 0;
      this.setData({ videoInfo });
      wx.showToast({
        title: result.favorited ? '已收藏' : '已取消收藏',
        icon: 'success',
      });
    } catch (err) {
      console.error('收藏操作失败', err);
    }
  },

  // 分享
  onShare() {
    wx.showShareMenu({
      withShareTicket: true,
    });
  },

  // 通过 onShareAppMessage 分享
  onShareAppMessage() {
    const info = this.data.videoInfo || {};
    return {
      title: info.title || 'AI 教材演绎视频',
      path: `/pages/video/watch/index?videoId=${this.data.videoId}`,
      imageUrl: info.thumbnail_url || '',
    };
  },

  // 点击分镜跳转（定位到对应时间）
  onSceneTap(e) {
    const index = e.currentTarget.dataset.index;
    this.setData({ scriptIndex: index });
    // 如果有 video context，可以 seek 到对应时间
    const scene = this.data.videoInfo?.script_json?.scenes[index];
    if (scene && scene.duration_sec && this.data.videoInfo.status === 'completed') {
      // 计算起始时间：前 n 段时长之和
      let seekTime = 0;
      const scenes = this.data.videoInfo.script_json.scenes;
      for (let i = 0; i < index; i++) {
        seekTime += scenes[i].duration_sec || 3;
      }
      const videoCtx = wx.createVideoContext('video-player');
      videoCtx.seek(seekTime);
    }
  },

  // 重新播放
  onReplay() {
    const videoCtx = wx.createVideoContext('video-player');
    videoCtx.seek(0);
    videoCtx.play();
  },

  formatDuration(sec) {
    if (!sec) return '';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  },

  onUnload() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
    }
  },
});
