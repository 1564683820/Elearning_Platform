// 多界面模式管理工具
// 定义学习阶段与界面模式的映射关系

// 学习阶段列表：索引、名称、归属模式、描述
const PHASES = [
  { index: 0, name: '幼儿启蒙', mode: 'child', desc: '适合3-6岁儿童', color: '#F97316' },
  { index: 1, name: '小学',     mode: 'student', desc: '适合6-12岁',    color: '#5B9E6F' },
  { index: 2, name: '初中',     mode: 'student', desc: '适合12-15岁',   color: '#8B5CF6' },
  { index: 3, name: '高中',     mode: 'student', desc: '适合15-18岁',   color: '#EC4899' },
  { index: 4, name: '四六级',   mode: 'student', desc: '大学英语考试',   color: '#3B82F6' },
  { index: 5, name: '成人自学', mode: 'adult',   desc: '自主学习，不限内容', color: '#5B9E6F' },
]

// 界面模式信息
const MODES = {
  child: {
    name: '幼儿启蒙',
    tabs: [
      { text: '首页', icon: 'home', pagePath: '/pages/child/home/index' },
      { text: '识词', icon: 'book', pagePath: '/pages/child/word/index' },
      { text: '小e', icon: 'robot', pagePath: '/pages/child/chat/index' },
      { text: '我的', icon: 'user', pagePath: '/pages/profile/index/index' },
    ],
  },
  student: {
    name: '学生学习',
    tabs: [
      { text: '首页', icon: 'home', pagePath: '/pages/home/index' },
      { text: '智能对话', icon: 'chat', pagePath: '/pages/chat/qa/index' },
      { text: '我的', icon: 'user', pagePath: '/pages/profile/index/index' },
    ],
  },
  adult: {
    name: '成人自学',
    tabs: [
      { text: '首页', icon: 'home', pagePath: '/pages/adult/home/index' },
      { text: '新闻', icon: 'news', pagePath: '/pages/adult/news/index' },
      { text: '小e', icon: 'robot', pagePath: '/pages/chat/qa/index' },
      { text: '我的', icon: 'user', pagePath: '/pages/profile/index/index' },
    ],
  },
  teacher: {
    name: '教师工作台',
    tabs: [
      { text: '班级', icon: 'class', pagePath: '/pages/teacher/class/index' },
      { text: '批卷', icon: 'exam', pagePath: '/pages/teacher/exam/index' },
      { text: '我的', icon: 'user', pagePath: '/pages/teacher/profile/index' },
    ],
  },
}

// 阶段索引 → 模式映射
// 参数: phaseIndex - 阶段索引(0-5)
// 返回: 模式标识字符串(child/student/adult)
function getModeByPhase(phaseIndex) {
  const phase = PHASES.find(p => p.index === phaseIndex)
  return phase ? phase.mode : 'student'
}

// 获取当前保存的学习阶段索引
// 返回: 阶段索引，默认0(幼儿启蒙)
function getSavedPhaseIndex() {
  try {
    const saved = wx.getStorageSync('learningPhase')
    if (saved !== '' && saved !== undefined && saved !== null) {
      const idx = parseInt(saved, 10)
      if (idx >= 0 && idx < PHASES.length) return idx
    }
  } catch (e) {
    // 存储读取失败，返回默认值
  }
  return 0
}

// 保存学习阶段
// 参数: index - 阶段索引(0-5)
function savePhaseIndex(index) {
  wx.setStorageSync('learningPhase', index)
}

// 获取当前保存的模式
function getSavedMode() {
  return getModeByPhase(getSavedPhaseIndex())
}

// 获取阶段名称列表
function getPhaseNames() {
  return PHASES.map(p => p.name)
}

// 根据名称查找阶段
// 参数: name - 阶段名称
// 返回: 阶段对象或undefined
function findPhaseByName(name) {
  return PHASES.find(p => p.name === name)
}

// 获取阶段索引（通过名称）
// 参数: name - 阶段名称
// 返回: 阶段索引，未找到返回0
function getPhaseIndexByName(name) {
  const phase = findPhaseByName(name)
  return phase ? phase.index : 0
}

module.exports = {
  PHASES,
  MODES,
  getModeByPhase,
  getSavedPhaseIndex,
  savePhaseIndex,
  getSavedMode,
  getPhaseNames,
  findPhaseByName,
  getPhaseIndexByName,
}
