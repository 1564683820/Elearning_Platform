/**
 * PPTX 设计系统 — 仿 Figma 组件化设计理念
 *
 * 提供布局常量、装饰组件、卡片系统、页面模板、图标管线等工具
 * 参考竞赛脚本 (generate_ppt.js) 的成熟设计模式
 *
 * 设计原则：
 *   1. Depth over flatness — 每个幻灯片至少 3 层视觉
 *   2. Color restraint — 每页最多 3-4 种颜色
 *   3. Typography hierarchy — 标题 > 副标题 > 正文 > 小字 > 微型
 *   4. Icon-first navigation — 每个板块有对应图标
 *   5. Consistent rhythm — 统一边距、卡片尺寸、间距
 */
const { PALETTES, SLIDE_ICONS, SLIDE_LABELS } = require("./pptx_theme_palettes");

// ========================= 布局常量 =========================
const L = {
  SLIDE_W: 10,
  SLIDE_H: 5.625,
  MARGIN: 0.5,
  CONTENT_W: 10 - 0.5 * 2,  // 9.0
};

// ========================= 字号体系 =========================
const FZ = {
  TITLE: 36,        // 封面主标题
  HEADING: 26,      // 内容页标题
  SUBHEADING: 20,   // 副标题/章节标题
  BODY: 14,         // 正文
  SMALL: 11,        // 辅助文字/选项
  TINY: 9,          // 注释/音标/页码
};

// ========================= 阴影预设 =========================
const SHADOW_CARD = { type: "outer", blur: 6, offset: 1.5, angle: 135, color: "000000", opacity: 0.10 };
const SHADOW_FEATURED = { type: "outer", blur: 8, offset: 2, angle: 135, color: "000000", opacity: 0.15 };
const SHADOW_TEXT = { type: "outer", blur: 8, offset: 2, angle: 135, color: "000000", opacity: 0.25 };

// ========================= 主题工具 =========================

/** 检测是否为深色背景主题（黑板/科技风格） */
function isDarkTheme(C) {
  if (!C || !C.bg) return false;
  // 浅色背景排除
  const lightPrefixes = ["fff", "faf", "f5f", "e8f", "fff3e0", "fff8e1", "f8f", "f0f"];
  if (lightPrefixes.some(p => C.bg.startsWith(p))) return false;
  // 深色背景检测：以 0/1/2 开头且非浅色
  return (C.bg.startsWith("0") || C.bg.startsWith("1") || C.bg.startsWith("2"));
}

/** 获取主题色板，fallback classic */
function getTheme(name) {
  return PALETTES[name] || PALETTES.classic;
}

// ========================= 图标管线 =========================

/** 图标管线是否已初始化 */
let _iconPipelineReady = false;

/** 预渲染图标缓存：{ iconName: "image/png;base64,..." } */
let _iconCache = {};

/**
 * 初始化图标管线（react-icons → SVG → sharp → PNG base64）
 * 首次调用时会加载依赖并预渲染所有教程图标
 */
