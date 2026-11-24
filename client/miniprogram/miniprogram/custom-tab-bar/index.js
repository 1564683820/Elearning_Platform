// 自定义底部导航栏组件
// 根据学习阶段模式动态切换 Tab 配置
const phaseMode = require('../utils/phase-mode.js')

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
    currentMode: 'student',
  },

  lifetimes: {
    attached() {
      this.loadTabs()
    },
  },

  // 页面显示时可能切换模式
  pageLifetimes: {
    show() {
      this.loadTabs()
    },
  },

  methods: {
    // 加载当前模式的 Tab 配置
    loadTabs() {
      const app = getApp()
      // 优先从 globalData 当前用户角色判断，教师走 teacher 模式
      const userRole = app?.globalData?.userRole || ''
      let mode = phaseMode.getSavedMode()
      if (userRole === 'teacher') {
        mode = 'teacher'
      }
      const tabs = phaseMode.MODES[mode] ? phaseMode.MODES[mode].tabs : phaseMode.MODES.student.tabs
      this.setData({ tabs, currentMode: mode })
    },

    // 切换 Tab
    onTabTap(e) {
      const index = e.currentTarget.dataset.index
      const pagePath = this.data.tabs[index].pagePath
      const mode = this.data.currentMode
      if (mode === 'teacher') {
        // 教师端页面不是原生 tabBar，需用 redirectTo
        wx.redirectTo({ url: pagePath })
      } else {
        wx.switchTab({ url: pagePath })
      }
    },
  },
})
