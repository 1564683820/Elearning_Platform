// 视觉风格配置 — 与后端 VisualStyleEngine.STYLE_REGISTRY 的 9 种风格对应
// 后端 key: swiss-minimal, soft-rounded, editorial, dark-tech,
//          sketch-notes, chalkboard, glassmorphism, paper-cut, warm-simple

export interface VisualStyleItem {
  /** 后端识别的风格 key */
  name: string;
  /** 中文显示名 */
  label: string;
  /** 一句话描述 */
  desc: string;
  /** 预览 emoji 图标 */
  icon: string;
  /** 主色调（卡片选中高亮） */
  color: string;
  /** 副色调 / 背景色 */
  bgColor: string;
  /** 风格关键词标签 */
  tags: string[];
}

export const VISUAL_STYLES: VisualStyleItem[] = [
  {
    name: 'warm-simple',
    label: '温暖简约',
    desc: '圆角卡片 + 柔和阴影，亲切自然',
    icon: '☀️',
    color: '#f59e0b',
    bgColor: '#fffbeb',
    tags: ['通用', '柔和'],
  },
  {
    name: 'swiss-minimal',
    label: '瑞士极简',
    desc: '直角卡片 + 无阴影，干净利落的信息层次',
    icon: '📐',
    color: '#4f46e5',
    bgColor: '#eef2ff',
    tags: ['学术', '清晰'],
  },
  {
    name: 'soft-rounded',
    label: '圆润可爱',
    desc: '大圆角 + 浅阴影 + 圆形装饰，亲和力强',
    icon: '🔵',
    color: '#06b6d4',
    bgColor: '#ecfeff',
    tags: ['低年级', '活泼'],
  },
  {
    name: 'editorial',
    label: '编辑风格',
    desc: '衬线标题 + 网格背景 + 点缀分隔线，杂志感',
    icon: '📰',
    color: '#8b5cf6',
    bgColor: '#f5f3ff',
    tags: ['文艺', '美观'],
  },
  {
    name: 'dark-tech',
    label: '暗色科技',
    desc: '深色网格 + 发光边框，科技感与沉浸感',
    icon: '🌙',
    color: '#0f172a',
    bgColor: '#f8fafc',
    tags: ['高中', '沉稳'],
  },
  {
    name: 'sketch-notes',
    label: '手绘笔记',
    desc: '手写字体 + 网格纸背景，课堂涂鸦风格',
    icon: '✏️',
    color: '#d97706',
    bgColor: '#fff7ed',
    tags: ['创意', '自由'],
  },
  {
    name: 'chalkboard',
    label: '粉笔黑板',
    desc: '粉笔质感字体 + 黑板暗色背景，复古教学感',
    icon: '🧑‍🏫',
    color: '#1e293b',
    bgColor: '#f1f5f9',
    tags: ['复古', '课堂'],
  },
  {
    name: 'glassmorphism',
    label: '毛玻璃',
    desc: '半透明磨砂卡片 + 发光背景，现代视觉层次',
    icon: '🪟',
    color: '#0891b2',
    bgColor: '#f0fdfa',
    tags: ['现代', '质感'],
  },
  {
    name: 'paper-cut',
    label: '剪纸风格',
    desc: '粗线条边框 + 剪纸阴影，立体层次感',
    icon: '✂️',
    color: '#dc2626',
    bgColor: '#fef2f2',
    tags: ['传统', '艺术'],
  },
];

/** 默认风格（与后端 DEFAULT_STYLE 一致） */
export const DEFAULT_VISUAL_STYLE = 'warm-simple';

/** 根据 name 获取单个风格的快捷方法 */
export function getVisualStyle(name: string): VisualStyleItem {
  return VISUAL_STYLES.find((s) => s.name === name) ?? VISUAL_STYLES[0];
}
