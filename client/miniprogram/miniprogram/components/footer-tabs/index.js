// 底部导航栏组件（用于幼儿/成人模式）
// 根据当前模式渲染对应的 Tab 列表
const phaseMode = require('../../utils/phase-mode.js')

// Tab 图标映射
const TAB_ICONS = {
  home: '🏠',
  book: '📖',
  robot: '🤖',
  user: '👤',
  chat: '💬',
  news: '📰',
}

Component({
  properties: {
    // 当前激活的 tab 索引
    activeIndex: {
      type: Number,
      value: 0,
    },
  },

  data: {
    tabs: [],
  },

  lifetimes: {
    attached() {
      this.loadTabs()
    },
  },

  methods: {
    // 加载当前模式的 Tab 列表
    loadTabs() {
      const mode = phaseMode.getSavedMode()
      const tabs = phaseMode.MODES[mode] ? phaseMode.MODES[mode].tabs : phaseMode.MODES.student.tabs
      this.setData({ tabs })
    },

    // 点击 Tab 切换页面
    onTabTap(e) {
      const index = e.currentTarget.dataset.index
      const pagePath = this.data.tabs[index].pagePath
      wx.reLaunch({ url: pagePath })
    },
  },
})
