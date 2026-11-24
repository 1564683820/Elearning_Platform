/**
 * AI 备课 PPT → .pptx 导出脚本（竞赛级品质版 v2.0）
 *
 * 使用 pptxgenjs + react-icons/sharp 图标管线 + 设计系统生成专业课件
 * 设计依据: .codebuddy/skills/ppt-generation/SKILL.md
 *
 * 视觉层次（每页至少 3 层）:
 *   L1 背景 — 纯色+渐变+大圆装饰
 *   L2 结构 — 顶/底色条+标题栏+左强调条+分割线
 *   L3 内容 — 卡片+图标+阴影+多风格文字
 *
 * 用法:
 *   node scripts/export_pptx.js <pages_json_path> <theme_name> [title] [output_path]
 */

const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");
const {
  L, FZ, SHADOW_CARD, getTheme, isDarkTheme,
  initIconPipeline, getSlideIcon, isPipelineReady,
  addGradientBg, addPageNum, addTopBar, addBottomBar,
  addCard, addStyledCard, addIconCircle, addDot, addCircleDeco, addDivider,
  addPageHeader, addNumberedSteps, addOptionRow, addBadge,
} = require("./pptx_design_system");
const { SLIDE_LABELS } = require("./pptx_theme_palettes");

const SLIDE_W = L.SLIDE_W, SLIDE_H = L.SLIDE_H, MARGIN = L.MARGIN;
const CONTENT_W = L.CONTENT_W;

/** 全局图标缓存引用（main() 中设置） */
let _iconCache = {};

function getCF(content, field, fallback) {
  if (!content || typeof content !== "object") return fallback;
  return content[field] !== undefined ? content[field] : fallback;
}

// =============================== 渲染器 ===============================

/** 封面页 — 深色渐变+大圆装饰+左侧竖条+标题阴影+分割线 (参考竞赛 S1) */
function renderTitle(pres, slide, page, C) {
  const content = page.content || {};
  const main = getCF(content, "main_title", page.title);
  const sub = getCF(content, "subtitle", "");
  const grade = getCF(content, "grade", "");

  addGradientBg(slide, pres, C.primaryDark || C.primary, C.primary);
  addTopBar(slide, pres, C.primary, 0.08);
  addBottomBar(slide, pres, C.primaryDark || C.primary, 0.06);
  addCircleDeco(slide, pres, "FFFFFF", 75);

  // 左侧强调竖条
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 1.0, w: 0.07, h: 2.8,
    fill: { color: "FFFFFF", transparency: 30 },
  });

  // 左下角圆形装饰
  slide.addShape(pres.shapes.OVAL, {
    x: -0.6, y: 3.9, w: 2.0, h: 2.0,
    fill: { color: "FFFFFF", transparency: 88 },
  });

  // 主标题（带阴影）
  slide.addText(main, {
    x: 1.1, y: 1.2, w: 7.5, h: 1.0,
    fontSize: FZ.TITLE, fontFace: C.fontHeading,
    color: "FFFFFF", bold: true, margin: 0,
    shadow: { type: "outer", blur: 8, offset: 2, color: "000", opacity: 0.25 },
  });

  if (sub) {
    slide.addText(sub, {
      x: 1.1, y: 2.3, w: 7, h: 0.55,
      fontSize: FZ.SUBHEADING, fontFace: C.fontBody,
      color: "FFFFFF", margin: 0,
    });
  }

  if (grade) {
    slide.addText(grade, {
      x: 1.1, y: 2.85, w: 5, h: 0.3,
      fontSize: FZ.TINY, fontFace: C.fontBody,
      color: "FFFFFF", transparency: 35, margin: 0,
    });
  }

  addDivider(slide, pres, 1.1, 3.35, 3.0, "FFFFFF");
  addPageNum(slide, 0, 1, "FFFFFF");
}

