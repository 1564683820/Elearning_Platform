/**
 * PPTX 主题色板映射表
 * 
 * 从 server/app/services/ppt_theme_data.py 的 _THEME_STYLE_SKILLS
 * 提取核心色值，映射到 pptxgenjs 的色值格式（不含 # 号）
 * 
 * 使用方式:
 *   const THEME = require('./pptx_theme_palettes');
 *   const palette = THEME.PALETTES[themeName] || THEME.PALETTES.classic;
 */

// 8 套教学主题的 PPTX 色板
// 每套包含: 主色、渐变、卡片、对话、语法、装饰、字体
const PALETTES = {
  // ========== 经典简约 - 蓝白清新风 ==========
  classic: {
    primary: "2d7d46",        // 绿色主色
    primaryDark: "1b5e20",    // 深绿
    accent: "1565c0",         // 蓝色强调
    accentLight: "e3f2fd",    // 淡蓝
    gradientFrom: "1b5e20",   // 渐变起始（封面）
    gradientTo: "2d7d46",     // 渐变终止（封面）
    deco: "a5d6a7",           // 装饰元素色
    bg: "FFFFFF",             // 白色背景
    bg2: "f8faf8",           // 浅灰绿卡片背景
    bg3: "f0f7f0",           // 浅绿标题栏
    text: "2c3e50",           // 深蓝灰正文
    textSec: "546e7a",        // 中灰辅助文字
    textLight: "607d8b",      // 浅灰次要文字
    heading: "1b5e20",        // 标题色 - 深绿
    subtitle: "455a64",       // 副标题色
    cardBg: "f8faf8",        // 卡片背景
    border: "e0e0e0",         // 边框色
    warm: "fff8e1",           // 暖色强调（语法卡片）
    warmBorder: "ffe082",     // 暖色边框
    speakerA: "1565c0",       // 说话人A
    speakerB: "c62828",       // 说话人B
    rule: "d84315",           // 语法规则色
    success: "4caf50",        // 正确（练习答案）
    error: "f44336",          // 错误
    fontHeading: "Georgia",
    fontBody: "Calibri",
  },

  // ========== 小学卡通 - 明亮活泼风 ==========
  cartoon: {
    primary: "ff7043",        // 橙色主色
    primaryDark: "e64a19",    // 深橙
    accent: "42a5f5",         // 蓝色强调
    accentLight: "e3f2fd",
    gradientFrom: "e64a19",
    gradientTo: "ff7043",
    deco: "ffccbc",
    success: "4caf50",
    error: "f44336",
    bg: "fff8e1",             // 浅黄背景
    bg2: "fff3e0",            // 浅橙卡片
    bg3: "ffccbc",            // 浅橙标题栏
    text: "4e342e",           // 深棕正文
    textSec: "6d4c41",        // 中棕辅助
    textLight: "8d6e63",      // 浅棕
    heading: "bf360c",        // 标题 - 深橙红
    subtitle: "6d4c41",
    cardBg: "fff3e0",
    border: "ffccbc",
    warm: "fff8e1",
    warmBorder: "ffe0b2",
    speakerA: "42a5f5",
    speakerB: "e91e63",
    rule: "d84315",
    fontHeading: "Comic Sans MS",
    fontBody: "Comic Sans MS",
  },

  // ========== 初中简约 - 清新学术风 ==========
  academic: {
    primary: "1976d2",        // 蓝色主色
    primaryDark: "0d47a1",    // 深蓝
    accent: "388e3c",         // 绿色强调
    accentLight: "e8f5e9",
    gradientFrom: "0d47a1",
    gradientTo: "1976d2",
    deco: "bbdefb",
    success: "4caf50",
    error: "f44336",
    bg: "f5f7fa",             // 浅灰蓝背景
    bg2: "ffffff",            // 白色卡片
    bg3: "1976d2",            // 蓝色标题栏
    text: "2c3e50",
    textSec: "455a64",
    textLight: "607d8b",
    heading: "0d47a1",
    subtitle: "455a64",
    cardBg: "ffffff",
    border: "cfd8dc",
    warm: "fff8e1",
    warmBorder: "ffe082",
    speakerA: "1976d2",
    speakerB: "e64a19",
    rule: "0d47a1",
    fontHeading: "Georgia",
    fontBody: "Calibri",
  },

  // ========== 高中学术 - 深色严谨风 ==========
  senior: {
    primary: "37474f",        // 深灰主色
    primaryDark: "1a237e",    // 深蓝
    accent: "d32f2f",         // 红色强调
    accentLight: "ffebee",
    gradientFrom: "1a237e",
    gradientTo: "37474f",
    deco: "90a4ae",
    success: "4caf50",
    error: "f44336",
    bg: "ffffff",
    bg2: "fafafa",
    bg3: "37474f",            // 深灰标题栏
    text: "263238",
    textSec: "455a64",
    textLight: "607d8b",
    heading: "1a237e",
    subtitle: "455a64",
    cardBg: "fafafa",
    border: "cfd8dc",
    warm: "fafafa",
    warmBorder: "e0e0e0",
    speakerA: "37474f",
    speakerB: "c62828",
    rule: "1a237e",
    fontHeading: "Georgia",
    fontBody: "Calibri",
  },

  // ========== 黑板风格 - 传统课堂风 ==========
  blackboard: {
    primary: "a5d6a7",        // 浅绿粉笔
    primaryDark: "1b5e20",
    accent: "fff176",         // 黄色强调
    accentLight: "ffee58",
    gradientFrom: "1b5e20",
    gradientTo: "388e3c",
    deco: "c8e6c9",
    success: "81c784",
    error: "ef9a9a",
    bg: "2e7d32",             // 深绿黑板
    bg2: "388e3c",            // 稍亮绿
    bg3: "2e7d32",            // 同背景
    text: "ffffff",           // 白色粉笔字
    textSec: "e8f5e9",        // 浅绿辅助
    textLight: "c8e6c9",      // 更浅绿
    heading: "ffffff",
    subtitle: "e8f5e9",
    cardBg: "388e3c",
    border: "4caf50",
    warm: "2e7d32",
    warmBorder: "4caf50",
    speakerA: "a5d6a7",
    speakerB: "fff176",
    rule: "fff176",
    fontHeading: "KaiTi",
    fontBody: "KaiTi",
  },

  // ========== 暖色温馨 - 柔和启蒙风 ==========
  warm: {
    primary: "ff7043",        // 暖橙主色
    primaryDark: "bf360c",
    accent: "ec407a",         // 粉色强调
    accentLight: "fce4ec",
    gradientFrom: "bf360c",
    gradientTo: "ff7043",
    deco: "ffab91",
    success: "4caf50",
    error: "f44336",
    bg: "fff3e0",             // 暖米背景
    bg2: "fff3e0",
    bg3: "fff3e0",
    text: "4e342e",           // 深棕
    textSec: "6d4c41",
    textLight: "8d6e63",
    heading: "bf360c",
    subtitle: "6d4c41",
    cardBg: "fff3e0",
    border: "ffab91",
    warm: "fff3e0",
    warmBorder: "ffab91",
    speakerA: "ff7043",
    speakerB: "ec407a",
    rule: "bf360c",
    fontHeading: "Georgia",
    fontBody: "Calibri",
  },

  // ========== 科技蓝调 - 未来科技风 ==========
  tech: {
    primary: "42a5f5",        // 亮蓝主色
    primaryDark: "0d47a1",
    accent: "00e5ff",         // 荧光青强调
    accentLight: "80deea",
    gradientFrom: "0d47a1",
    gradientTo: "1a237e",
    deco: "80deea",
    success: "00e676",
    error: "ff1744",
    bg: "0a1628",             // 深蓝黑背景
    bg2: "1a237e",            // 深蓝卡片
    bg3: "0d47a1",
    text: "e8f0ff",           // 亮白蓝文字
    textSec: "90caf9",
    textLight: "64b5f6",
    heading: "e8f0ff",
    subtitle: "90caf9",
    cardBg: "1a237e",
    border: "1565c0",
    warm: "0d47a1",
    warmBorder: "1565c0",
    speakerA: "42a5f5",
    speakerB: "00e5ff",
    rule: "00e5ff",
    fontHeading: "Segoe UI",
    fontBody: "Segoe UI",
  },

  // ========== 自然绿意 - 清新生态风 ==========
  nature: {
    primary: "43a047",        // 绿主色
    primaryDark: "1b5e20",
    accent: "ef6c00",         // 橙强调
    accentLight: "fff3e0",
    gradientFrom: "1b5e20",
    gradientTo: "43a047",
    deco: "a5d6a7",
    success: "4caf50",
    error: "f44336",
    bg: "e8f5e9",             // 浅绿背景
    bg2: "c8e6c9",            // 淡绿
    bg3: "a5d6a7",
    text: "1b5e20",           // 深绿
    textSec: "2e7d32",
    textLight: "388e3c",
    heading: "1b5e20",
    subtitle: "2e7d32",
    cardBg: "c8e6c9",
    border: "81c784",
    warm: "fff3e0",
    warmBorder: "ffcc80",
    speakerA: "43a047",
    speakerB: "ef6c00",
    rule: "ef6c00",
    fontHeading: "Georgia",
    fontBody: "Calibri",
  },

  // ========== 商务专业 - 灰调商务风 ==========
  business: {
    primary: "607d8b",        // 灰蓝主色
    primaryDark: "37474f",
    accent: "e65100",         // 橙强调
    accentLight: "fff3e0",
    gradientFrom: "37474f",
    gradientTo: "607d8b",
    deco: "b0bec5",
    success: "4caf50",
    error: "f44336",
    bg: "fafafa",             // 近白背景
    bg2: "eceff1",            // 浅灰
    bg3: "607d8b",
    text: "37474f",
    textSec: "546e7a",
    textLight: "607d8b",
    heading: "37474f",
    subtitle: "546e7a",
    cardBg: "ffffff",
    border: "bdbdbd",
    warm: "fff3e0",
    warmBorder: "ffcc80",
    speakerA: "607d8b",
    speakerB: "e65100",
    rule: "e65100",
    fontHeading: "Segoe UI",
    fontBody: "Segoe UI",
  },
};

// 各 slide_type 对应图标名称（react-icons/fa）
const SLIDE_ICONS = {
  title:       "FaGraduationCap",
  objective:   "FaLightbulb",
  vocabulary:  "FaBookOpen",
  dialogue:    "FaComments",
  grammar:     "FaBrain",
  practice:    "FaClipboardList",
  interactive: "FaUsers",
  ai_interaction: "FaRobot",
  summary:     "FaStar",
  listening:   "FaMicrophoneAlt",
  speaking:    "FaMicrophoneAlt",
};

// 各 slide_type 的中文标签
const SLIDE_LABELS = {
  title:       "标题页",
  objective:   "学习目标",
  vocabulary:  "词汇展示",
  dialogue:    "对话练习",
  grammar:     "语法讲解",
  practice:    "课堂练习",
  interactive: "互动活动",
  ai_interaction: "人机互动",
  summary:     "总结回顾",
  listening:   "听力练习",
  speaking:    "口语跟读",
};

module.exports = { PALETTES, SLIDE_ICONS, SLIDE_LABELS };
