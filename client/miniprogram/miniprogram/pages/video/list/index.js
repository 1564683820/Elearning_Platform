// 我的视频列表页
const api = require('../../../utils/api.js');

Page({
  data: {
    videos: [],
    loading: true,
    page: 1,
    pageSize: 20,
    hasMore: false,
    filterStatus: '', // ''/completed/processing
  },

  onLoad() {
    this.loadVideos();
  },

  onPullDownRefresh() {
    this.setData({ page: 1, videos: [], loading: true });
    this.loadVideos().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  async loadVideos() {
    try {
      const data = await api.getVideoList({
        status: this.data.filterStatus || undefined,
        page: this.data.page,
        pageSize: this.data.pageSize,
      });
      const items = data.items || data.list || data || [];
      this.setData({
        videos: this.data.page === 1 ? items : this.data.videos.concat(items),
        loading: false,
        hasMore: (data.total || items.length) > this.data.page * this.data.pageSize,
      });
    } catch (err) {
      console.error('加载视频列表失败', err);
      this.setData({ loading: false });
    }
  },

  // 筛选
  onFilterAll() { this.setData({ filterStatus: '', page: 1, videos: [], loading: true }); this.loadVideos(); },
  onFilterCompleted() { this.setData({ filterStatus: 'completed', page: 1, videos: [], loading: true }); this.loadVideos(); },
  onFilterProcessing() { this.setData({ filterStatus: 'processing', page: 1, videos: [], loading: true }); this.loadVideos(); },

  // 加载更多
  onLoadMore() {
    if (!this.data.hasMore || this.data.loading) return;
    this.setData({ page: this.data.page + 1, loading: true });
    this.loadVideos();
  },

  // 点击视频
  onVideoTap(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/video/watch/index?videoId=${id}`,
    });
  },

  // 创建视频
  onGoCreate() {
    wx.navigateTo({
      url: '/pages/video/create/index',
    });
  },

  formatDuration(sec) {
    if (!sec) return '';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  },

  formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const month = d.getMonth() + 1;
    const day = d.getDate();
    return `${month}月${day}日`;
  },
});
