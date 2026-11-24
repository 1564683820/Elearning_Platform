const api = require('../../../utils/api.js');

// 考试标签显示颜色映射
const TAG_COLORS = {
  'cet4': '#4F8EF7',
  'cet6': '#9B59B6',
  'zk': '#E67E22',
  'gk': '#E74C3C',
  'ky': '#1ABC9C',
  'toefl': '#2ECC71',
  'ielts': '#3498DB',
  'gre': '#E91E63',
  'pets': '#F39C12',
  'bec': '#34495E',
};

Page({
  data: {
    // === Tab切换 ===
    activeTab: 0, // 0=单词记忆, 1=情景记忆, 2=收藏
    menuItems: ['单词记忆', '情景记忆', '收藏'],
    showSidebar: false,
    showWordList: false,

    // === 排序 ===
    sortOptions: ['重要度', '升序(A-Z)', '随机'],
    sortValues: ['importance', 'asc', 'random'],
    currentSort: 'importance', // 对应 sortValues
    currentSortLabel: '重要度',
    drawerSortOptions: [
      { label: '重要度', value: 'importance' },
      { label: 'A-Z', value: 'asc' },
      { label: '随机', value: 'random' },
    ],

    // === 阶段切换跟踪 ===
    loadedPhase: '',

    // === 单词记忆 ===
    wordDetail: null,
    wordList: [],
    wordIdMap: {},
    currentIndex: 0,
    totalWords: 0,
    searchValue: '',
    isFavorite: false,
    _favoriteId: null,
    loading: true,

    // === 分页状态 ===
    wordListPage: 1,
    hasMore: false,
    loadingMore: false,
    pageSize: 50,

    // === 情景记忆 ===
    timeRanges: ['一天', '一周', '一个月'],
    activeTimeRange: 1,
    textTypes: ['报道', '故事', '顺口溜'],
    activeTextType: 1,
    wordSources: ['错题', '随机'],
    activeWordSource: 0,
    scenarioWords: [],          // [{word}]
    scenarioText: '',
    scenarioSegments: [],       // [{text, bold}]
    generated: false,
    generating: false,
    scenarioLoading: false,
    scenarioId: null,            // 最新生成情景文段的 DB id，用于收藏
    scenarioFaved: false,        // 当前情景文段是否已收藏
    scenarioError: '',            // 生成错误信息

    // === 收藏 ===
    favTabs: ['单词', '文章', '文段', '歌曲'],
    activeFavTab: 0,
    favorites: { words: [], articles: [], passages: [], songs: [] },
    showPassageModal: false,
    favPassageDetail: { content: '', passage_type: '' },

    // === 导航栏安全区 ===
    statusBarHeight: 44,
    navBarTop: 0,
    navBarHeight: 44,
    navPadLeft: 16,
    navPadRight: 16,

    // === oapp 5-tab 切换 ===
    oappTab: 0,
    showOset: false,

    // === oapp Tab 0: 首页 ===
    dailyQuote: {
      en: 'The only way to do great work is to love what you do.',
      cn: '成就伟业的唯一途径是热爱你所做的事。'
    },
    studyDays: 0,
    todayDate: '',
    stats: { todayWords: 0, weekWords: 0, accuracy: 0 },
    mistakeStats: { wordCount: 0, grammarCount: 0 },
    mistakeItems: [],

    // === oapp Tab 2: 训练（从 question_bank 题库取题） ===
    trainData: {
      current: 0, correct: 0, wrong: 0,
      type: '', question: '', options: [],
      selected: null, feedback: '', analysis: '',
      isFillIn: false,          // 是否为填空题/开放题
      userInput: '',            // 用户文本输入
      reference: '',            // 参考答案/范文
      fillSubmitted: false,     // 是否已提交
    },
    trainHistory: [],
    trainProgress: 0,
    trainLoading: false,
    trainArticle: null,            // 阅读模式文章 {title, content, content_cn, word_count}
    _questions: [],                // 从 API 拉取的题目 [{id, type, content: {stem, options, answer, explanation}}]
    questionCount: 10,
    showTrainMenu: false,
    showTranslation: false,        // 阅读模式是否显示中文翻译
    favorites: {},                 // 收藏映射表 { favKey: { stem, type, timestamp } }
    currentFavKey: '',             // 当前阅读文章的收藏 key
    trainContentTypes: ['单词', '短语语法', '阅读', '句子翻译', '作文'],
    activeTrainType: 0,

    // === oapp Tab 3: 小e ===
    oecTab: 0,
    oecSceneKeyword: '',
    // 情景对话
    oecScenePresets: [],        // 预设场景列表
    oecSceneSelected: null,     // 当前选中的场景对象
    oecSceneMsgs: [],           // 情景对话消息列表
    oecSceneInput: '',          // 情景对话输入
    oecSceneSending: false,     // 发送中
    oecSceneScrollToId: '',     // 滚动锚点
    // 智能问答 & 翻译
    oecChatMsgs: [{ role: 'ai', content: '你好！我是小e AI 助手，有什么可以帮助你学习英语的呢？' }],
    oecChatInput: '',
    oecTransDir: 'zh2en',
    oecTransInput: '',

    // === oapp Tab 4: 我的 ===
    oappProfile: {
      avatar: '', name: '学习者',
      phase: '四六级', days: 0,
      wordCount: 0, trainCount: 0, totalDays: 0,
      remindOn: false, darkMode: false
    },
    // studyPhase 从 app.globalData 获取
    studyPhase: '四六级'
  },

  onLoad() {
    // 合并首次加载的所有 setData 为一次调用，减少分离窗口下跨进程通信次数
    this.initNavBar();
    this.loadFavorites();
    // 合并 startFreshLoad 的同步部分 + loadOappHomeData 为一次 setData
    const app = getApp();
    const now = new Date();
    const dateStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
    this.setData({
      wordList: [], wordIdMap: {}, wordDetail: null,
      totalWords: 0, loading: true,
      wordListPage: 1, hasMore: false, loadingMore: false,
      todayDate: dateStr,
      studyDays: app.globalData.studyDays || 0,
      studyPhase: app.globalData.studyPhase || '四六级',
      stats: {
        todayWords: app.globalData.todayWords || 0,
        weekWords: app.globalData.weekWords || 0,
        accuracy: app.globalData.accuracy || 0
      },
      mistakeStats: {
        wordCount: app.globalData.mistakeWordCount || 0,
        grammarCount: app.globalData.mistakeGrammarCount || 0
      },
      mistakeItems: app.globalData.mistakeItems || [],
      oappProfile: {
        avatar: '',
        name: app.globalData.nickName || '学习者',
        phase: app.globalData.studyPhase || '四六级',
        days: app.globalData.studyDays || 0,
        wordCount: app.globalData.totalWords || 0,
        trainCount: app.globalData.trainCount || 0,
        totalDays: app.globalData.totalDays || 0,
        remindOn: app.globalData.remindOn || false,
        darkMode: app.globalData.darkMode || false
      }
    });
    // 异步加载单词列表延迟到下一帧，避免阻塞首屏渲染和交互
    wx.nextTick(() => {
      this.loadWordList(1, true);
    });
  },

  onUnload() {
    // 清理情景对话打字机定时器
    if (this._oecSceneTimer) {
      clearInterval(this._oecSceneTimer);
      this._oecSceneTimer = null;
    }
  },

  onShow() {
    // 每次页面显示都强制检查阶段是否变化，消除异步竞态
    if (this.data._wasHidden) {
      this.setData({ _wasHidden: false });
      this.checkPhaseAndReload();
    }
    if (this.data.activeTab === 1) {
      this.loadScenarioWords();
    } else if (this.data.activeTab === 2) {
      this.loadFavorites();
    }
  },

  onHide() {
    // 页面隐藏时标记，下次 onShow 时做一次完整检查
    this.setData({ _wasHidden: true });
  },

  // 检查阶段变化，如果变了则重新加载整个单词列表
  checkPhaseAndReload() {
    const app = getApp();
    const currentPhase = app.globalData.studyPhase || '';
    if (currentPhase && currentPhase !== this.data.loadedPhase) {
      this.startFreshLoad();
    }
  },

  // 完全重新加载：清空旧数据、重置分页、从第一页加载
  startFreshLoad() {
    this.setData({
      wordList: [], wordIdMap: {}, wordDetail: null,
      totalWords: 0, loading: true,
      wordListPage: 1, hasMore: false, loadingMore: false
    });
    this.loadWordList(1, true);
  },

  initNavBar() {
    try {
      // 优先使用新 API，低版本 lib 降级（typeof 检查避免触发弃用警告）
      let appBase, winInfo;
      if (typeof wx.getAppBaseInfoSync === 'function') {
        appBase = wx.getAppBaseInfoSync();
        winInfo = wx.getWindowInfoSync();
      } else {
        const sysInfo = wx.getSystemInfoSync();
        appBase = sysInfo;
        winInfo = sysInfo;
      }
      const btnRect = wx.getMenuButtonBoundingClientRect();
      const statusBarHeight = appBase.statusBarHeight || 44;
      const navBarHeight = (btnRect.top - statusBarHeight) * 2 + btnRect.height;
      this.setData({
        statusBarHeight: statusBarHeight,
        navBarTop: statusBarHeight,
        navBarHeight: navBarHeight,
        navPadLeft: Math.max(btnRect.left > 100 ? 16 : btnRect.left - 8, 8),
        navPadRight: Math.max(winInfo.windowWidth - btnRect.left + 8, 16)
      });
    } catch (e) {
      console.error('获取系统信息失败', e);
      this.setData({ statusBarHeight: 44, navBarTop: 0, navBarHeight: 44, navPadLeft: 16, navPadRight: 16 });
    }
  },

  // ===== 侧边栏 =====
  onBack() {
    wx.navigateBack();
  },

  onMenuTap() {
    this.setData({ showSidebar: true });
  },

  onCloseSidebar() {
    this.setData({ showSidebar: false });
  },

  onMenuSelect(e) {
    const tab = Number(e.currentTarget.dataset.tab);
    this.setData({ activeTab: tab, showSidebar: false });
    if (tab === 1) {
      this.loadScenarioWords();
    } else if (tab === 2) {
      this.loadFavorites();
    }
  },

  // ===== 右侧单词列表抽屉 =====
  onWordListTap() {
    this.setData({ showWordList: true });
  },

  onCloseWordList() {
    this.setData({ showWordList: false });
  },

  onWordItemTap(e) {
    const index = Number(e.currentTarget.dataset.index);
    const word = this.data.wordList[index];
    this.setData({ currentIndex: index, showWordList: false });
    this.loadWordDetail(word);
  },

  // ===== 单词记忆逻辑 =====

  // 加载单词列表（支持分页，fresh=true 时清空旧数据重建）
  async loadWordList(page, fresh) {
    try {
      const app = getApp();
      const phase = app.globalData.studyPhase || '四六级';
      const sortBy = this.data.currentSort;
      const pageSize = this.data.pageSize;
      const result = await api.getWordList({ phase, page, pageSize, sortBy });
      const items = result.items || [];

      // 对新数据建立 word → id 映射
      const newIdMap = {};
      const newWords = items.map(w => {
        newIdMap[w.word] = w.id;
        return w.word;
      });

      if (fresh) {
        // 完全刷新：替换列表
        this.setData({
          wordList: newWords, wordIdMap: newIdMap,
          totalWords: result.total || newWords.length,
          wordListPage: page, hasMore: page < result.total_pages,
          loading: false, loadingMore: false,
          loadedPhase: phase
        });
        // 加载第一个单词详情（异步非阻塞，用户先看到列表，详情后台加载）
        if (newWords.length > 0) {
          this.loadWordDetail(newWords[0]).catch(e => console.error('首单词详情加载失败', e));
        }
      } else {
        // 追加分页：合并列表和映射
        const mergedWords = this.data.wordList.concat(newWords);
        const mergedMap = { ...this.data.wordIdMap, ...newIdMap };
        this.setData({
          wordList: mergedWords, wordIdMap: mergedMap,
          wordListPage: page, hasMore: page < result.total_pages,
          loadingMore: false
        });
      }
    } catch (err) {
      console.error('加载单词列表失败', err);
      this.setData({ loading: false, loadingMore: false });
      wx.showToast({ title: '无法加载单词列表，请检查后端服务', icon: 'none' });
    }
  },

  // 加载更多（下一页）
  async loadMoreWords() {
    if (this.data.loadingMore || !this.data.hasMore) return;
    this.setData({ loadingMore: true });
    await this.loadWordList(this.data.wordListPage + 1, false);
  },

  // 单词列表抽屉滚动到底部 → 加载更多
  onWordListScrollToLower() {
    this.loadMoreWords();
  },

  // 将后端 WordDetail 字段映射为 WXML 期望的格式
  adaptWordDetail(detail) {
    if (!detail) return null;

    // meaning: 后端返回 translation（释义行展示），只保留 translation，definition 用于例句兜底
    const meaning = detail.translation || '';

    // 从 detail_json 中提取真实例句
    let realExample = null;
    if (detail.detail_json) {
      const dj = detail.detail_json;
      if (dj.example && typeof dj.example === 'object') {
        realExample = { en: dj.example.en || dj.example.sentence || '', zh: dj.example.zh || dj.example.translation || '' };
      } else if (dj.sentences && Array.isArray(dj.sentences) && dj.sentences.length > 0) {
        const s = dj.sentences[0];
        realExample = { en: s.en || s.sentence || '', zh: s.zh || s.translation || '' };
      }
    }

    // 按 POS 前缀提取函数：将 "n.xxx n.xxx v.xxx" 格式的文本解析为 [{pos, texts}, ...]
    function parseByPos(text) {
      if (!text) return [];
      const groups = [];
      const re = /\b([a-z]{1,5})\.\s*/gi;
      let lastIdx = 0;
      let lastPos = '';
      let match;
      while ((match = re.exec(text)) !== null) {
        if (lastPos) {
          const content = text.substring(lastIdx, match.index).replace(/^[;,；，\s]+|[;,；，\s]+$/g, '').trim();
          if (content) groups.push({ pos: lastPos, texts: content });
        }
        lastPos = match[1] + '.';
        lastIdx = match.index + match[0].length;
      }
      if (lastPos) {
        const content = text.substring(lastIdx).replace(/^[;,；，\s]+|[;,；，\s]+$/g, '').trim();
        if (content) groups.push({ pos: lastPos, texts: content });
      }
      return groups;
    }

    // 解析中文释义（POS 分组），如 "n.州;状态;国家 v.说明;陈述"
    // 注意 translation 可能使用 ; 或 ，等分隔符
    const cnGroups = parseByPos(meaning);

    // 解析英文释义（用作例句兜底），如 "n. the territory... n. the way... v. express..."
    const enGroups = parseByPos(detail.definition || '');

    // 合并生成 posGroups：从 cnGroups 获取 pos + 中文释义，从 enGroups 匹配同 pos 的英文释义
    const posGroups = [];
    for (const cg of cnGroups) {
      // 匹配同词性的英文释义
      let enText = '';
      for (const eg of enGroups) {
        if (eg.pos === cg.pos) {
          enText = eg.texts;
          break;
        }
      }
      // 统一中文分隔符展示
      const displayDefs = cg.texts.replace(/;/g, '；');
      posGroups.push({ pos: cg.pos, definitions: displayDefs, enText });
    }
    // 没有 cnGroups 但有 enGroups 时（translation 为空），用英文分组兜底
    if (posGroups.length === 0 && enGroups.length > 0) {
      for (const eg of enGroups) {
        posGroups.push({ pos: eg.pos, definitions: '', enText: eg.texts });
      }
    }

    // 找第一个有英文的分组，后面的分组如果没有独立英文，借用第一个的
    let firstEnExample = '';
    for (const pg of posGroups) {
      if (pg.enText) {
        firstEnExample = pg.enText;
        break;
      }
    }

    // 组装最终例句 + 单词高亮 segments
    const word = detail.word || '';
    for (const pg of posGroups) {
      let exampleEn = '';
      let exampleZh = '';
      const hasRealExample = realExample && (realExample.en || realExample.zh);
      if (hasRealExample) {
        exampleEn = realExample.en;
        exampleZh = realExample.zh;
      } else if (pg.enText) {
        exampleEn = pg.enText;
        exampleZh = '';
      } else if (firstEnExample) {
        // 借用第一个有英文的分组作为例句
        exampleEn = firstEnExample;
        exampleZh = '';
      }
      // 生成高亮 segments：将单词部分拆分出来用于加粗展示
      const segments = [];
      if (word && exampleEn && typeof exampleEn === 'string') {
        const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const parts = exampleEn.split(new RegExp(`(${escaped})`, 'gi'));
        for (const p of parts) {
          if (p) segments.push({ text: p, bold: p.toLowerCase() === word.toLowerCase() });
        }
      }
      pg.example = { en: exampleEn, zh: exampleZh, segments };
    }
    // 清理临时字段
    for (const pg of posGroups) delete pg.enText;

    // exchange: 解析词形变化字符串，如 "d:predicted/p:predicted/i:predicting/3:predicts"
    const exchangeMap = {
      'p': '过去式', 'd': '过去分词', 'i': '现在分词',
      '3': '第三人称单数', 's': '复数', 'r': '比较级', 't': '最高级'
    };
    const exchangeData = [];
    if (detail.exchange) {
      for (const part of detail.exchange.split('/')) {
        const [code, form] = part.split(':');
        if (form && exchangeMap[code]) {
          exchangeData.push({ label: exchangeMap[code], form });
        }
      }
    }

    // synonyms: 后端返回 {synonym_word, tag, usage_desc, example}，映射为 WXML 字段
    const tagStyleMap = {
      '常用': { tagBg: '#EEF2FF', tagColor: '#5B9E6F' },
      '正式': { tagBg: '#FEF3C7', tagColor: '#D97706' },
      '口语': { tagBg: '#FCE7F3', tagColor: '#DB2777' },
      '文学': { tagBg: '#F3F4F6', tagColor: '#6B7280' },
      '书面': { tagBg: '#E0E7FF', tagColor: '#4338CA' },
    };
    const synonyms = (detail.synonyms || []).map((s, i) => {
      const st = tagStyleMap[s.tag] || { tagBg: '#F3F4F6', tagColor: '#6B7280' };
      return {
        word: s.synonym_word || '',
        isPrimary: i === 0,
        tag: s.tag || '',
        tagBg: st.tagBg,
        tagColor: st.tagColor,
        usage: s.usage_desc || '',
        example: s.example || ''
      };
    });

    // tag: 后端返回空格分隔的考试标签，如 "cet4 zk gk"
    const tagList = (detail.tag || '')
      .split(/\s+/)
      .filter(Boolean)
      .map(t => ({
        label: t,
        color: TAG_COLORS[t] || '#6B7280',
      }));

    return {
      ...detail,
      meaning,
      posGroups,
      synonyms,
      tagList,
      exchangeData
    };
  },

  async loadWordDetail(word) {
    try {
      // 查询 word → id 映射，后端 /words/{word_id} 需整数 ID
      const wordId = this.data.wordIdMap?.[word];
      if (!wordId) {
        console.error('未找到单词ID，跳过', word);
        return;
      }
      const detail = await api.getWordDetail(wordId);
      if (detail) {
        // 字段适配：将后端返回格式转为 WXML 期望的格式
        const adapted = this.adaptWordDetail(detail);
        this.setData({ wordDetail: adapted });
        // 用 word_id 检查收藏状态
        const favResult = await api.checkFavorite('word', wordId).catch(() => ({ is_favorite: false, favorite_id: null }));
        this.setData({ isFavorite: favResult.is_favorite, _favoriteId: favResult.favorite_id });
      }
    } catch (err) {
      console.error('加载单词详情失败', word, err);
      wx.showToast({ title: '无法加载单词详情，请检查后端服务', icon: 'none' });
    }
  },

  onSearchInput(e) {
    this.setData({ searchValue: e.detail.value });
  },

  async onSearchConfirm() {
    const word = this.data.searchValue.trim();
    if (!word) return;
    await this.loadWordDetail(word);
  },

  onPlaySound() {
    const word = this.data.wordDetail?.word;
    if (word) {
      const innerAudioContext = wx.createInnerAudioContext();
      innerAudioContext.src = `https://dict.youdao.com/dictvoice?audio=${encodeURIComponent(word)}&type=2`;
      innerAudioContext.play();
      innerAudioContext.onError(() => {
        wx.showToast({ title: '播放发音', icon: 'none' });
      });
    }
  },

  async onToggleFavorite() {
    const detail = this.data.wordDetail;
    const wordText = detail?.word;
    const wordId = detail?.id;
    if (!wordText || !wordId) return;

    try {
      if (this.data.isFavorite) {
        await api.removeFavorite('word', wordId);
        this.setData({ isFavorite: false, _favoriteId: null });
        wx.showToast({ title: '已取消收藏', icon: 'none' });
      } else {
        const result = await api.addFavorite({
          target_type: 'word',
          target_id: wordId,
          data: {
            word: wordText,
            phonetic: detail.phonetic || '',
            meaning: detail.meaning || ''
          }
        });
        // 保存新增收藏记录的 id
        const favId = result && (result.id || result._id);
        this.setData({ isFavorite: true, _favoriteId: favId });
        wx.showToast({ title: '已收藏', icon: 'none' });
      }
    } catch (err) {
      console.error('收藏操作失败', err);
      wx.showToast({ title: '操作失败', icon: 'none' });
    }
  },

  /** 记录当前单词学习进度（切换单词时调用） */
  async recordCurrentWordProgress() {
    const detail = this.data.wordDetail;
    if (!detail || !detail.id) return;
    try {
      // 浏览过至少记为“认识”，保留已熟悉/掌握的等级。
      await api.recordWordProgress(detail.id, Math.max(1, detail.progress?.mastery_level || 0));
    } catch (err) {
      console.warn('记录单词进度失败', err);
    }
  },

  async onPrev() {
    if (this.data.currentIndex > 0) {
      await this.recordCurrentWordProgress();
      const newIndex = this.data.currentIndex - 1;
      this.setData({ currentIndex: newIndex });
      await this.loadWordDetail(this.data.wordList[newIndex]);
    }
  },

  async onNext() {
    if (this.data.currentIndex < this.data.totalWords - 1) {
      await this.recordCurrentWordProgress();
      const newIndex = this.data.currentIndex + 1;
      this.setData({ currentIndex: newIndex });
      await this.loadWordDetail(this.data.wordList[newIndex]);
    }
  },

  // ===== 情景记忆逻辑 =====

  onWordSourceChange(e) {
    const index = e.currentTarget.dataset.index;
    this.setData({ activeWordSource: index, scenarioText: '', generated: false, scenarioLoading: true }, () => {
      this.loadScenarioWords();
    });
  },

  onSelectTimeRange(e) {
    this.setData({ activeTimeRange: e.currentTarget.dataset.index });
    // 切换时间范围后重新加载错题（仅错题模式下）
    if (this.data.wordSources[this.data.activeWordSource] === '错题') {
      this.loadScenarioWords();
    }
  },

  onSelectTextType(e) {
    this.setData({ activeTextType: e.currentTarget.dataset.index });
  },

  // 加载情景单词（错题 / 随机），使用世代计数器防竞态
  async loadScenarioWords() {
    this._scenarioGen = (this._scenarioGen || 0) + 1;
    const gen = this._scenarioGen;
    const source = this.data.wordSources[this.data.activeWordSource];
    try {
      if (source === '错题') {
        await this.loadMistakeWords(gen);
      } else {
        await this.loadRandomWords(gen);
      }
    } finally {
      if (gen === this._scenarioGen) {
        this.setData({ scenarioLoading: false });
      }
    }
  },

  async loadMistakeWords(gen) {
    try {
      const result = await api.getMistakes();
      if (gen !== this._scenarioGen) return;
      const items = (result && result.items) || [];
      if (!items.length) return;
      const words = [];
      for (const m of items) {
        if (words.length >= 8) break;
        const q = m.question;
        if (!q || !q.content) continue;
        const content = q.content;
        const wordText = content.word || content.question_text || content.text || '';
        const wordId = content.word_id || q.id;
        if (wordText) {
          words.push({ word: wordText, id: wordId });
        }
      }
      if (gen !== this._scenarioGen) return;
      this.setData({ scenarioWords: words, generated: false });
    } catch (err) {
      console.error('加载错题单词失败', err);
    }
  },

  async loadRandomWords(gen) {
    try {
      const app = getApp();
      const phase = app.globalData.studyPhase || '四六级';
      const result = await api.getWordList({ phase, page: 1, pageSize: 50, sortBy: 'random' });
      if (gen !== this._scenarioGen) return;
      let rawList = [];
      if (Array.isArray(result)) {
        rawList = result;
      } else if (result && Array.isArray(result.items)) {
        rawList = result.items;
      }
      const words = rawList.slice(0, 8).map(w => ({ word: w.word || w, id: w.id || null }));
      if (gen !== this._scenarioGen) return;
      this.setData({ scenarioWords: words, generated: false });
    } catch (err) {
      console.error('加载随机单词失败', err);
    }
  },

  async onGenerate() {
    if (this.data.scenarioLoading || this.data.generating) {
      return;
    }
    const items = this.data.scenarioWords;
    if (items.length === 0) {
      wx.showToast({ title: '请先选择单词', icon: 'none' });
      return;
    }
    this.setData({
      generating: true, generated: false,
      scenarioText: '', scenarioSegments: [],
      scenarioId: null, scenarioFaved: false,
      scenarioError: '',
    });
    try {
      // 只提取数字 wordId，确保后端 List[int] 校验通过
      let wordIds = items
        .map(w => (typeof w.id === 'number' ? w.id : null))
        .filter(id => id !== null);
      // 如果没有数字 ID（如错题模式），用 word 文本从 wordIdMap 查 ID
      if (wordIds.length === 0) {
        const idMap = this.data.wordIdMap || {};
        wordIds = items
          .map(w => idMap[w.word] || null)
          .filter(id => id !== null);
      }
      // 仍然拿不到数字 ID，回退到单词文本（后端需兼容）
      if (wordIds.length === 0) {
        wordIds = items.map(w => w.word).filter(Boolean);
      }
      console.log('[scenario] 发送生成请求 wordIds:', wordIds);
      const data = await api.generateScenario({
        wordIds,
        textType: this.data.textTypes[this.data.activeTextType],
        timeRange: this.data.timeRanges[this.data.activeTimeRange],
      });
      console.log('[scenario] 生成响应:', data);
      const rawText = (data && data.content) || '';
      if (!rawText) {
        throw new Error('AI 返回内容为空');
      }
      const scenarioId = data && data.id;
      let scenarioFaved = false;
      if (scenarioId) {
        const favResult = await api.checkFavorite('segment', scenarioId).catch(() => ({ is_favorite: false }));
        scenarioFaved = favResult.is_favorite;
      }
      this.setData({
        scenarioText: rawText,
        scenarioSegments: this.parseScenarioText(rawText),
        scenarioId: scenarioId,
        scenarioFaved: scenarioFaved,
        generated: true,
        generating: false,
        scenarioError: '',
      });
    } catch (err) {
      console.error('生成情景文段失败', err);
      const errMsg = err.message || err.errMsg || '未知错误，请检查后端服务是否运行';
      wx.showToast({ title: '生成失败', icon: 'none' });
      this.setData({ generating: false, scenarioError: errMsg });
    }
  },

  // 解析 AI 返回的 **word** 标记为加粗 segments
  parseScenarioText(text) {
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
    return segments;
  },

  async onBookmark() {
    const scenarioId = this.data.scenarioId;
    if (!scenarioId) {
      wx.showToast({ title: '暂无内容可收藏', icon: 'none' });
      return;
    }
    try {
      if (this.data.scenarioFaved) {
        await api.removeFavorite('segment', scenarioId);
        this.setData({ scenarioFaved: false });
        wx.showToast({ title: '已取消收藏', icon: 'none' });
      } else {
        await api.addFavorite({
          target_type: 'segment',
          target_id: scenarioId,
          data: { content: this.data.scenarioText, passage_type: this.data.textTypes[this.data.activeTextType] }
        });
        this.setData({ scenarioFaved: true });
        wx.showToast({ title: '已收藏', icon: 'success' });
      }
    } catch (err) {
      console.error('情景文段收藏失败', err);
      wx.showToast({ title: '操作失败', icon: 'none' });
    }
  },

  onGenerateVideo() {
    // 获取当前情景 ID，跳转到场景创建页
    const scenarioId = this.data.scenarioId;
    if (!scenarioId) {
      wx.showToast({ title: '暂无情景内容', icon: 'none' });
      return;
    }
    wx.navigateTo({
      url: `/pages/memory/scene-create/index?scenarioId=${scenarioId}`
    });
  },

  // ===== 收藏逻辑 =====
  async loadFavorites() {
    this.setData({ loading: true });
    try {
      // 一次性加载全部收藏，前端按 target_type 过滤（1=单词,2=文章,3=文段,4=歌曲）
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
        created_at: f.created_at || '',
        video_url: f.video_url || '',
      });

      this.setData({
        favorites: {
          words: allFavs.filter(f => f.target_type === 1).map(toItem),
          articles: allFavs.filter(f => f.target_type === 2).map(toItem),
          passages: allFavs.filter(f => f.target_type === 3).map(toItem),
          songs: allFavs.filter(f => f.target_type === 4).map(toItem)
        },
        loading: false
      });
    } catch (err) {
      console.error('加载收藏失败', err);
      this.setData({ loading: false });
    }
  },

  onFavTabChange(e) {
    this.setData({ activeFavTab: e.currentTarget.dataset.index });
  },

  onFavItemTap(e) {
    const word = e.currentTarget.dataset.word;
    if (word) {
      const idx = this.data.wordList.indexOf(word);
      if (idx >= 0) {
        this.setData({ activeTab: 0, currentIndex: idx });
        this.loadWordDetail(word);
      } else {
        this.setData({ activeTab: 0 });
        this.loadWordDetail(word);
      }
    }
  },

  // ===== 排序切换 =====
  onSortChange(e) {
    const index = Number(e.currentTarget.dataset.index);
    const sortValue = this.data.sortValues[index];
    const sortLabel = this.data.sortOptions[index];
    this.setData({
      currentSort: sortValue,
      currentSortLabel: sortLabel,
    });
    // 重置到第一个单词并重新加载全部
    this.setData({ currentIndex: 0 });
    this.startFreshLoad();
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

  // ===== 收藏文段查看 =====
  onFavPassageTap(e) {
    const idx = e.currentTarget.dataset.index;
    const passage = this.data.favorites.passages[idx];
    if (!passage) return;
    const segments = this.parseBoldSegments(passage.content);
    this.setData({
      showPassageModal: true,
      favPassageDetail: { content: passage.content, passage_type: passage.passage_type, segments }
    });
  },

  onClosePassageModal() {
    this.setData({ showPassageModal: false, favPassageDetail: { content: '', passage_type: '', segments: [] } });
  },

  onStopPropagation() {},

  // ===== oapp 5-tab 切换 =====
  onOappTab(e) {
    const tab = Number(e.currentTarget.dataset.tab);
    const app = getApp();
    const phase = app.globalData.studyPhase || '四六级';
    // 先只切换 Tab 视图，让渲染层立即响应点击
    this.setData({ oappTab: tab, studyPhase: phase });
    // 延迟数据加载到下一帧，避免阻塞 Tab 切换动画
    wx.nextTick(() => {
      if (tab === 0) this.loadOappHomeData();
      if (tab === 2) {
        this._questions = [];
        this.startTrainingSession();
      }
    });
  },

  onOappStageTap() {
    wx.showActionSheet({
      itemList: ['小学', '初中', '高中', '四六级'],
      success: (res) => {
        const phases = ['小学', '初中', '高中', '四六级'];
        const newPhase = phases[res.tapIndex];
        const app = getApp();
        app.globalData.studyPhase = newPhase;
        this.setData({ studyPhase: newPhase });
        wx.showToast({ title: '切换至 ' + newPhase, icon: 'none' });
      }
    });
  },

  onBackToOappHome() {
    this.setData({ oappTab: 0 });
  },

  // ===== 侧边栏（obar）选择 =====
  onObarSelect(e) {
    const tab = Number(e.currentTarget.dataset.tab);
    this.setData({ activeTab: tab, showSidebar: false });
    if (tab === 1) this.loadScenarioWords();
    else if (tab === 2) this.loadFavorites();
  },

  // ===== 单词列表抽屉排序/选择 =====
  onOdrawerSort(e) {
    const sort = e.currentTarget.dataset.sort;
    const idx = this.data.sortValues.indexOf(sort);
    const sortValue = this.data.sortValues[idx >= 0 ? idx : 0];
    const sortLabel = this.data.sortOptions[idx >= 0 ? idx : 0];
    this.setData({ currentSort: sortValue, currentSortLabel: sortLabel });
    this.startFreshLoad();
  },

  onOdrawerSelect(e) {
    const index = Number(e.currentTarget.dataset.index);
    const word = this.data.wordList[index];
    this.setData({ currentIndex: index, showWordList: false });
    this.loadWordDetail(word);
  },

  // ===== oapp Tab 0: 首页数据加载 =====
  async loadOappHomeData() {
    const now = new Date();
    const dateStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
    const app = getApp();

    // 初始数据用 globalData 兜底，后面异步覆盖为真实 API 数据
    this.setData({
      todayDate: dateStr,
      studyDays: app.globalData.studyDays || 0,
      studyPhase: app.globalData.studyPhase || '四六级',
      stats: {
        todayWords: app.globalData.todayWords || 0,
        weekWords: app.globalData.weekWords || 0,
        accuracy: app.globalData.accuracy || 0
      },
      mistakeStats: {
        wordCount: 0,
        grammarCount: 0
      },
      mistakeItems: [],
      oappProfile: {
        avatar: app.globalData.avatarUrl || '',
        name: app.globalData.nickName || '学习者',
        phase: app.globalData.studyPhase || '四六级',
        days: app.globalData.studyDays || 0,
        wordCount: 0,
        trainCount: 0,
        totalDays: 0,
        remindOn: false,
        darkMode: false
      }
    });

    // 异步从 API 获取真实数据，并行请求减少等待时间
    try {
      const [dashboardData, profileData, mistakeRes] = await Promise.all([
        api.getUserStats().catch(() => null),
        api.getUserProfile().catch(() => null),
        api.getWordTrainingMistakes({ page: 1, pageSize: 10 }).catch(() => null),
      ]);

      const profile = profileData || {};
      const phase = profile.phase || app.globalData.studyPhase || '四六级';
      // 同步到 globalData 保持各 Tab 一致
      app.globalData.studyPhase = phase;
      if (profile.nickname) app.globalData.nickName = profile.nickname;

      const stats = dashboardData ? {
        todayWords: dashboardData.words_learned_today || 0,
        weekWords: dashboardData.words_learned_week || 0,
        accuracy: dashboardData.quiz_accuracy || 0,
      } : { todayWords: 0, weekWords: 0, accuracy: 0 };

      const mistakeItems = (mistakeRes && mistakeRes.items) || [];
      const mistakeStats = {
        wordCount: mistakeItems.length,
        grammarCount: 0,
      };

      this.setData({
        studyDays: profile.studyDays || 0,
        studyPhase: phase,
        stats,
        mistakeStats,
        mistakeItems,
        oappProfile: {
          avatar: profile.avatar_url || '',
          name: profile.nickname || '学习者',
          phase,
          days: profile.studyDays || 0,
          wordCount: stats.todayWords,
          trainCount: profile.totalTraining || 0,
          totalDays: profile.studyDays || 0,
          remindOn: false,
          darkMode: false,
        },
      });
    } catch (err) {
      console.warn('加载首页数据失败，使用 globalData 兜底', err);
    }
  },

  onViewAllMistakes() {
    wx.showToast({ title: '查看全部错题', icon: 'none' });
  },

  // ===== oapp Tab 2: 训练 =====
  onOsetTap() {
    // 打开设置时同步当前阶段
    const app = getApp();
    this.setData({
      showOset: true,
      studyPhase: app.globalData.studyPhase || '四六级',
    });
  },
  onCloseOset() {
    this.setData({ showOset: false });
  },

  /** 训练设置 - 切换学习阶段 */
  onOsetPhaseTap() {
    wx.showActionSheet({
      itemList: ['小学', '初中', '高中', '四六级'],
      success: (res) => {
        const phases = ['小学', '初中', '高中', '四六级'];
        const newPhase = phases[res.tapIndex];
        const app = getApp();
        app.globalData.studyPhase = newPhase;
        this.setData({
          studyPhase: newPhase,
          showOset: false,
        });
        wx.showToast({ title: '已切换至 ' + newPhase, icon: 'none' });
        // 切换阶段后重置训练题目
        this._questions = [];
        this.startTrainingSession();
      }
    });
  },

  // ===== 训练：从 question_bank 题库取题 =====

  /** 当前阶段名称 → stage 数字（精简为四个阶段） */
  _phaseToStage(phase) {
    const map = {
      '小学': 1, '英语启蒙': 1, '小学三年级': 1, '小学四年级': 1, '小学五年级': 1, '小学英语': 1,
      '初中': 2, '初中一年级': 2, '初中二年级': 2, '初中三年级': 2, '初中英语': 2,
      '高中': 3, '高中一年级': 3, '高中二年级': 3, '高中三年级': 3, '高中英语': 3,
      '四六级': 4, '英语四级': 4, '英语六级': 4, '考研英语': 4,
      '雅思': 4, '托福': 4, 'GRE': 4,
    };
    return map[phase] || 4;  // 默认四六级
  },

  /** 当前训练类型 → 后端题型编号 */
  _activeTypeToQuestionTypes() {
    const map = [
      [1, 2],   // 0: 单词 → 英译中 + 中译英
      [4],      // 1: 短语语法
      [6],      // 2: 阅读 → 阅读理解
      [8],      // 3: 句子翻译（中译英填空，AI生成）
      [9],      // 4: 作文写作（AI生成）
    ];
    return map[this.data.activeTrainType] || [1, 2];
  },

  /** 拉取真实题目并启动训练 */
  async startTrainingSession() {
    const app = getApp();
    const phase = app.globalData.studyPhase || '四六级';
    const stage = this._phaseToStage(phase);
    const count = this.data.questionCount || 10;
    const questionTypes = this._activeTypeToQuestionTypes();
    const activeType = this.data.activeTrainType;

    this.setData({ trainLoading: true, trainArticle: null });
    try {
      // 阅读模式（trainContentTypes 索引 2）：从 AI 题库取文章 + 5 题选择题
      if (activeType === 2) {
        const readingRes = await api.fetchFromQuestionBank({ qtype: 'reading', stage, difficulty: '中级' });
        if (!readingRes || !readingRes.questions || readingRes.questions.length === 0) {
          wx.showToast({ title: '暂无可用题目', icon: 'none' });
          this.setData({ trainLoading: false });
          return;
        }
        // AI 返回格式 → 标准化题目格式（correct → content.answer）
        const rc = 5; // 阅读固定 5 题
        const questions = readingRes.questions.map((q, i) => ({
          id: -(i + 1),  // 负 ID 标记 AI 生成题
          type: 6,
          content: {
            stem: q.stem,
            options: q.options,
            answer: q.correct,
            explanation: q.explanation || '',
          },
        }));
        this._questions = questions;
        this.setData({
          trainArticle: {
            title: readingRes.title || '',
            content: readingRes.content || '',
            content_cn: readingRes.content_cn || '',
            word_count: readingRes.word_count || 0,
          },
          trainHistory: [],
          trainData: this._buildTrainData(questions[0], 0, 0, 0),
          trainProgress: Math.min(1 / rc * 100, 100),
          questionCount: rc,
          trainLoading: false,
        });
        this.refreshFavStatus();
        return;
      }

      const questions = await api.generateTrainingQuestions({
        questionTypes,
        stage,
        count: count === 0 ? 50 : count,
        mode: count === 0 ? 'infinite' : 'fixed',
      });
      if (!questions || questions.length === 0) {
        wx.showToast({ title: '暂无可用题目', icon: 'none' });
        this.setData({ trainLoading: false });
        return;
      }
      this._questions = questions;
      this.setData({
        trainHistory: [],
        trainData: this._buildTrainData(questions[0], 0, 0, 0),
        trainProgress: count === 0 ? 0 : Math.min(1 / count * 100, 100),
        trainLoading: false,
      });
    } catch (e) {
      console.error('获取训练题目失败:', e);
      wx.showToast({ title: '加载题目失败', icon: 'none' });
      this.setData({ trainLoading: false });
    }
  },

  /** 后端题目 → 前端 trainData */
  _buildTrainData(q, index, correct, wrong) {
    // 填空/开放题（type 8/9）— 无 ABCD 选项，显示输入框
    const isFillIn = q.type === 8 || q.type === 9;
    const opts = isFillIn ? [] : (q.content.options || []).map((text, i) => ({
      letter: String.fromCharCode(65 + i),
      text,
      status: '',
    }));
    const typeNames = {
      1: '英译中', 2: '中译英', 3: '听力选择',
      4: '短语语法', 5: '句子翻译', 6: '阅读理解', 7: '听力训练',
      8: '句子翻译', 9: '作文写作',
    };
    return {
      current: index, correct, wrong,
      _qid: q.id,
      _answerIdx: q.content.answer ?? 0,
      _analysis: q.content.explanation || '',
      type: typeNames[q.type] || '选择题',
      question: q.content.stem || '',
      options: opts,
      selected: null, feedback: '', analysis: '',
      // 填空/开放题字段
      isFillIn,
      userInput: '',
      reference: q.content.reference || '',
      fillSubmitted: false,
    };
  },

  /** 保存当前题状态到历史（用于前后导航恢复） */
  saveCurrentTrainState() {
    const cur = this.data.trainData.current;
    const history = [...(this.data.trainHistory || [])];
    history[cur] = JSON.parse(JSON.stringify(this.data.trainData));
    this.setData({ trainHistory: history });
  },

  /** 选择答案 */
  async onTrainSelect(e) {
    if (this.data.trainData.selected !== null) return;
    const idx = Number(e.currentTarget.dataset.index);
    const td = this.data.trainData;
    const correct = idx === td._answerIdx;

    const opts = td.options.map((o, i) => ({
      ...o,
      status: i === idx ? (correct ? 'cor' : 'wro') : (i === td._answerIdx ? 'cor' : ''),
    }));

    this.setData({
      'trainData.selected': idx,
      'trainData.options': opts,
      'trainData.feedback': correct ? '回答正确！' : '回答错误',
      'trainData.analysis': td._analysis || '',
      'trainData.correct': td.correct + (correct ? 1 : 0),
      'trainData.wrong': td.wrong + (correct ? 0 : 1),
    }, () => { this.saveCurrentTrainState(); });

    // 异步提交答案到后端记录错题
    try {
      await api.submitAnswer({ questionId: td._qid, answer: idx, timeSpent: 0 });
    } catch (e) {
      console.warn('提交答案记录失败:', e);
    }
  },

  /** 填空题文本输入 */
  onFillInput(e) {
    this.setData({ 'trainData.userInput': e.detail.value });
  },

  /** 提交填空/开放题答案 */
  async _onFillSubmit() {
    const td = this.data.trainData;
    if (td.fillSubmitted) return; // 已提交过
    const userAnswer = (td.userInput || '').trim();
    if (!userAnswer) {
      wx.showToast({ title: '请先输入内容', icon: 'none' });
      return;
    }

    this.setData({
      'trainData.fillSubmitted': true,
      'trainData.feedback': '已提交！下方是参考翻译/范文：',
      'trainData.analysis': td.reference || '',
      'trainData.correct': td.correct + 1,
    }, () => { this.saveCurrentTrainState(); });

    // 异步记录答题
    try {
      await api.submitAnswer({ questionId: td._qid, answer: userAnswer, timeSpent: 0 });
    } catch (e) {
      console.warn('提交答案记录失败:', e);
    }
  },

  onTrainPrev() {
    const prev = this.data.trainData.current - 1;
    if (prev < 0) return;
    this.saveCurrentTrainState();
    const history = this.data.trainHistory || [];
    if (history[prev]) {
      const restored = JSON.parse(JSON.stringify(history[prev]));
      this.setData({
        trainData: { ...restored, correct: this.data.trainData.correct, wrong: this.data.trainData.wrong },
        trainProgress: this.data.questionCount === 0 ? 0 : Math.max(prev / this.data.questionCount * 100, 0),
      });
    }
  },

  onTrainNext() {
    // 保存当前题状态（选择题用 selected，填空题用 fillSubmitted）
    const td = this.data.trainData;
    if (td.isFillIn ? td.fillSubmitted : (td.selected !== null)) {
      this.saveCurrentTrainState();
    }
    const next = this.data.trainData.current + 1;
    const history = this.data.trainHistory || [];

    // 已有历史 → 恢复
    if (history[next]) {
      const restored = JSON.parse(JSON.stringify(history[next]));
      this.setData({
        trainData: { ...restored, correct: this.data.trainData.correct, wrong: this.data.trainData.wrong },
        trainProgress: this.data.questionCount === 0 ? 0 : Math.min(next / this.data.questionCount * 100, 100),
      });
      return;
    }

    // 从已拉取的题目中取下一题
    if (this._questions && next < this._questions.length) {
      const q = this._questions[next];
      const td = this.data.trainData;
      this.setData({
        trainData: this._buildTrainData(q, next, td.correct, td.wrong),
        trainProgress: this.data.questionCount === 0 ? 0 : Math.min(next / this.data.questionCount * 100, 100),
      });
      return;
    }

    // 无限模式：拉取更多题目
    if (this.data.questionCount === 0) {
      this._loadMoreQuestions(next);
    } else {
      wx.showToast({ title: '已完成全部题目！', icon: 'none' });
    }
  },

  /** 无限模式 - 追加拉取题目 */
  async _loadMoreQuestions(currentIndex) {
    const app = getApp();
    const phase = app.globalData.studyPhase || '四六级';
    const stage = this._phaseToStage(phase);
    const questionTypes = this._activeTypeToQuestionTypes();
    wx.showToast({ title: '加载更多题目...', icon: 'loading', duration: 2000 });

    try {
      const more = await api.generateTrainingQuestions({
        questionTypes, stage, count: 20, mode: 'infinite',
      });
      if (more && more.length > 0) {
        this._questions = (this._questions || []).concat(more);
        const q = this._questions[currentIndex];
        const td = this.data.trainData;
        this.setData({
          trainData: this._buildTrainData(q, currentIndex, td.correct, td.wrong),
        });
      } else {
        wx.showToast({ title: '没有更多题目了', icon: 'none' });
      }
    } catch (e) {
      console.error('加载更多题目失败:', e);
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  // 步进器 - 减少题数（到 0 表示无限）
  onDecreaseCount() {
    const cur = this.data.questionCount;
    if (cur === 0) return;
    const count = cur <= 5 ? 0 : cur - 5;
    this.setData({ questionCount: count });
  },

  // 步进器 - 增加题数（从 0 跳到 5）
  onIncreaseCount() {
    const cur = this.data.questionCount;
    if (cur === 0) {
      this.setData({ questionCount: 5 });
      return;
    }
    const count = Math.min(100, cur + 5);
    this.setData({ questionCount: count });
  },

  // 快捷数量选择（0 表示无限）
  onQuickCount(e) {
    const count = Number(e.currentTarget.dataset.count);
    this.setData({ questionCount: count });
  },

  // 训练 - 左侧菜单：选择训练内容
  onTrainMenuTap() {
    this.setData({ showTrainMenu: true });
  },

  onCloseTrainMenu() {
    this.setData({ showTrainMenu: false });
  },

  onTrainMenuSelect(e) {
    const index = Number(e.currentTarget.dataset.index);
    const type = this.data.trainContentTypes[index];
    this.setData({ activeTrainType: index, showTrainMenu: false });
    wx.showToast({ title: '已切换至 ' + type, icon: 'none' });
    // 重新拉取对应题型的题目
    this.startTrainingSession();
  },

  // ===== oapp Tab 3: 小e =====
  /** 切换小e子Tab */
  onOecTabChange(e) {
    const tab = Number(e.currentTarget.dataset.tab);
    this.setData({ oecTab: tab });
    // 延迟场景列表加载到下一帧，避免阻塞子 Tab 切换渲染
    if (tab === 0) {
      wx.nextTick(() => this.loadOecScenarios());
    }
  },
  /** 情景对话关键词输入 */
  onOecKeywordInput(e) {
    this.setData({ oecSceneKeyword: e.detail.value });
  },
  /** 加载情景对话场景预设 */
  async loadOecScenarios() {
    if (this.data.oecScenePresets.length > 0) return; // 已加载则跳过
    try {
      const result = await api.getScenarioPresets();
      if (result && result.presets) {
        this.setData({ oecScenePresets: result.presets });
        return;
      }
    } catch (err) {
      console.error('加载场景列表失败', err);
    }
    // 本地兜底
    this.setData({
      oecScenePresets: [
        { id: 'coffee', name: '咖啡店点餐', icon: '☕' },
        { id: 'restaurant', name: '餐厅用餐', icon: '🍽️' },
        { id: 'shopping', name: '购物逛街', icon: '🛍️' },
        { id: 'travel', name: '旅行问路', icon: '🗺️' },
        { id: 'hotel', name: '酒店入住', icon: '🏨' },
        { id: 'airport', name: '机场出行', icon: '✈️' },
        { id: 'interview', name: '面试求职', icon: '💼' },
        { id: 'hospital', name: '看医生', icon: '🏥' },
        { id: 'library', name: '图书馆', icon: '📚' },
        { id: 'friends', name: '结识朋友', icon: '🤝' },
      ]
    });
  },
  /** 选择预设场景 */
  onOecSelectScenario(e) {
    const id = e.currentTarget.dataset.id;
    const name = e.currentTarget.dataset.name;
    const presets = this.data.oecScenePresets;
    const scene = presets.find(s => s.id === id) || { id, name, icon: '🗣️' };
    this.enterOecScene(scene);
  },
  /** 自定义场景 */
  onOecCustomScene() {
    const kw = this.data.oecSceneKeyword.trim();
    if (!kw) {
      wx.showToast({ title: '请输入场景关键词', icon: 'none' });
      return;
    }
    const scene = { id: 'custom', name: kw, icon: '🎯', custom: true };
    this.enterOecScene(scene);
  },
  /** 进入场景对话 */
  async enterOecScene(scene) {
    // 先立即切换到对话视图（一次 setData），让渲染层先出画面
    this.setData({
      oecSceneSelected: scene,
      oecSceneMsgs: [{ role: 'ai', content: '', thinking: true }],
      oecSceneInput: '',
      oecSceneSending: true,
    });
    // 延迟到下一帧再发起网络请求，避免阻塞视图切换渲染
    wx.nextTick(async () => {
      try {
        await this.sendOecSceneMessage('', true);
      } catch (err) {
        console.error('进入场景失败', err);
        wx.showToast({ title: '进入场景失败', icon: 'none' });
      }
    });
  },
  /** 返回场景选择 */
  onOecBackToScenarios() {
    // 清理打字机定时器
    if (this._oecSceneTimer) {
      clearInterval(this._oecSceneTimer);
      this._oecSceneTimer = null;
    }
    this.setData({
      oecSceneSelected: null,
      oecSceneMsgs: [],
      oecSceneSending: false,
    });
  },
  /** 情景对话输入 */
  onOecSceneInput(e) {
    this.setData({ oecSceneInput: e.detail.value });
  },
  /** 发送情景对话消息 */
  onOecSceneSend() {
    const text = this.data.oecSceneInput.trim();
    if (!text || this.data.oecSceneSending) return;
    this.sendOecSceneMessage(text);
  },
  /** 通用：发送情景对话消息（初始化时传空字符串触发开场） */
  async sendOecSceneMessage(userText, isInit = false) {
    const { oecSceneSelected, oecSceneMsgs } = this.data;
    const msgs = [...oecSceneMsgs];
    if (!isInit) {
      msgs.push({ role: 'usr', content: userText });
      msgs.push({ role: 'ai', content: '', thinking: true });
      this.setData({
        oecSceneMsgs: msgs,
        oecSceneInput: '',
        oecSceneSending: true,
      });
    }
    // 构造消息历史（跳过 thinking 占位）
    const chatHistory = msgs
      .filter(m => m.role !== 'ai' || !m.thinking)
      .slice(-20)
      .map(m => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.content }));
    try {
      const result = await api.chatWithAI({
        messages: chatHistory,
        scenario: oecSceneSelected.id,
        provider: 'cloudbase',
        level: 'intermediate',
      });
      this.oecSceneTypewriterOutput(result.content);
    } catch (err) {
      console.error('情景对话失败', err);
      const curMsgs = [...this.data.oecSceneMsgs];
      for (let i = curMsgs.length - 1; i >= 0; i--) {
        if (curMsgs[i].role === 'ai' && curMsgs[i].thinking) {
          curMsgs[i] = { role: 'ai', content: '抱歉，回复生成失败，请稍后重试。', thinking: false };
          break;
        }
      }
      this.setData({ oecSceneMsgs: curMsgs, oecSceneSending: false });
    }
  },
  /** 情景对话打字机效果 */
  oecSceneTypewriterOutput(fullText) {
    const msgs = [...this.data.oecSceneMsgs];
    let targetIdx = -1;
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'ai' && msgs[i].thinking) {
        targetIdx = i;
        msgs[i] = { role: 'ai', content: '', thinking: false };
        break;
      }
    }
    if (targetIdx === -1) {
      msgs.push({ role: 'ai', content: fullText, thinking: false });
      this.setData({ oecSceneMsgs: msgs, oecSceneSending: false });
      return;
    }
    this.setData({ oecSceneMsgs: msgs });
    let index = 0;
    // 分离窗口下降低 setData 频率（80ms 间隔），每次输出 3 个字符
    // 避免每 30ms 跨进程通信导致的渲染线程阻塞
    const step = 3;
    const speed = 80;
    let scrollPending = false;
    this._oecSceneTimer = setInterval(() => {
      if (index >= fullText.length) {
        clearInterval(this._oecSceneTimer);
        this._oecSceneTimer = null;
        this.setData({ oecSceneSending: false });
        return;
      }
      const end = Math.min(index + step, fullText.length);
      const partial = fullText.slice(0, end);
      const latestMsgs = [...this.data.oecSceneMsgs];
      latestMsgs[targetIdx].content = partial;
      this.setData({ oecSceneMsgs: latestMsgs });
      index = end;
      // 每两次 tick 滚动一次，减少 setData 频率
      if (!scrollPending) {
        scrollPending = true;
        this.setData({ oecSceneScrollToId: 'oec-scene-bottom' });
        setTimeout(() => {
          this.setData({ oecSceneScrollToId: '' });
          scrollPending = false;
        }, 160);
      }
    }, speed);
  },
  /** 情景对话滚动到底部 */
  oecSceneScrollBottom() {
    this.setData({ oecSceneScrollToId: 'oec-scene-bottom' });
    setTimeout(() => {
      this.setData({ oecSceneScrollToId: '' });
    }, 100);
  },
  /** 小e输入（智能问答Tab） */
  onOecChatInput(e) {
    this.setData({ oecChatInput: e.detail.value });
  },
  /** 发送智能问答 */
  onOecChatSend() {
    const msg = this.data.oecChatInput.trim();
    if (!msg) return;
    const msgs = [...this.data.oecChatMsgs, { role: 'usr', content: msg }];
    this.setData({ oecChatMsgs: msgs, oecChatInput: '' });
    setTimeout(() => {
      const aiReply = { role: 'ai', content: '这是一个很好的问题！让我来帮助你学习...' };
      this.setData({ oecChatMsgs: [...this.data.oecChatMsgs, aiReply] });
    }, 800);
  },
  /** 翻译方向切换 */
  onOecTransDir(e) {
    const dir = e.currentTarget.dataset.tab === 0 ? 'zh2en' : 'en2zh';
    this.setData({ oecTransDir: dir });
  },
  /** 翻译方向交换 */
  onOecSwapDir() {
    const newDir = this.data.oecTransDir === 'zh2en' ? 'en2zh' : 'zh2en';
    this.setData({ oecTransDir: newDir });
  },
  /** 翻译内容输入 */
  onOecTransInput(e) {
    this.setData({ oecTransInput: e.detail.value });
  },
  /** 执行翻译 */
  onOecTranslate() {
    const text = this.data.oecTransInput.trim();
    if (!text) {
      wx.showToast({ title: '请输入翻译内容', icon: 'none' });
      return;
    }
    wx.showToast({ title: '翻译中...', icon: 'loading' });
    setTimeout(() => {
      wx.showToast({ title: '翻译完成', icon: 'none' });
    }, 1000);
  },
  /** 选择图片翻译 */
  onOecPickImage() {
    wx.chooseImage({
      count: 1,
      success: (res) => {
        wx.showToast({ title: '已选择图片', icon: 'none' });
      }
    });
  },

  // ===== oapp Tab 4: 我的 =====
  onOprofStudyPhase() {
    wx.showActionSheet({
      itemList: ['小学', '初中', '高中', '四六级'],
      success: (res) => {
        const phases = ['小学', '初中', '高中', '四六级'];
        const newPhase = phases[res.tapIndex];
        const app = getApp();
        app.globalData.studyPhase = newPhase;
        this.setData({ 'oappProfile.phase': newPhase, studyPhase: newPhase });
        wx.showToast({ title: '已切换至 ' + newPhase, icon: 'none' });
      }
    });
  },
  onOprofReport() {
    wx.showToast({ title: '学习报告', icon: 'none' });
  },
  onOprofToggleRemind() {
    const newVal = !this.data.oappProfile.remindOn;
    this.setData({ 'oappProfile.remindOn': newVal });
    wx.showToast({ title: newVal ? '已开启提醒' : '已关闭提醒', icon: 'none' });
  },
  onOprofApiKey() {
    wx.showToast({ title: 'API Key 配置', icon: 'none' });
  },
  onOprofTeacher() {
    wx.showToast({ title: '教师管理后台', icon: 'none' });
  },
  onOprofDocUpload() {
    wx.showToast({ title: '文档上传', icon: 'none' });
  },
  onOprofToggleDark() {
    const newVal = !this.data.oappProfile.darkMode;
    this.setData({ 'oappProfile.darkMode': newVal });
    wx.showToast({ title: newVal ? '深色模式' : '浅色模式', icon: 'none' });
  },
  onOprofSettings() {
    wx.showToast({ title: '系统设置', icon: 'none' });
  },
  onOprofFeedback() {
    wx.showToast({ title: '反馈', icon: 'none' });
  },
  onOprofLogout() {
    wx.showModal({
      title: '确认退出',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          wx.navigateBack();
        }
      }
    });
  },

  // ===== 阅读模式：中文翻译切换 =====
  onToggleTranslation() {
    this.setData({ showTranslation: !this.data.showTranslation });
  },

  // ===== 阅读模式：收藏功能（localStorage 持久化） =====
  FAVORITES_KEY: 'memoryWordFavorites',

  loadFavorites() {
    try {
      const saved = wx.getStorageSync(this.FAVORITES_KEY);
      if (saved && typeof saved === 'object') {
        this.setData({ favorites: saved });
      }
    } catch (e) {
      console.error('加载收藏失败', e);
    }
  },

  _saveFavorites() {
    try {
      wx.setStorageSync(this.FAVORITES_KEY, this.data.favorites);
    } catch (e) {
      console.error('保存收藏失败', e);
    }
  },

  _getFavKey() {
    const article = this.data.trainArticle;
    if (!article) return '';
    return 'r_article_' + (article.title || article.content || '').slice(0, 30);
  },

  /** 刷新当前阅读文章的收藏状态 */
  refreshFavStatus() {
    const key = this._getFavKey();
    this.setData({ currentFavKey: key });
  },

  onToggleFavorite() {
    const key = this.data.currentFavKey;
    if (!key) return;
    const fav = { ...this.data.favorites };
    if (fav[key]) {
      delete fav[key];
      wx.showToast({ title: '已取消收藏', icon: 'none' });
    } else {
      const article = this.data.trainArticle;
      fav[key] = {
        stem: (article.title || '').slice(0, 80),
        type: '阅读理解',
        timestamp: Date.now(),
      };
      wx.showToast({ title: '已收藏', icon: 'success' });
    }
    this.setData({ favorites: fav, currentFavKey: key });
    this._saveFavorites();
  },
});