/** 学习目标 — 图标标题 + 编号圆点列表 */
function renderObjective(pres, slide, page, C) {
  addPageHeader(slide, pres, page.title || "学习目标", C, null, "objective");
  const items = getCF(page.content, "items", []);
  if (!items.length) return;

  addNumberedSteps(slide, pres, items, MARGIN, 1.15, CONTENT_W, C, C.primary);

  // 右下角装饰圆
  const decoIcon = getSlideIcon("objective");
  if (decoIcon) {
    slide.addShape(pres.shapes.OVAL, {
      x: SLIDE_W - 1.3, y: SLIDE_H - 1.6, w: 1.1, h: 1.1,
      fill: { color: C.primary, transparency: 92 },
    });
  }
  addPageNum(slide, 0, 0, C.textLight);
}

/** 词汇展示 — 每词一张带左侧色条的样式卡片 */
function renderVocabulary(pres, slide, page, C) {
  addPageHeader(slide, pres, page.title || "词汇学习", C);
  const words = getCF(page.content, "words", []);
  if (!words.length) return;
  const cardH = 1.0;

  for (let i = 0; i < Math.min(words.length, 6); i++) {
    const wd = words[i], y = 1.15 + i * (cardH + 0.15);
    addStyledCard(slide, pres, MARGIN, y, CONTENT_W, cardH, C.primary, C.cardBg);

    const wordT = wd.word || "";
    const ph = wd.phonetic ? `  ${wd.phonetic}` : "";
    slide.addText([
      { text: wordT, options: { fontSize: 15, fontFace: C.fontBody, color: C.heading, bold: true } },
      { text: ph, options: { fontSize: 10, fontFace: C.fontBody, color: C.textLight } },
    ], {
      x: MARGIN + 0.2, y: y + 0.05, w: CONTENT_W - 0.4, h: 0.35,
      valign: "middle", margin: 0,
    });

    const detail = (wd.translation || "") + (wd.example ? `  — ${wd.example}` : "");
    slide.addText(detail, {
      x: MARGIN + 0.2, y: y + 0.45, w: CONTENT_W - 0.4, h: 0.45,
      fontSize: FZ.SMALL, fontFace: C.fontBody,
      color: C.textSec, valign: "top", margin: 0,
    });
  }
  addPageNum(slide, 0, 1, C.textLight);
}

/** 对话练习 — 左右交替气泡 + 彩色左侧条 */
function renderDialogue(pres, slide, page, C) {
  addPageHeader(slide, pres, page.title || "对话练习", C);
  const dlist = getCF(page.content, "dialogues", []);
  if (!dlist.length) return;
  const bH = 0.75;

  for (let i = 0; i < Math.min(dlist.length, 6); i++) {
    const d = dlist[i], y = 1.2 + i * (bH + 0.12);
    const isA = (d.speaker === "A" || d.speaker === "Teacher" || i % 2 === 0);
    const bc = isA ? C.speakerA : C.speakerB;
    const bx = isA ? MARGIN : MARGIN + 1.5;
    const bw = CONTENT_W - 1.5;

    // 气泡背景
    slide.addShape(pres.shapes.RECTANGLE, {
      x: bx, y, w: bw, h: bH,
      fill: { color: bc, transparency: 88 },
      rectRadius: 0.12,
    });
    // 左侧色条
    slide.addShape(pres.shapes.RECTANGLE, {
      x: bx, y, w: 0.05, h: bH,
      fill: { color: bc },
      rectRadius: 0.02,
    });

    slide.addText(d.speaker || (isA ? "A" : "B"), {
      x: bx + 0.2, y: y + 0.03, w: bw - 0.3, h: 0.2,
      fontSize: FZ.SMALL, fontFace: C.fontBody,
      color: bc, bold: true, margin: 0,
    });
    slide.addText(d.text || "", {
      x: bx + 0.2, y: y + 0.25, w: bw - 0.3, h: 0.25,
      fontSize: 13, fontFace: C.fontBody,
      color: C.text, margin: 0,
    });
    if (d.translation) {
      slide.addText(d.translation, {
        x: bx + 0.2, y: y + 0.52, w: bw - 0.3, h: 0.18,
        fontSize: FZ.TINY, fontFace: C.fontBody,
        color: C.textLight, italic: true, margin: 0,
      });
    }
  }
  addPageNum(slide, 0, 1, C.textLight);
}

