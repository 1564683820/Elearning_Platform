// 幼儿小e对话页面
// 长按录音语音交互，AI 用 TTS 语音回复（哄小孩语气）
const phaseMode = require('../../../utils/phase-mode.js')
const api = require('../../../utils/api.js')

// 小e 角色回复语料（模拟，后续接入 LLM + TTS）
const AI_REPLIES = [
  '小朋友你好呀！我是小e，你今天开心吗？',
  '哇，你真棒！我们一起学英语吧～',
  '小星星亮晶晶，你会唱小星星吗？',
  '今天天气真好，我们一起读单词吧！',
  '你最喜欢什么颜色呀？小e喜欢绿色～',
  '真厉害！你读得真好听，再来一遍好不好？',
  '小狗叫 dog，小猫叫 cat，记住了吗？',
]

Page({
  data: {
    // 对话消息列表
    messages: [
      {
        type: 'ai',
        text: '小朋友你好呀！我是小e\n按住下面按钮，跟小e说说话吧！',
        time: this.formatTime(new Date()),
      },
    ],
    // 录音状态
    isRecording: false,
    recordingHint: '按住说话，松开发送',
    // 阶段信息
    currentPhase: '',
    showPhaseSelector: false,
  },

  onLoad() {
    this.loadPhaseInfo()
    // 初始化录音管理器
    this.recorderManager = wx.getRecorderManager()
    this.initRecorder()
  },

  onShow() {
    this.loadPhaseInfo()
  },

  // 加载阶段信息
  loadPhaseInfo() {
    const idx = phaseMode.getSavedPhaseIndex()
    this.setData({ currentPhase: phaseMode.PHASES[idx].name })
  },

  // 初始化录音管理器
  initRecorder() {
    this.recorderManager.onStop((res) => {
      // 录音结束，模拟 AI 回复
      this.sendVoiceMessage(res.tempFilePath)
    })
    this.recorderManager.onError(() => {
      wx.showToast({ title: '录音失败，请检查权限', icon: 'none' })
      this.setData({ isRecording: false, recordingHint: '按住说话，松开发送' })
    })
  },

  // 开始录音
  onStartRecord() {
    this.setData({ isRecording: true, recordingHint: '录音中，请说话...' })
    const options = {
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: 'mp3',
    }
    this.recorderManager.start(options)
  },

  // 结束录音
  onStopRecord() {
    if (!this.data.isRecording) return
    this.recorderManager.stop()
    this.setData({ isRecording: false, recordingHint: '发送中...' })
  },

  // 发送语音消息（模拟 AI 回复）
  sendVoiceMessage(tempFilePath) {
    // 添加用户语音消息
    const userMsg = {
      type: 'user',
      text: '🎤（语音消息）',
      time: this.formatTime(new Date()),
    }
    const msgs = [...this.data.messages, userMsg]
    this.setData({ messages: msgs })

    // 模拟 AI 回复（带延迟）
    setTimeout(() => {
      const reply = AI_REPLIES[Math.floor(Math.random() * AI_REPLIES.length)]
      const aiMsg = {
        type: 'ai',
        text: reply,
        time: this.formatTime(new Date()),
        showListenBtn: true,
      }
      const newMsgs = [...this.data.messages, aiMsg]
      this.setData({ messages: newMsgs, recordingHint: '按住说话，松开发送' })

      // 自动滚动到底部
      this.scrollToBottom()
    }, 1500)

    this.scrollToBottom()
  },

  // 重播小e语音
  onPlayVoice(e) {
    const index = e.currentTarget.dataset.index
    const msg = this.data.messages[index]
    if (!msg) return

    wx.showToast({ title: '🔊 播放语音：' + msg.text.slice(0, 10) + '...', icon: 'none' })
  },

  // 滚动到底部
  scrollToBottom() {
    setTimeout(() => {
      wx.createSelectorQuery()
        .selectViewport()
        .scrollOffset((res) => {
          wx.pageScrollTo({ scrollTop: res.scrollHeight, duration: 300 })
        })
        .exec()
    }, 100)
  },

  // 格式化时间
  formatTime(date) {
    const h = String(date.getHours()).padStart(2, '0')
    const m = String(date.getMinutes()).padStart(2, '0')
    return h + ':' + m
  },

  // 打开阶段选择
  onOpenPhaseSelector() {
    this.setData({ showPhaseSelector: true })
  },
  onClosePhaseSelector() {
    this.setData({ showPhaseSelector: false })
  },
  onPhaseSaved(e) {
    this.setData({
      showPhaseSelector: false,
      currentPhase: e.detail.name,
    })
    wx.showToast({ title: '阶段已保存，请重启', icon: 'none' })
  },
})