async function initIconPipeline() {
  if (_iconPipelineReady) return _iconCache;

  const React = require("react");
  const ReactDOMServer = require("react-dom/server");
  const sharp = require("sharp");
  const {
    FaGraduationCap, FaLightbulb, FaBookOpen, FaComments,
    FaBrain, FaClipboardList, FaUsers, FaRobot, FaStar,
    FaMicrophoneAlt, FaCheckCircle, FaArrowRight,
    FaFilePowerpoint, FaLanguage, FaChartBar
  } = require("react-icons/fa");

  /** 将 react-icons 组件渲染为 base64 PNG */
  async function iconToDataUri(IconComponent, color, size = 256) {
    const svgStr = ReactDOMServer.renderToStaticMarkup(
      React.createElement(IconComponent, { color: `#${color}`, size: String(size) })
    );
    const pngBuf = await sharp(Buffer.from(svgStr)).png().toBuffer();
    return `image/png;base64,${pngBuf.toString("base64")}`;
  }

  // 预渲染所有 slide_type 对应的图标（白色 + primary 双版本）
  const iconMap = {
    title:       FaGraduationCap,
    objective:   FaLightbulb,
    vocabulary:  FaBookOpen,
    dialogue:    FaComments,
    grammar:     FaBrain,
    practice:    FaClipboardList,
    interactive: FaUsers,
    ai_interaction: FaRobot,
    summary:     FaStar,
    listening:   FaMicrophoneAlt,
    speaking:    FaMicrophoneAlt,
  };

  const classicPrimary = PALETTES.classic ? PALETTES.classic.primary : "5B9E6F";

  for (const [name, Icon] of Object.entries(iconMap)) {
    // 白底图标（用于彩色圆形内）
    _iconCache[`${name}_white`] = await iconToDataUri(Icon, "FFFFFF");
    // 主题色图标（用于浅色卡片内）
    _iconCache[`${name}_primary`] = await iconToDataUri(Icon, classicPrimary);
  }

  // 额外图标
  _iconCache["check_green"] = await iconToDataUri(FaCheckCircle, "2d7d46");
  _iconCache["check_primary"] = await iconToDataUri(FaCheckCircle, classicPrimary);
  _iconCache["arrow"] = await iconToDataUri(FaArrowRight, "888888");
  _iconCache["ppt"] = await iconToDataUri(FaFilePowerpoint, classicPrimary);

  _iconPipelineReady = true;
  return _iconCache;
}

/** 获取预渲染图标 data URI */
function getIcon(name) {
  return _iconCache[name] || null;
}

/** 获取 slide_type 对应的白色图标 */
function getSlideIcon(slideType) {
  return _iconCache[`${slideType}_white`] || null;
}

/** 获取 slide_type 对应的主题色图标 */
function getSlideIconPrimary(slideType) {
  return _iconCache[`${slideType}_primary`] || null;
}

// ========================= 装饰组件 =========================

/** 渐变背景（封面页）—— 用旋转矩形模拟渐变 */
function addGradientBg(s, p, c1, c2) {
  s.background = { color: c1 };
  s.addShape(p.shapes.RECTANGLE, {
    x: 5.5, y: -0.84, w: 6, h: 2.8,
    fill: { color: c2, transparency: 70 },
    rotate: 15,
  });
  s.addShape(p.shapes.RECTANGLE, {
    x: -2, y: 3.9, w: 5, h: 2.8,
    fill: { color: c2, transparency: 80 },
    rotate: -10,
  });
}

/** 页码：右下角 "3 / 10" */
function addPageNum(s, pageIndex, total, color) {
  s.addText(`${pageIndex + 1} / ${total}`, {
    x: 8.8, y: 5.25, w: 1.0, h: 0.25,
    fontSize: FZ.TINY, fontFace: "Calibri",
    color: color || "999999",
    align: "right", valign: "middle", margin: 0,
  });
}

/** 顶部细条 */
function addTopBar(s, p, color, h) {
  s.addShape(p.shapes.RECTANGLE, {
    x: 0, y: 0, w: L.SLIDE_W, h: h || 0.06,
    fill: { color },
  });
}

/** 底部细条 */
function addBottomBar(s, p, color, h) {
  s.addShape(p.shapes.RECTANGLE, {
    x: 0, y: L.SLIDE_H - (h || 0.06), w: L.SLIDE_W, h: h || 0.06,
    fill: { color },
  });
}

/** 基础卡片 — 圆角 + 阴影 + 可选边框 */
function addCard(s, p, x, y, w, h, bg, border, shadow) {
  const opts = {
    x, y, w, h,
    fill: { color: bg || "FFFFFF" },
    rectRadius: 0.12,
    shadow: shadow || SHADOW_CARD,
  };
  if (border) opts.line = { color: border, width: 0.5 };
  s.addShape(p.shapes.RECTANGLE, opts);
}