/** 语法讲解 — 带边框的规则卡片 + 举例 + 说明 */
function renderGrammar(pres, slide, page, C) {
  addPageHeader(slide, pres, page.title || "语法讲解", C);
  const pts = getCF(page.content, "points", []);
  if (!pts.length) return;
  const ptH = 1.25;

  for (let i = 0; i < Math.min(pts.length, 4); i++) {
    const pt = pts[i], y = 1.15 + i * (ptH + 0.15);
    addCard(slide, pres, MARGIN, y, CONTENT_W, ptH, C.warm, C.warmBorder);
    slide.addText(pt.rule || "", {
      x: MARGIN + 0.25, y: y + 0.08, w: CONTENT_W - 0.5, h: 0.3,
      fontSize: 14, fontFace: C.fontBody,
      color: C.rule, bold: true, margin: 0,
    });

    const ex = typeof pt.example === "string"
      ? pt.example
      : Array.isArray(pt.example) ? pt.example.join("\n") : "";
    if (ex) {
      slide.addText(ex, {
        x: MARGIN + 0.25, y: y + 0.42, w: CONTENT_W - 0.5, h: 0.35,
        fontSize: 12, fontFace: C.fontBody,
        color: C.textSec, italic: true, margin: 0,
      });
    }
    if (pt.explanation) {
      slide.addText(pt.explanation, {
        x: MARGIN + 0.25, y: y + 0.82, w: CONTENT_W - 0.5, h: 0.35,
        fontSize: FZ.TINY, fontFace: C.fontBody,
        color: C.textLight, margin: 0,
      });
    }
  }
  addPageNum(slide, 0, 1, C.textLight);
}

/** 课堂练习 — 题目卡片 + 选项行 + 正确答案高亮 */
function renderPractice(pres, slide, page, C) {
  addPageHeader(slide, pres, page.title || "课堂练习", C, null, "practice");
  const qs = getCF(page.content, "questions", []);
  if (!qs.length) return;
  const qH = 1.05;
  const qGap = 0.1;

  for (let i = 0; i < Math.min(qs.length, 4); i++) {
    const q = qs[i], y = 1.15 + i * (qH + qGap);
    addCard(slide, pres, MARGIN, y, CONTENT_W, qH, C.cardBg);

    slide.addText(`${i + 1}. ${q.stem || ""}`, {
      x: MARGIN + 0.18, y: y + 0.06, w: CONTENT_W - 0.36, h: 0.26,
      fontSize: 13, fontFace: C.fontBody,
      color: C.text, bold: true, valign: "middle", margin: 0,
    });

    const options = q.options || [];
    if (options.length) {
      addOptionRow(slide, pres, options, q.answer, MARGIN, y + 0.34, CONTENT_W, C);
    }
  }
  addPageNum(slide, 0, 0, C.textLight);
}

/** 互动活动 — 活动类型标签 + 步骤编号列表 */
function renderInteractive(pres, slide, page, C) {
  addPageHeader(slide, pres, page.title || "互动活动", C);
  const content = page.content || {};
  const at = getCF(content, "activity_type", "game");
  const desc = getCF(content, "description", "");
  const steps = getCF(content, "steps", []);

  // 活动类型标签
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN, y: 1.15, w: 2.0, h: 0.35,
    fill: { color: C.primary }, rectRadius: 0.08,
  });
  slide.addText(at.toUpperCase(), {
    x: MARGIN, y: 1.15, w: 2.0, h: 0.35,
    fontSize: FZ.SMALL, fontFace: C.fontBody,
    color: "FFFFFF", bold: true,
    align: "center", valign: "middle", margin: 0,
  });
  if (desc) {
    slide.addText(desc, {
      x: MARGIN + 2.3, y: 1.15, w: CONTENT_W - 2.3, h: 0.35,
      fontSize: 13, fontFace: C.fontBody,
      color: C.textSec, valign: "middle", margin: 0,
    });
  }

  for (let i = 0; i < Math.min(steps.length, 5); i++) {
    const y = 1.8 + i * 0.6;
    const ns = 0.35;
    const cc = C.accent || C.primary;
    addIconCircle(slide, pres, MARGIN, y + 0.04, ns, cc);
    slide.addText(String(i + 1), {
      x: MARGIN, y: y + 0.04, w: ns, h: ns,
      fontSize: 14, fontFace: C.fontBody,
      color: "FFFFFF", bold: true,
      align: "center", valign: "middle", margin: 0,
    });
    slide.addText(steps[i], {
      x: MARGIN + 0.55, y, w: CONTENT_W - 0.55, h: 0.45,
      fontSize: FZ.BODY, fontFace: C.fontBody,
      color: C.text, valign: "middle", margin: 0,
    });
  }
  addPageNum(slide, 0, 1, C.textLight);
}

