// 幼儿启蒙首页
// 欢迎区 + 儿歌播放 + 更多儿歌列表
const phaseMode = require('../../../utils/phase-mode.js')

Page({
  data: {
    // 昵称
    nickname: '小朋友',
    // 当前播放状态
    isPlaying: false,
    currentSong: null,
    progressPercent: 0,
    playTime: '00:00 / 02:15',
    // 儿歌列表
    songs: [
      { id: 1, title: '小星星 English Song', subtitle: 'Twinkle twinkle little star', duration: '02:15' },
      { id: 2, title: 'Bingo Song', subtitle: 'There was a farmer had a dog', duration: '01:45' },
      { id: 3, title: 'ABC Song', subtitle: 'A B C D E F G', duration: '02:00' },
      { id: 4, title: 'Head Shoulders', subtitle: 'Head and shoulders knees and toes', duration: '01:30' },
    ],
    // 当前阶段名称
    currentPhase: '',
    // 阶段选择弹窗
    showPhaseSelector: false,
    // 保存提示弹窗
    showSaveTip: false,
    savedPhaseName: '',
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
    const name = phaseMode.PHASES[idx].name
    this.setData({ currentPhase: name })
  },

  // 播放/暂停儿歌
  onPlaySong(e) {
    const id = e.currentTarget.dataset.id
    const song = this.data.songs.find(s => s.id === id)
    if (!song) return

    if (this.data.currentSong && this.data.currentSong.id === id) {
      // 切换播放/暂停
      const isPlaying = !this.data.isPlaying
      this.setData({ isPlaying })
      if (isPlaying) {
        this.startProgress()
      } else {
        this.stopProgress()
      }
    } else {
      // 切换歌曲
      this.setData({ currentSong: song, isPlaying: true, progressPercent: 0 })
      this.startProgress()
    }
  },

  // 模拟播放进度
  progressTimer: null,
  startProgress() {
    this.stopProgress()
    this.progressTimer = setInterval(() => {
      let p = this.data.progressPercent + 1
      if (p > 95) {
        p = 0
        this.setData({ isPlaying: false })
        this.stopProgress()
      }
      this.setData({ progressPercent: p })
    }, 500)
  },
  stopProgress() {
    if (this.progressTimer) {
      clearInterval(this.progressTimer)
      this.progressTimer = null
    }
  },

  onUnload() {
    this.stopProgress()
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
    const { index, name } = e.detail
    this.setData({
      showPhaseSelector: false,
      showSaveTip: true,
      savedPhaseName: name,
      currentPhase: name,
    })
  },

  // 立即重启
  onRestartNow() {
    this.setData({ showSaveTip: false })
    wx.reLaunch({ url: '/pages/child/home/index' })
  },
})
