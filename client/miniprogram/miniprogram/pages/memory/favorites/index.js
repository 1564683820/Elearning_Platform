const api = require('../../../utils/api.js');

// 收藏目标类型：1=单词, 2=文章, 3=情景文段, 4=歌曲
const TYPE_WORD = 1;
const TYPE_ARTICLE = 2;
const TYPE_SEGMENT = 3;
const TYPE_SONG = 4;

Page({
  data: {
    tabs: ['单词', '文章', '文段', '歌曲'],
    activeTab: 0,
    favorites: { words: [], articles: [], passages: [], songs: [] },
    loading: true,

    // 编辑模式
    editing: false,
    selectedIds: [],

    // 文段详情弹窗
    showPassageModal: false,
    passageDetail: { content: '', passage_type: '' }
  },

  onLoad() {
    this.loadFavorites();
  },

  onShow() {
    this.loadFavorites();
  },

  /* 一次性加载全部收藏，前端按 target_type 过滤 */
  async loadFavorites() {
    this.setData({ loading: true });
    try {
      const result = await api.getFavorites('');
      const allFavs = Array.isArray(result) ? result : (result.items || []);

      const toItem = f => ({
        id: f.id || f._id,
        target_type: f.target_type || 0,
        target_type_name: f.target_type_name || '',
        target_id: f.target_id || 0,
        word: f.word || '',
        phonetic: f.phonetic || '',
        meaning: f.meaning || '',
        content: f.content || '',
        passage_type: f.passage_type || '',
        created_at: f.created_at || ''
      });

      this.setData({
        favorites: {
          words: allFavs.filter(f => f.target_type === TYPE_WORD).map(toItem),
          articles: allFavs.filter(f => f.target_type === TYPE_ARTICLE).map(toItem),
          passages: allFavs.filter(f => f.target_type === TYPE_SEGMENT).map(toItem),
          songs: allFavs.filter(f => f.target_type === TYPE_SONG).map(toItem)
        },
        loading: false,
        selectedIds: []
      });
    } catch (err) {
      console.error('加载收藏失败', err);
      this.setData({ loading: false });
    }
  },

  /* Tab 切换：只切 activeTab，不重新请求 */
  onTabChange(e) {
    this.setData({ activeTab: e.currentTarget.dataset.index });
  },

  /* ==== 编辑模式 ==== */

  /* 切换编辑模式 */
  onEditToggle() {
    this.setData({
      editing: !this.data.editing,
      selectedIds: []
    });
  },

  /* 选中/取消选中收藏项 */
  onSelectItem(e) {
    const id = e.currentTarget.dataset.id;
    let selectedIds = [...this.data.selectedIds];
    const idx = selectedIds.indexOf(id);
    if (idx > -1) {
      selectedIds.splice(idx, 1);
    } else {
      selectedIds.push(id);
    }
    this.setData({ selectedIds });
  },

  /* 全选/取消全选当前 tab */
  onSelectAll() {
    const key = ['words', 'articles', 'passages', 'songs'][this.data.activeTab];
    const items = this.data.favorites[key] || [];
    if (this.data.selectedIds.length === items.length) {
      this.setData({ selectedIds: [] });
    } else {
      this.setData({ selectedIds: items.map(i => i.id) });
    }
  },

  /* 批量删除选中项 */
  async onDeleteSelected() {
    const ids = this.data.selectedIds;
    if (ids.length === 0) {
      wx.showToast({ title: '请选择要删除的收藏', icon: 'none' });
      return;
    }
    try {
      await api.batchRemoveFavorites(ids);
      wx.showToast({ title: `已删除 ${ids.length} 条收藏`, icon: 'none' });
      this.setData({ editing: false, selectedIds: [] });
      this.loadFavorites();
    } catch (err) {
      console.error('批量删除失败', err);
      wx.showToast({ title: '删除失败', icon: 'none' });
    }
  },

  /* ==== 单个删除（非编辑模式） ==== */

  async onRemoveFavorite(e) {
    if (this.data.editing) return;
    const dataset = e.currentTarget.dataset;
    const { targetType, targetId } = dataset;
    const typeNames = { '1': 'word', '2': 'article', '3': 'segment', '4': 'song' };
    const typeName = typeNames[targetType];
    if (!typeName || !targetId) return;

    try {
      await api.removeFavorite(typeName, targetId);
      wx.showToast({ title: '已取消收藏', icon: 'none' });
      this.loadFavorites();
    } catch (err) {
      console.error('取消收藏失败', err);
    }
  },

  /* 解析 **word** 标记为加粗 segments */
  parseBoldSegments(text) {
    if (!text) return [];
    const segments = [];
    const regex = /\*\*([^*]+)\*\*/g;
    let lastIdx = 0;
    let match;
    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIdx) {
        segments.push({ text: text.slice(lastIdx, match.index), bold: false });
      }
      segments.push({ text: match[1], bold: true });
      lastIdx = match.index + match[0].length;
    }
    if (lastIdx < text.length) {
      segments.push({ text: text.slice(lastIdx), bold: false });
    }
    return segments.length > 0 ? segments : [{ text, bold: false }];
  },

  /* ==== 文段详情弹窗 ==== */

  onViewPassage(e) {
    if (this.data.editing) return;
    const idx = e.currentTarget.dataset.index;
    const passage = this.data.favorites.passages[idx];
    if (!passage) return;
    const segments = this.parseBoldSegments(passage.content);
    this.setData({
      showPassageModal: true,
      passageDetail: {
        content: passage.content,
        passage_type: passage.passage_type,
        segments: segments
      }
    });
  },

  onCloseModal() {
    this.setData({
      showPassageModal: false,
      passageDetail: { content: '', passage_type: '', segments: [] }
    });
  },

  /* 阻止弹窗点击穿透到遮罩层 */
  onStopPropagation() {},

  /* 点击单词跳转 */
  onItemTap(e) {
    if (this.data.editing) return;
    const word = e.currentTarget.dataset.word;
    if (word) {
      wx.navigateTo({ url: `/pages/memory/word/index?word=${word}` });
    }
  }
});