/** 人机互动 — Prompt 高亮 + 问题卡片列表 */
function renderAiInteraction(pres, slide, page, C) {
  addPageHeader(slide, pres, page.title || "AI 互动", C);
  const content = page.content || {};
  const prompt = getCF(content, "prompt", "");
  const questions = getCF(content, "questions", []);

  if (prompt) {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN, y: 1.1, w: CONTENT_W, h: 0.5,
      fill: { color: C.primary, transparency: 85 },
      rectRadius: 0.1,
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN, y: 1.1, w: 0.06, h: 0.5,
      fill: { color: C.primary },
    });
    slide.addText(prompt, {
      x: MARGIN + 0.2, y: 1.1, w: CONTENT_W - 0.4, h: 0.5,
      fontSize: 14, fontFace: C.fontBody,
      color: C.text, bold: true, valign: "middle", margin: 0,
    });
  }

  const startY = prompt ? 1.85 : 1.3;
  for (let i = 0; i < Math.min(questions.length, 5); i++) {
    const q = questions[i], y = startY + i * 0.55;
    const qt = q.question || q.title || `问题 ${i + 1}`;
    addCard(slide, pres, MARGIN, y, CONTENT_W, 0.48, C.cardBg);
    slide.addText(`Q${i + 1}: ${qt}`, {
      x: MARGIN + 0.2, y: y + 0.03, w: CONTENT_W - 0.4, h: 0.22,
      fontSize: 12, fontFace: C.fontBody,
      color: C.text, bold: true, margin: 0,
    });
    if (q.hint) {
      slide.addText(`提示: ${q.hint}`, {
        x: MARGIN + 0.3, y: y + 0.27, w: CONTENT_W - 0.5, h: 0.17,
        fontSize: FZ.TINY, fontFace: C.fontBody,
        color: C.textLight, margin: 0,
      });
    }
  }
  addPageNum(slide, 0, 1, C.textLight);
}

/** 总结回顾 — 核心要点圆点列表 + 课后作业卡片 */
function renderSummary(pres, slide, page, C) {
  addPageHeader(slide, pres, page.title || "总结回顾", C);
  const content = page.content || {};
  const kps = getCF(content, "key_points", []);
  const hw = getCF(content, "homework", "");

  slide.addText("核心要点", {
    x: MARGIN, y: 1.1, w: 4, h: 0.35,
    fontSize: 15, fontFace: C.fontBody,
    color: C.text, bold: true, margin: 0,
  });

  for (let i = 0; i < Math.min(kps.length, 7); i++) {
    const y = 1.55 + i * 0.32;
    const ds = 0.1;
    addDot(slide, pres, MARGIN + 0.1, y + 0.1, ds, C.primary);
    slide.addText(kps[i], {
      x: MARGIN + 0.35, y, w: CONTENT_W - 0.35, h: 0.28,
      fontSize: 13, fontFace: C.fontBody,
      color: C.text, valign: "middle", margin: 0,
    });
  }

  if (hw) {
    const hy = Math.max(1.55 + kps.length * 0.32 + 0.3, 4.0);
    addCard(slide, pres, MARGIN, hy, CONTENT_W, 0.6, C.warm, C.warmBorder);
    slide.addText([
      { text: "课后作业  ", options: { bold: true, fontSize: 13, color: C.rule } },
      { text: hw, options: { fontSize: 12, color: C.textSec } },
    ], {
      x: MARGIN + 0.2, y: hy + 0.05, w: CONTENT_W - 0.4, h: 0.5,
      fontFace: C.fontBody, valign: "middle", margin: 0,
    });
  }
  addPageNum(slide, 0, 1, C.textLight);
}

