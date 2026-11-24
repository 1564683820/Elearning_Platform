// 幼儿识词页面
// 展示单词卡片：字母占位 + 英文单词 + 中文释义 + 小e语音教读
const phaseMode = require('../../../utils/phase-mode.js')

// 单词词库
const WORD_LIST = [
  { en: 'cat', cn: '猫咪', letters: 'C A T' },
  { en: 'dog', cn: '小狗', letters: 'D O G' },
  { en: 'fish', cn: '小鱼', letters: 'F I S H' },
  { en: 'bird', cn: '小鸟', letters: 'B I R D' },
  { en: 'bear', cn: '小熊', letters: 'B E A R' },
  { en: 'apple', cn: '苹果', letters: 'A P P L E' },
  { en: 'moon', cn: '月亮', letters: 'M O O N' },
  { en: 'star', cn: '星星', letters: 'S T A R' },
  { en: 'tree', cn: '大树', letters: 'T R E E' },
  { en: 'fish', cn: '小鱼', letters: 'F I S H' },
]

Page({
  data: {
    wordList: WORD_LIST,
    currentIndex: 0,
    currentWord: WORD_LIST[0],
    // 语音相关
    isSpeaking: false,
    // 对话气泡
    speechBubbles: [],
  },

  onLoad() {
    this.loadPhaseInfo()
  },

  onShow() {
    this.loadPhaseInfo()
  },

  // 加载阶段信息
  loadPhaseInfo() {
    const idx = phaseMode.getSavedPhaseIndex()
    this.setData({ currentPhase: phaseMode.PHASES[idx].name })
  },

  // 上一步：切到前一个单词
  onPrevWord() {
    if (this.data.currentIndex > 0) {
      const newIndex = this.data.currentIndex - 1
      this.setData({
        currentIndex: newIndex,
        currentWord: this.data.wordList[newIndex],
      })
    }
  },

  // 下一步：切到后一个单词
  onNextWord() {
    if (this.data.currentIndex < this.data.wordList.length - 1) {
      const newIndex = this.data.currentIndex + 1
      this.setData({
        currentIndex: newIndex,
        currentWord: this.data.wordList[newIndex],
      })
    }
  },

  // 跳转到指定单词（轮播指示点）
  onDotTap(e) {
    const index = e.currentTarget.dataset.index
    this.setData({
      currentIndex: index,
      currentWord: this.data.wordList[index],
    })
  },

  // 小e语音教读
  onSpeak() {
    const word = this.data.currentWord
    this.setData({ isSpeaking: true })

    // 模拟 TTS 教读
    const ttsMessages = [
      `真棒！${word.en} 是${word.cn}哦！`,
      `读得很好！再来一遍！`,
      `小朋友好厉害！${word.en} 就是${word.cn}！`,
      `跟小e一起读：${word.en}～`,
    ]
    const msg = ttsMessages[Math.floor(Math.random() * ttsMessages.length)]

    // 添加语音对话气泡
    const bubbles = this.data.speechBubbles
    bubbles.push({ text: msg })
    this.setData({ speechBubbles: bubbles, isSpeaking: false })

    // 3秒后自动清除气泡
    setTimeout(() => {
      bubbles.shift()
      this.setData({ speechBubbles: bubbles })
    }, 3000)
  },

  // 打开阶段选择
  onOpenPhaseSelector() {
    this.setData({ showPhaseSelector: true })
  },

  // 关闭阶段选择
  onClosePhaseSelector() {
    this.setData({ showPhaseSelector: false })
  },

  // 阶段已保存
  onPhaseSaved(e) {
    this.setData({
      showPhaseSelector: false,
      currentPhase: e.detail.name,
    })
    wx.showToast({ title: '阶段已保存，请重启', icon: 'none' })
  },
})