/** 带左侧色条的样式卡片（用于词汇/对话） */
function addStyledCard(s, p, x, y, w, h, color, bg) {
  addCard(s, p, x, y, w, h, bg);
  s.addShape(p.shapes.RECTANGLE, {
    x, y: y + 0.08, w: 0.06, h: h - 0.16,
    fill: { color },
    rectRadius: 0.03,
  });
}

/** 彩色圆形 + 白色图标（用于板块标题） */
function addIconCircle(s, p, x, y, sz, color, iconData) {
  // 半透明底色圆
  s.addShape(p.shapes.OVAL, {
    x, y, w: sz, h: sz,
    fill: { color, transparency: iconData ? 0 : 15 },
  });
  // 图标（如果有）
  if (iconData) {
    const pad = sz * 0.18;
    s.addImage({
      data: iconData,
      x: x + pad, y: y + pad,
      w: sz - pad * 2, h: sz - pad * 2,
    });
  }
}

/** 小圆点装饰 */
function addDot(s, p, x, y, sz, color) {
  s.addShape(p.shapes.OVAL, {
    x, y, w: sz, h: sz,
    fill: { color },
  });
}

/** 封面/分隔页的大圆装饰 */
function addCircleDeco(s, p, color, opacity) {
  s.addShape(p.shapes.OVAL, {
    x: 8.8, y: -0.6, w: 2.4, h: 2.4,
    fill: { color, transparency: opacity || 70 },
  });
  s.addShape(p.shapes.OVAL, {
    x: 8.2, y: -0.2, w: 1.2, h: 1.2,
    fill: { color, transparency: (opacity || 70) + 10 },
  });
}

/** 分割线 */
function addDivider(s, p, x, y, w, color) {
  s.addShape(p.shapes.LINE, {
    x, y, w, h: 0,
    line: { color: color || "E0E0E0", width: 1.5 },
  });
}

// ========================= 内容页头部 =========================

/**
 * 标准内容页头部：顶部色条 + 左侧强调竖条 + 标题 + 分割线 + 底部色条
 * @returns {{ contentY: number }} 内容区起始 Y 坐标
 */
function addPageHeader(s, p, title, C, subtitle, slideType) {
  const { MARGIN, SLIDE_W } = L;
  const isDark = isDarkTheme(C);

  addTopBar(s, p, C.primary, isDark ? 0.08 : 0.06);
  addBottomBar(s, p, C.primary, isDark ? 0.05 : 0.04);

  // 左侧强调色条
  s.addShape(p.shapes.RECTANGLE, {
    x: MARGIN, y: 0.15, w: 0.04, h: 0.5,
    fill: { color: isDark ? C.accent || C.primary : C.primary },
  });

  // 标题文字
  s.addText(title, {
    x: MARGIN + 0.15, y: 0.12, w: SLIDE_W - MARGIN * 2 - 0.15, h: 0.55,
    fontSize: FZ.HEADING, fontFace: C.fontHeading || "Georgia",
    color: C.heading, bold: true, margin: 0,
  });

  // 副标题（可选）
  if (subtitle) {
    s.addText(subtitle, {
      x: MARGIN + 0.15, y: 0.62, w: SLIDE_W - MARGIN * 2 - 0.15, h: 0.3,
      fontSize: FZ.SMALL, fontFace: C.fontBody || "Calibri",
      color: C.textLight, margin: 0,
    });
  }

  // 分割线
  const dividerColor = isDark ? (C.accent || C.primary) : C.primary;
  addDivider(s, p, MARGIN, 0.92, 2.5, dividerColor);

  // 右侧图标（如果有）
  if (slideType && _iconPipelineReady) {
    const icon = getSlideIcon(slideType);
    if (icon) {
      const ix = SLIDE_W - MARGIN - 0.45;
      addIconCircle(s, p, ix, 0.14, 0.45, C.primary, icon);
    }
  }

  return { contentY: 1.1 };
}

