// 教材点读阅读页 — 翻页 / 点击句子播放音频 / 单词卡片
const app = getApp();
const api = require('../../../utils/api');
const animCache = require('../../../utils/animation-cache');

// 后端服务器根地址（用于拼接媒体文件完整URL）
const SERVER_ROOT = 'http://47.106.80.147:18000';

Page({
  data: {
    loading: false,
    pageTitle: '',
    currentPageNum: 0,
    swiperIndex: 0,
    pageItems: [],
    pageList: [],
    sidebarOpen: false,
    playbackActive: false,
    currentAudioUrl: '',
    currentSentences: [],
    currentAudioTitle: '',
    // 动画联动
    currentCharAnimUrl: '',       // 当前说话角色的动画 URL
    currentSpeaker: '',           // 当前说话角色名
    currentBgAnimUrl: '',         // 当前页背景微动 URL
    wordPopup: { show: false, word: '', phonetic: '', meanings: [], translation: '', favorited: false },
    statusBarHeight: 20,
  },

  _params: null,
  _pageCache: {},

  onLoad(params) {
    this._params = params;
    const { version, grade, semester, unit } = params;
    try {
      const win = wx.getWindowInfo();
      this.setData({ statusBarHeight: win.statusBarHeight || 20 });
    } catch (_) {
      try {
        const appInfo = wx.getAppBaseInfo();
        this.setData({ statusBarHeight: appInfo.statusBarHeight || 20 });
      } catch (_2) {}
    }
    this.setData({ pageTitle: `U${unit} · ${grade}年级` });
    this._loadPageList(version, grade, semester, unit);
  },

  // ========== 数据加载 ==========

  _loadPageList(version, grade, semester, unit) {
    this.setData({ loading: true });
    api.getTextbookPages(version, grade, semester, unit)
      .then(pages => {
        const pageList = (pages || []).map(p => ({
          id: p.id,
          page_number: p.page_number || p,
        }));
        this.setData({ pageList });
        if (pageList.length > 0) {
          this._loadAllPages(pageList);
        } else {
          this.setData({ loading: false });
        }
      })
      .catch(err => {
        console.error('[reader] 加载页面列表失败:', err);
        this.setData({ loading: false });
      });
  },

  _loadAllPages(pageList) {
    const promises = pageList.map(p =>
      api.getTextbookPageDetail({ pageId: p.id })
        .then(data => { this._pageCache[p.id] = data; })
        .catch(err => {
          console.error('[reader] 加载页面详情失败 pageId=', p.id, err);
          this._pageCache[p.id] = { page_number: p.page_number, sentences: [], words: [] };
        })
    );

    Promise.all(promises).then(async () => {
      const items = pageList.map(p =>
        this._formatPageData(this._pageCache[p.id], p.page_number)
      );

      // 收集所有需要缓存的动画 URL 并预下载到本地（URL 已通过 _formatPageData 转为完整路径）
      const allUrls = [];
      items.forEach(item => {
        allUrls.push(...animCache.extractAnimUrls(item));
      });
      const uniqueUrls = [...new Set(allUrls)].filter(Boolean);
      if (uniqueUrls.length > 0) {
        console.log('[reader] 预下载动画文件:', uniqueUrls.length, '个');
        const result = await animCache.preloadUrls(uniqueUrls);
        console.log('[reader] 预下载结果: 成功', result.success, '失败', result.fail);
      }

      // 将已缓存的 URL 替换为本地路径
      items.forEach(item => animCache.applyCacheToPage(item));

      this.setData({
        pageItems: items,
        currentPageNum: pageList[0] ? pageList[0].page_number : 0,
        swiperIndex: 0,
        loading: false,
      });
      // 初始加载后自动显示当前页背景动图
      if (items.length > 0) {
        this._autoShowCurrentPageAnimation(items[0]);
      }
    });
  },

  /** 将API返回的原始数据格式化为页面展示数据 */
  _formatPageData(raw, pageNum) {
    const rawText = raw.text_content || '';
    const rawSentences = raw.sentences || raw.sentences_json || [];

    let sentences;
    if (Array.isArray(rawSentences) && rawSentences.length > 0) {
      sentences = rawSentences.map(s => {
        // 统一格式：确保每个 sentence 对象包含 speaker 和 animation_url
        const text = s.text || s.en || '';
        const cn = s.cn || '';
        const audio_url = s.audio_url || '';
        return { text, cn, audio_url, highlight: false, speaker: s.speaker || '', animation_url: this._toFullUrl(s.animation_url || '') };
      });
    } else if (rawText) {
      // 无结构化句子数据，从原始文本按标点分割
      sentences = this._textToSentences(rawText);
    } else {
      sentences = [];
    }

    // 兜底：如果还是空的，把原始文本当作一句
    if (sentences.length === 0 && rawText) {
      sentences = [{ text: rawText, cn: '', audio_url: '', highlight: false }];
    }

      // character_animations 中的 URL 也转为完整路径
      const charAnims = raw.character_animations || {};
      const charAnimsFull = {};
      for (const [key, val] of Object.entries(charAnims)) {
        charAnimsFull[key] = this._toFullUrl(val || '');
      }
      return {
        pageId: raw.id || pageNum,
        page_number: raw.page_number || pageNum,
        image_url: raw.image_url || raw.image || '',
        animation_url: this._toFullUrl(raw.animation_url || raw.animation || ''),
        background_anim_url: this._toFullUrl(raw.background_anim_url || ''),
        audio_url: raw.audio_url || raw.audio || '',
        sentences,
        words: raw.words || raw.words_json || [],
        character_animations: charAnimsFull,
        animationPlaying: false,
        showAnimation: false,
      };
  },

  /** 按标点符号将文本拆分为句子数组 */
  _textToSentences(text) {
    if (!text) return [];
    const parts = text.match(/[^.!?]+[.!?]+/g);
    if (!parts || parts.length === 0) {
      return text.trim() ? [{ text: text.trim(), cn: '', audio_url: '', highlight: false }] : [];
    }
    const result = [];
    let lastEnd = 0;
    for (const p of parts) {
      const idx = text.indexOf(p, lastEnd);
      if (idx >= 0) lastEnd = idx + p.length;
      const trimmed = p.trim();
      if (trimmed) result.push({ text: trimmed, cn: '', audio_url: '', highlight: false });
    }
    // 末尾残余文本
    if (lastEnd < text.length) {
      const tail = text.slice(lastEnd).trim();
      if (tail) result.push({ text: tail, cn: '', audio_url: '', highlight: false });
    }
    return result;
  },

  /** 将相对路径转为完整 HTTP URL（后端 static files 挂载在 /uploads 下） */
  _toFullUrl(path) {
    if (!path) return '';
    if (path.startsWith('http://') || path.startsWith('https://')) return path;
    // 云存储 fileID 直接返回
    if (path.startsWith('cloud://')) return path;
    return SERVER_ROOT + (path.startsWith('/') ? path : '/' + path);
  },

  // ========== 导航 ==========

  goBack() { wx.navigateBack(); },

  onSwiperChange(e) {
    const idx = e.detail.current;
    const item = this.data.pageItems[idx];
    if (item) {
      this.setData({ currentPageNum: item.page_number });
      this._stopAllPlayback();
      this._autoShowCurrentPageAnimation(item);
    }
  },

  onPrevPage() {
    if (this.data.swiperIndex <= 0) return;
    const newIdx = this.data.swiperIndex - 1;
    const item = this.data.pageItems[newIdx];
    if (item) {
      this.setData({ swiperIndex: newIdx, currentPageNum: item.page_number });
      this._stopAllPlayback();
      this._autoShowCurrentPageAnimation(item);
    }
  },

  onNextPage() {
    if (this.data.swiperIndex >= this.data.pageItems.length - 1) return;
    const newIdx = this.data.swiperIndex + 1;
    const item = this.data.pageItems[newIdx];
    if (item) {
      this.setData({ swiperIndex: newIdx, currentPageNum: item.page_number });
      this._stopAllPlayback();
      this._autoShowCurrentPageAnimation(item);
    }
  },

  // ========== 侧边栏 ==========

  onOpenSidebar() { this.setData({ sidebarOpen: true }); },
  onCloseSidebar() { this.setData({ sidebarOpen: false }); },

  goToPage(e) {
    const pageNum = Number(e.currentTarget.dataset.page);
    this.setData({ sidebarOpen: false });
    const idx = this.data.pageItems.findIndex(p => p.page_number === pageNum);
    if (idx >= 0) {
      const item = this.data.pageItems[idx];
      this.setData({ swiperIndex: idx, currentPageNum: pageNum });
      this._stopAllPlayback();
      this._autoShowCurrentPageAnimation(item);
    }
  },

  // ========== 点击插图 ==========

  onTapImage(e) {
    const pageId = e.currentTarget.dataset.pageid;
    const items = this.data.pageItems;
    const idx = items.findIndex(i => i.pageId === pageId);
    if (idx === -1) return;
    const key = `pageItems[${idx}].animationPlaying`;
    this.setData({ [key]: true, [`pageItems[${idx}].showAnimation`]: true });
    setTimeout(() => this.setData({ [key]: false }), 3000);
  },

  // ========== 点击句子 — 3 级音频优先级 ==========

  onTapSentence(e) {
    const { pageid: pageId, sidx } = e.currentTarget.dataset;
    console.log('[reader] 点击句子 pageId=', pageId, 'sidx=', sidx);

    const items = this.data.pageItems;
    const pIdx = items.findIndex(i => i.pageId === pageId);
    if (pIdx === -1) {
      console.warn('[reader] 未找到页面 pageId=', pageId);
      return;
    }

    const sentences = items[pIdx].sentences || [];
    if (!sentences[sidx]) {
      console.warn('[reader] 句子索引越界 sidx=', sidx, 'length=', sentences.length);
      return;
    }

    // 高亮当前句
    sentences.forEach((s, i) => { s.highlight = i === sidx; });
    this.setData({ [`pageItems[${pIdx}].sentences`]: sentences });

    const pageTitle = `第${items[pIdx].page_number}页`;

    // 第 1 级：句子自身的 audio_url（已缓存/已生成过）
    const sentenceAudio = sentences[sidx].audio_url;
    if (sentenceAudio) {
      console.log('[reader] 第1级: 句子级音频', sentenceAudio);
      this._playAudio(this._toFullUrl(sentenceAudio), sentences, pageTitle);
      return;
    }

    // 第 2 级：整页合并音频
    const pageItem = this._pageCache[pageId] || {};
    const pageAudio = pageItem.audio_url || items[pIdx].audio_url;
    if (pageAudio) {
      console.log('[reader] 第2级: 整页音频', pageAudio);
      this._playAudio(this._toFullUrl(pageAudio), sentences, pageTitle);
      return;
    }

    // 第 3 级：即时 TTS 合成
    console.log('[reader] 第3级: 请求 TTS 合成 pageId=', pageId, 'sidx=', sidx);
    wx.showLoading({ title: '生成音频中...', mask: true });

    api.requestTTS(pageId, sidx)
      .then(res => {
        wx.hideLoading();
        console.log('[reader] TTS 返回:', res);
        const audioUrl = res ? res.audio_url : '';
        if (audioUrl) {
          // 缓存到本地数据，下次直接走第 1 级
          sentences[sidx].audio_url = audioUrl;
          items[pIdx].audio_url = items[pIdx].audio_url || audioUrl;
          const fullUrl = this._toFullUrl(audioUrl);
          console.log('[reader] 播放 TTS 音频:', fullUrl);
          this._playAudio(fullUrl, sentences, pageTitle);
        } else {
          console.warn('[reader] TTS 返回无 audio_url');
          wx.showToast({ title: '音频生成失败', icon: 'none' });
        }
      })
      .catch(err => {
        wx.hideLoading();
        console.error('[reader] TTS 请求失败:', err);
        wx.showToast({ title: '音频生成失败，请重试', icon: 'none' });
      });
  },

  // ========== 全文朗读 ==========

  onTogglePlayback() {
    if (this.data.playbackActive) {
      this._stopAllPlayback();
      return;
    }
    const items = this.data.pageItems;
    const cur = items.find(i => i.page_number === this.data.currentPageNum);
    if (!cur) return;
    const pageItem = this._pageCache[cur.pageId] || {};
    const audioUrl = pageItem.audio_url || cur.audio_url;
    if (audioUrl) {
      this._playAudio(this._toFullUrl(audioUrl), cur.sentences, `第${cur.page_number}页`);
    } else {
      wx.showToast({ title: '暂无可朗读音频', icon: 'none' });
    }
  },

  _stopAllPlayback() {
    this.setData({
      playbackActive: false,
      currentAudioUrl: '',
      currentCharAnimUrl: '',
      currentSpeaker: '',
      currentBgAnimUrl: '',
    });
    const audio = this.selectComponent('#textbookAudio');
    if (audio) audio.onClose();
  },

  /** 自动显示当前页的背景动图 */
  _autoShowCurrentPageAnimation(item) {
    // 背景动图通过 WXML 中 index === swiperIndex 自动控制显示
    const bgUrl = item.background_anim_url || '';
    const pageUrl = item.animation_url || '';
    const sentAnimCount = (item.sentences || []).filter(s => s && s.animation_url).length;
    console.log('[reader] 当前页动画数据: pageId=', item.pageId,
                'swiperIndex=', this.data.swiperIndex,
                'image_url=', (item.image_url || '').substring(0, 40),
                'background_anim_url=', bgUrl.substring(0, 50) || '(空)',
                'animation_url=', pageUrl.substring(0, 50) || '(空)',
                'sentences有动画=', sentAnimCount, '/', (item.sentences || []).length);
  },

  // ========== 动画联动 — 音频播放时切换角色动画 ==========

  /** audio 组件句子切换事件处理：更新角色微动图和背景微动 */
  onAudioSentenceChange(e) {
    const { speaker, animationUrl, index } = e.detail;
    if (index < 0) {
      // 无匹配句子或播放结束 → 关闭角色动画
      this.setData({ currentCharAnimUrl: '', currentSpeaker: '' });
      return;
    }
    // 优先使用句子级 animation_url，否则查 character_animations 映射
    if (animationUrl) {
      this.setData({ currentCharAnimUrl: animCache.getLocalPathSync(this._toFullUrl(animationUrl)), currentSpeaker: speaker });
    } else {
      // 从当前页的 character_animations 映射中查找（已通过 applyCacheToPage 替换为本地路径）
      const currentItem = this.data.pageItems[this.data.swiperIndex];
      if (currentItem && currentItem.character_animations) {
        const charUrl = currentItem.character_animations[speaker] || '';
        this.setData({
          currentCharAnimUrl: charUrl,
          currentSpeaker: speaker,
        });
      }
    }
  },

  _playAudio(url, sentences, title) {
    if (!url || !(url.startsWith('http') || url.startsWith('cloud://'))) {
      console.warn('[reader] 无效音频URL，忽略:', url);
      return;
    }
    console.log('[reader] _playAudio url=', url);
    // 获取当前页的背景微动 URL（已通过 applyCacheToPage 替换为本地路径）
    const currentItem = this.data.pageItems[this.data.swiperIndex];
    const bgAnimUrl = (currentItem && currentItem.background_anim_url) || '';
    this.setData({
      currentAudioUrl: url,
      currentSentences: sentences || [],
      currentAudioTitle: title || '课文朗读',
      playbackActive: true,
      currentBgAnimUrl: bgAnimUrl,
      currentCharAnimUrl: '',
      currentSpeaker: '',
    });
    // 等待 setData 生效后触发组件播放
    setTimeout(() => {
      const audio = this.selectComponent('#textbookAudio');
      if (audio) audio.playAudio();
    }, 150);
  },

  // ========== 单词弹窗 ==========

  onTapWord(e) {
    const word = e.currentTarget.dataset.word;
    if (!word) return;
    this.setData({ loading: true });
    api.getTextbookWordDetail(word)
      .then(detail => {
        this.setData({
          wordPopup: {
            show: true, word,
            phonetic: detail.phonetic || `/${word}/`,
            meanings: detail.meanings || (detail.translation ? [{ pos: '', definition: detail.translation }] : [{ pos: '', definition: '暂未收录' }]),
            translation: detail.translation || '',
            favorited: detail.favorited || false,
          },
          loading: false,
        });
      })
      .catch(() => {
        this.setData({
          wordPopup: { show: true, word, phonetic: '', meanings: [{ pos: '', definition: '暂未收录' }], translation: '', favorited: false },
          loading: false,
        });
      });
  },

  hideWordPopup() { this.setData({ 'wordPopup.show': false }); },

  onPopupAddFavorite(e) {
    const word = e.currentTarget.dataset.word;
    wx.showToast({ title: '已收藏', icon: 'success' });
    api.addFavorite({ type: 'textbook_word', refId: word, data: { word } }).catch(() => {});
  },

  onPopupPlayTTS(e) {
    const word = e.currentTarget.dataset.word;
    wx.playVoice({ src: `https://dict.youdao.com/dictvoice?audio=${word}&type=0` });
  },
});