/** 听力练习 — 播放按钮 + 音频文本 + 题目 */
function renderListening(pres, slide, page, C) {
  addPageHeader(slide, pres, page.title || "听力练习", C);
  const content = page.content || {};
  const audioText = getCF(content, "audio_text", "");
  const subtitle = getCF(content, "subtitle", "");
  const questions = getCF(content, "questions", []);
  const optLabels = ["A", "B", "C", "D"];

  // 播放按钮
  addIconCircle(slide, pres, MARGIN, 1.1, 0.42, C.primary);
  slide.addText("▶", {
    x: MARGIN, y: 1.1, w: 0.42, h: 0.42,
    fontSize: 16, fontFace: C.fontBody,
    color: "FFFFFF", align: "center", valign: "middle", margin: 0,
  });
  slide.addText("点击播放音频", {
    x: MARGIN + 0.6, y: 1.1, w: 3, h: 0.42,
    fontSize: FZ.SMALL, fontFace: C.fontBody,
    color: C.textLight, valign: "middle", margin: 0,
  });

  // 音频文本
  if (audioText) {
    slide.addText(audioText, {
      x: MARGIN, y: 1.7, w: CONTENT_W, h: 0.7,
      fontSize: 13, fontFace: C.fontBody,
      color: C.text, valign: "top", margin: 0,
      lineSpacingMultiple: 1.3,
    });
  }
  if (subtitle) {
    slide.addText(subtitle, {
      x: MARGIN, y: 2.45, w: CONTENT_W, h: 0.3,
      fontSize: 12, fontFace: C.fontBody,
      color: C.textLight, italic: true, margin: 0,
    });
  }

  // 题目
  for (let i = 0; i < Math.min(questions.length, 3); i++) {
    const q = questions[i], y = 2.9 + i * 0.7;
    slide.addText(`Q${i + 1}. ${q.stem || ""}`, {
      x: MARGIN, y, w: CONTENT_W, h: 0.25,
      fontSize: 12, fontFace: C.fontBody,
      color: C.text, bold: true, margin: 0,
    });
    (q.options || []).slice(0, 4).forEach((opt, oi) => {
      const oy = y + 0.28 + oi * 0.18;
      const isCorrect = q.answer !== undefined && q.answer === oi;
      slide.addShape(pres.shapes.RECTANGLE, {
        x: MARGIN + 0.15, y: oy, w: CONTENT_W - 0.3, h: 0.16,
        fill: { color: isCorrect ? "C8E6C9" : (C.bg2 || "F5F5F5") },
        rectRadius: 0.04,
      });
      slide.addText(`${optLabels[oi]}. ${opt}`, {
        x: MARGIN + 0.3, y: oy, w: CONTENT_W - 0.55, h: 0.16,
        fontSize: FZ.SMALL, fontFace: C.fontBody,
        color: C.text, valign: "middle", margin: 0,
      });
    });
  }
  addPageNum(slide, 0, 1, C.textLight);
}