// ========================= 高级排版组件 =========================

/**
 * 编号步骤列表（用于 objectives / interactive pages）
 * 每个步骤 = 圆形序号 + 文字
 */
function addNumberedSteps(s, p, items, startX, startY, width, C, color) {
  const stepColor = color || C.accent || C.primary;
  const dotSize = 0.2;

  for (let i = 0; i < Math.min(items.length, 8); i++) {
    const y = startY + i * 0.45;
    // 圆形背景
    addDot(s, p, startX, y + 0.05, dotSize, stepColor);
    // 数字
    s.addText(String(i + 1), {
      x: startX, y: y + 0.05, w: dotSize, h: dotSize,
      fontSize: 11, fontFace: "Calibri",
      color: "FFFFFF", bold: true,
      align: "center", valign: "middle", margin: 0,
    });
    // 文字
    s.addText(items[i], {
      x: startX + dotSize + 0.2, y, w: width - dotSize - 0.2, h: 0.4,
      fontSize: FZ.BODY, fontFace: C.fontBody,
      color: C.text, valign: "middle", margin: 0,
    });
  }
}

/**
 * 选项按钮行（用于 practice / listening questions）
 */
function addOptionRow(s, p, options, correctIdx, x, y, w, C) {
  const optLabels = ["A", "B", "C", "D"];
  const optH = 0.2;
  const optGap = 0.05;

  for (let i = 0; i < Math.min(options.length, 4); i++) {
    const oy = y + i * (optH + optGap);
    const isCorrect = correctIdx !== undefined && correctIdx === i;

    // 选项背景
    s.addShape(p.shapes.RECTANGLE, {
      x: x + 0.15, y: oy, w: w - 0.3, h: optH,
      fill: { color: isCorrect ? "C8E6C9" : (C.bg2 || "F5F5F5") },
      rectRadius: 0.05,
    });
    // 标签 + 文字
    s.addText(`${optLabels[i]}. ${options[i]}`, {
      x: x + 0.35, y: oy, w: w - 0.55, h: optH,
      fontSize: FZ.SMALL, fontFace: C.fontBody,
      color: C.text, valign: "middle", margin: 0,
    });
  }
}

/**
 * 带图标的色块标签（用于活动类型 / 语法标签）
 */
function addBadge(s, p, text, x, y, w, h, C, color) {
  s.addShape(p.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: color || C.primary },
    rectRadius: 0.08,
  });
  s.addText(text, {
    x, y, w, h,
    fontSize: FZ.SMALL, fontFace: C.fontBody,
    color: "FFFFFF", bold: true,
    align: "center", valign: "middle", margin: 0,
  });
}

/**
 * 底部信息栏（用于关键提示/场景说明）
 */
function addInfoBar(s, p, textParts, x, y, w, h, C) {
  s.addShape(p.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: C.cardBg || "F5F5F5" },
    shadow: SHADOW_CARD,
    rectRadius: 0.06,
  });
  s.addText(textParts, {
    x: x + 0.15, y, w: w - 0.3, h,
    fontFace: C.fontBody, valign: "middle", margin: 0,
  });
}

// ========================= 导出 =========================

module.exports = {
  L, FZ, SHADOW_CARD, SHADOW_FEATURED, SHADOW_TEXT,
  getTheme, isDarkTheme,

  // 图标管线
  initIconPipeline, getIcon, getSlideIcon, getSlideIconPrimary,
  isPipelineReady: () => _iconPipelineReady,

  // 装饰组件
  addGradientBg, addPageNum, addTopBar, addBottomBar,
  addCard, addStyledCard, addIconCircle, addDot, addCircleDeco, addDivider,
  addPageHeader,

  // 高级排版组件
  addNumberedSteps, addOptionRow, addBadge, addInfoBar,
};
