// 阶段选择弹窗组件
// 展示所有学习阶段，供用户选择，保存后提示重启
const phaseMode = require('../../utils/phase-mode.js')

Component({
  properties: {
    // 当前选中的阶段索引
    currentPhase: {
      type: Number,
      value: 0,
    },
    // 是否显示弹窗
    visible: {
      type: Boolean,
      value: false,
    },
  },

  data: {
    phases: phaseMode.PHASES,
    selectedIndex: 0,
  },

  observers: {
    currentPhase(val) {
      if (val !== undefined && val !== null) {
        this.setData({ selectedIndex: val })
      }
    },
  },

  methods: {
    // 选择阶段
    onSelect(e) {
      const index = e.currentTarget.dataset.index
      this.setData({ selectedIndex: index })
    },

    // 取消选择
    onCancel() {
      this.setData({ selectedIndex: this.properties.currentPhase })
      this.triggerEvent('close')
    },

    // 保存并重启
    onSave() {
      const index = this.data.selectedIndex
      phaseMode.savePhaseIndex(index)
      const phaseName = phaseMode.PHASES[index].name
      this.triggerEvent('saved', { index, name: phaseName })
    },
  },
})