/** 口语跟读 — 话筒图标 + 居中大字文本 + 发音提示 */
function renderSpeaking(pres, slide, page, C) {
  addPageHeader(slide, pres, page.title || "口语跟读", C);
  const content = page.content || {};
  const text = getCF(content, "text", "");
  const translation = getCF(content, "translation", "");
  const tips = getCF(content, "tips", "");

  // 话筒图标
  addIconCircle(slide, pres, MARGIN, 1.1, 0.42, C.primary);
  slide.addText("🎤", {
    x: MARGIN, y: 1.1, w: 0.42, h: 0.42,
    fontSize: 16, align: "center", valign: "middle", margin: 0,
  });
  slide.addText("请跟读以下内容", {
    x: MARGIN + 0.6, y: 1.1, w: 3, h: 0.42,
    fontSize: FZ.SMALL, fontFace: C.fontBody,
    color: C.textLight, valign: "middle", margin: 0,
  });

  // 跟读文本（居中大字）
  if (text) {
    addCard(slide, pres, MARGIN, 1.65, CONTENT_W, 2.0, C.cardBg);
    slide.addText(text, {
      x: MARGIN + 0.3, y: 1.75, w: CONTENT_W - 0.6, h: 1.8,
      fontSize: 18, fontFace: C.fontBody,
      color: C.heading, align: "center",
      valign: "middle", margin: 0,
      lineSpacingMultiple: 1.5,
    });
  }

  if (translation) {
    slide.addText(translation, {
      x: MARGIN, y: 3.8, w: CONTENT_W, h: 0.35,
      fontSize: 13, fontFace: C.fontBody,
      color: C.textSec, align: "center", margin: 0,
    });
  }
  if (tips) {
    slide.addText(`发音提示: ${tips}`, {
      x: MARGIN, y: 4.2, w: CONTENT_W, h: 0.35,
      fontSize: FZ.SMALL, fontFace: C.fontBody,
      color: C.textLight, italic: true, margin: 0,
    });
  }
  addPageNum(slide, 0, 1, C.textLight);
}

// =============================== 渲染器注册表 ===============================

const RENDERERS = {
  title:          renderTitle,
  objective:      renderObjective,
  vocabulary:     renderVocabulary,
  dialogue:       renderDialogue,
  grammar:        renderGrammar,
  practice:       renderPractice,
  interactive:    renderInteractive,
  ai_interaction: renderAiInteraction,
  summary:        renderSummary,
  listening:      renderListening,
  speaking:       renderSpeaking,
};

// =============================== 主流程 ===============================

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error("用法: node export_pptx.js <pages_json_path> <theme_name> [title] [output_path]");
    console.error("  pages_json_path: JSON 文件路径，或 '-' 表示从 stdin 读取");
    process.exit(1);
  }

  const [pagesPath, themeName, title, outputPath] = args;

  // 1. 读取 pages_json
  let pagesRaw;
  if (pagesPath === "-") {
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    pagesRaw = Buffer.concat(chunks).toString("utf-8");
  } else {
    pagesRaw = fs.readFileSync(pagesPath, "utf-8");
  }
  let pages = JSON.parse(pagesRaw);
  if (!Array.isArray(pages)) {
    for (const k of ["pages", "slides", "data"]) {
      if (Array.isArray(pages[k])) { pages = pages[k]; break; }
    }
  }
  if (!Array.isArray(pages) || pages.length === 0) {
    console.error("错误: pages_json 应为非空数组");
    process.exit(1);
  }

  // 2. 获取主题色板
  const C = getTheme(themeName);
  const pptTitle = title || pages[0]?.title || "AI 备课课件";

  // 3. 创建演示文稿
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "E-Learning AI PPT";
  pres.title = pptTitle;

  // 4. 逐页渲染（传入总页数用于页码）
  const total = pages.length;
  for (let i = 0; i < total; i++) {
    const page = pages[i];
    const slideType = page.type || "practice";
    const renderer = RENDERERS[slideType];
    if (!renderer) {
      console.warn(`警告: 未知 slide_type "${slideType}"，使用 practice 渲染`);
    }
    const slide = pres.addSlide();
    try {
      (renderer || renderPractice)(pres, slide, page, C);
    } catch (err) {
      console.error(`渲染第 ${i + 1} 页失败 (type=${slideType}): ${err.message}`);
      slide.background = { color: "FFFFFF" };
      slide.addText(`第 ${i + 1} 页 - 渲染出错`, {
        x: 0, y: 0, w: SLIDE_W, h: SLIDE_H,
        fontSize: 24, align: "center", valign: "middle", color: "FF0000",
      });
    }
  }

  // 5. 输出文件
  const outPath = outputPath || path.join(
    process.cwd(), "uploads", "ppt_export",
    `ppt_export_${Date.now()}.pptx`
  );
  const dir = path.dirname(outPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  await pres.writeFile({ fileName: outPath });
  console.log(JSON.stringify({ success: true, path: outPath, slideCount: pages.length }));
}

main().catch(err => {
  console.error(JSON.stringify({ success: false, error: err.message }));
  process.exit(1);
});
