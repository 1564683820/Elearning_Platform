"""HTML 幻灯片渲染器：将 JSON 页面 + 主题 CSS 合并为自包含 HTML"""
"""支持题目交互、翻页动效、postMessage 双向通信"""

import json
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.ppt_theme_service import PPTThemeService

# Phase 3.5: 视觉风格桥接（延迟导入以避免循环依赖）
_VISUAL_STYLE_BRIDGE = None
def _get_style_bridge():
    global _VISUAL_STYLE_BRIDGE
    if _VISUAL_STYLE_BRIDGE is None:
        from app.ppt_generator.services.ppt_html_style_bridge import (
            generate_style_full_css, generate_style_css_variables,
        )
        _VISUAL_STYLE_BRIDGE = (generate_style_full_css, generate_style_css_variables)
    return _VISUAL_STYLE_BRIDGE


# ========== HTML 模板 ==========

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
/* ===== Reset & Base ===== */
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:100%; height:100%; overflow:hidden; background:#fff; }}
.ppt-presentation {{
  width:100%;
  height:100vh;
  display:flex;
  align-items:center;
  justify-content:center;
  position:relative;
  overflow:hidden;
  background:var(--slide-bg,#ffffff);
}}

.ppt-slide-container {{
  width:100%;
  height:100%;
  max-width:calc(100vh * 16 / 9);
  aspect-ratio:16/9;
  margin:auto;
  display:flex;
  flex-direction:column;
  overflow:hidden;
  position:relative;
}}

/* ===== Theme CSS (主题变量覆盖默认值) ===== */
/* ===== 默认CSS变量（确保未定义变量有合理回退值）===== */
:root {{
  --slide-subtitle-color: #546e7a;
  --slide-grade-color: #78909c;
  --slide-header-text: inherit;
  --slide-word-color: var(--slide-primary-dark);
  --slide-phonetic-color: #78909c;
  --slide-translation-color: #546e7a;
  --slide-example-color: #90a4ae;
  --slide-rule-color: #d84315;
  --slide-explain-color: #607d8b;
  --slide-speaker-a-color: #1565c0;
  --slide-speaker-b-color: #c62828;
  --slide-label-color: #37474f;
  --slide-hint-color: #607d8b;
  --slide-prompt-color: var(--slide-text);
  --slide-footer-text: #78909c;
  --slide-ai-question-bg: rgba(0,0,0,0.04);
  --slide-ai-question-text: var(--slide-text);
  --slide-title-color: var(--slide-primary-dark);
  /* ===== 第二阶段扩展：设计token体系 (80+变量) ===== */
  /* 边框与分隔 */
  --slide-border-style: solid;
  --slide-border-width: 1px;
  --slide-divider-style: solid;
  --slide-divider-color: var(--slide-border);
  --slide-divider-thickness: 1px;
  /* 卡片样式 */
  --slide-card-layout: block;
  --slide-card-shadow: 0 2px 12px rgba(0,0,0,0.06);
  --slide-card-padding: 1.0vw 1.3vw;
  --slide-card-border: 1px solid var(--slide-border);
  --slide-card-hover-transform: translateY(-2px);
  --slide-card-hover-shadow: 0 4px 16px rgba(0,0,0,0.12);
  /* 标题栏样式变体 */
  --slide-header-style: left-border;
  --slide-header-font-size: clamp(18px,1.8vw,32px);
  --slide-header-font-weight: 700;
  --slide-header-padding: clamp(8px,0.9vw,16px);
  --slide-header-margin: 0 0 clamp(8px,1.2vw,16px) 0;
  --slide-header-letter-spacing: 0;
  /* 排版 */
  --slide-corner-radius: 12px;
  --slide-font-title-weight: 800;
  --slide-font-title-letter-spacing: -0.02em;
  --slide-font-body-line-height: 1.7;
  --slide-paragraph-spacing: 0.6vw;
  --slide-text-margin-bottom: 0.4vw;
  /* 列表样式 */
  --slide-list-style-type: none;
  --slide-list-item-marker-color: var(--slide-primary);
  --slide-list-line-height: 2.0;
  --slide-list-item-spacing: 0.5vw 0;
  /* 动画token */
  --slide-anim-entrance: fadeInUp;
  --slide-anim-duration: 0.5s;
  --slide-anim-easing: cubic-bezier(0.4, 0, 0.2, 1);
  --slide-anim-exit: fadeOut;
  --slide-anim-stagger-delay: 0.05s;
  --slide-entrance-offset: 20px;
  /* 页面切换 */
  --slide-transition-type: slide;
  --slide-transition-duration: 400ms;
  --slide-transition-easing: cubic-bezier(0.4, 0, 0.2, 1);
  /* 滚动条 */
  --slide-scrollbar-width: 6px;
  --slide-scrollbar-color: var(--slide-border);
  --slide-scrollbar-bg: transparent;
  /* 选中文本 */
  --slide-selection-bg: var(--slide-primary-light);
  --slide-selection-text: var(--slide-text);
  /* 图标/装饰颜色 */
  --slide-icon-color: var(--slide-primary);
  /* 代码块 */
  --slide-code-font-family: 'Consolas','Monaco','Courier New',monospace;
  --slide-code-font-size: 1.2vw;
  --slide-code-padding: 0.8vw 1.2vw;
  /* 表格 */
  --slide-table-border-color: var(--slide-border);
  --slide-table-header-bg: var(--slide-primary-light);
  /* 页脚 */
  --slide-footer-bg: transparent;
  --slide-footer-padding: 0.5vw 0;
  --slide-footer-font-size: 1.0vw;
  /* 引用块 */
  --slide-blockquote-style: solid;
  --slide-blockquote-color: var(--slide-primary);
  --slide-blockquote-bg: var(--slide-primary-light);
  /* 响应式布局 */
  --slide-layout-direction: column;
  --slide-body-max-width: 100%;
  --slide-body-text-align: left;
  --slide-spacing-unit: 0.6vw;
  /* 渐变/纹理背景 */
  --slide-bg-overlay: none;
  --slide-bg-pattern: none;
  /* AI互动页 */
  --slide-ai-card-bg: var(--slide-ai-question-bg);
  --slide-ai-card-border: 1px solid var(--slide-border);
  --slide-ai-card-radius: var(--slide-radius);
}

/* 文字标签代替 emoji 图标 */
.icon-rule {
  display: inline-block;
  background: var(--slide-primary-light, #e3f2fd);
  color: var(--slide-primary, #1565c0);
  font-size: 0.8em;
  font-weight: 600;
  padding: 0.1em 0.5em;
  border-radius: 4px;
  margin-right: 0.4em;
}
.activity-icon-badge {
  display: inline-block;
  background: var(--slide-primary-light, #e3f2fd);
  color: var(--slide-primary, #1565c0);
  font-size: 1.4vw;
  font-weight: 700;
  padding: 0.3vw 1.2vw;
  border-radius: 20px;
  margin-bottom: 0.8vw;
}}
/* ===== 目录导航 ===== */
.catalog-block {{
  width:100%; max-width:90%; margin:0 auto;
}}
.catalog-list {{
  list-style:none; padding:0; margin:1vw 0 0;
  display:flex; flex-direction:column; gap:clamp(6px,0.6vw,12px);
}}
.catalog-list li {{
  display:flex; align-items:center; gap:clamp(6px,0.6vw,12px);
  padding:clamp(6px,0.5vw,10px) clamp(8px,0.8vw,16px);
  background:var(--slide-surface,rgba(0,0,0,0.02));
  border-radius:8px; transition:background 0.2s;
}}
.catalog-list li:hover {{
  background:var(--slide-primary-light,rgba(21,101,192,0.06));
}}
.catalog-num {{
  display:inline-flex; align-items:center; justify-content:center;
  width:clamp(20px,1.8vw,32px); height:clamp(20px,1.8vw,32px);
  border-radius:50%;
  background:var(--slide-accent,rgba(255,152,0,0.15));
  color:var(--slide-accent,#f57c00);
  font-size:clamp(10px,0.8vw,14px); font-weight:700;
  flex-shrink:0;
}}
.catalog-label {{
  font-size:clamp(13px,1.2vw,18px);
  color:var(--slide-text,#333);
  line-height:1.4;
}}
.catalog-list-full li {{
  padding:clamp(10px,0.8vw,16px) clamp(12px,1vw,20px);
}}
{theme_css}

/* ===== 幻灯片通用样式 ===== */
.ppt-slide {{
  position:absolute; top:0; left:0;
  width:100%; height:100%;
  display:none;
  flex-direction:column;
  opacity:0;
  padding:clamp(12px,2vw,40px);
  transition:opacity 0.35s ease, transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}}
.ppt-slide.active {{ display:flex; opacity:1; transform:translateX(0); }}
.ppt-slide .slide-body {{
  flex:1;
  overflow-y:auto;
  padding:clamp(8px,1vw,24px);
  font-size:clamp(14px,1.4vw,22px);
  line-height:1.7;
}}

/* ===== 逐元素入场动画 ===== */
@keyframes fadeInUp {{ from{{opacity:0;transform:translateY(20px)}} to{{opacity:1;transform:translateY(0)}} }}
.ppt-slide.active .slide-content > * {{
  animation:fadeInUp 0.5s ease forwards;
  opacity:0;
}}
.ppt-slide.active .slide-content > *:nth-child(1) {{ animation-delay:0.1s; }}
.ppt-slide.active .slide-content > *:nth-child(2) {{ animation-delay:0.2s; }}
.ppt-slide.active .slide-content > *:nth-child(3) {{ animation-delay:0.25s; }}
.ppt-slide.active .slide-content > *:nth-child(4) {{ animation-delay:0.3s; }}
.ppt-slide.active .slide-content > *:nth-child(5) {{ animation-delay:0.35s; }}
.ppt-slide.active .slide-content > *:nth-child(6) {{ animation-delay:0.4s; }}
.ppt-slide.active .slide-content > *:nth-child(7) {{ animation-delay:0.45s; }}
.ppt-slide.active .slide-content > *:nth-child(8) {{ animation-delay:0.5s; }}

/* ===== 题目交互 ===== */
@keyframes shake {{
  0%,100% {{ transform:translateX(0); }}
  25% {{ transform:translateX(-5px); }}
  75% {{ transform:translateX(5px); }}
}}
.option-item {{
  cursor:pointer;
  transition:all 0.2s ease;
  user-select:none;
}}
.option-item:hover {{
  transform:translateY(-1px);
  box-shadow:0 2px 8px rgba(0,0,0,0.08);
}}
.option-item.wrong {{
  background:#ffebee !important;
  border-color:#e53935 !important;
  color:#c62828 !important;
  animation:shake 0.3s ease;
}}
.option-item.correct {{
  background:#c8e6c9 !important;
  border-color:#43a047 !important;
  animation:shake 0.3s ease;
}}
.question-card.answered .option-item {{
  pointer-events:none;
}}
.explanation {{ transition:opacity 0.3s ease; display:none; margin-top:0.5vw; font-size:1.2vw; color:var(--slide-hint-color,#607d8b); }}

/* ===== 对话气泡说话人颜色 ===== */
.dialogue-bubble .speaker {{ color:var(--slide-speaker-color, inherit); }}
.dialogue-bubble.a .speaker {{ color:var(--slide-speaker-a-color,#1565c0); }}
.dialogue-bubble.b .speaker {{ color:var(--slide-speaker-b-color,#c62828); }}

/* ===== AI 互动页样式 ===== */
.ai-interaction-body {{ text-align:center; }}

/* ===== 音频播放器 ===== */
.audio-player-bar {{
  display:flex; align-items:center; gap:clamp(8px,0.8vw,16px);
  padding:clamp(8px,0.8vw,16px); margin-bottom:clamp(8px,0.8vw,16px);
  background:var(--slide-card-bg,#f0faf3); border-radius:var(--slide-corner-radius,12px);
  border:1px solid var(--slide-border,#c8e6c9);
}}
.audio-expand-btn {{
  display:inline-flex; align-items:center; gap:4px;
  padding:clamp(4px,0.3vw,8px) clamp(10px,0.8vw,16px);
  border-radius:9999px; border:1px solid var(--slide-border,#c8e6c9);
  cursor:pointer; font-size:clamp(11px,0.9vw,14px); font-weight:400;
  background:var(--slide-card-bg,#f0faf3); color:var(--slide-hint-color,#607d8b);
  transition:all 0.15s; white-space:nowrap;
}}
.audio-expand-btn:hover {{
  background:var(--slide-border,#c8e6c9); color:var(--slide-text,#333);
}}
.audio-expand-btn.expanded {{
  background:var(--slide-primary,#2d7d46); color:#fff; border-color:var(--slide-primary,#2d7d46);
}}
.speaking-text-wrap {{
  margin-top:clamp(8px,0.8vw,16px);
  padding:clamp(8px,0.8vw,16px);
  background:var(--slide-card-bg,#fff);
  border:1px solid var(--slide-border,#e0e0e0);
  border-radius:var(--slide-corner-radius,12px);
}}
.speaking-text-wrap.expanded {{
  display:block !important;
}}
.audio-play-btn {{
  display:inline-flex; align-items:center; gap:6px;
  padding:clamp(6px,0.5vw,12px) clamp(14px,1.2vw,24px);
  border-radius:9999px; border:none; cursor:pointer;
  font-size:clamp(13px,1.1vw,16px); font-weight:500;
  background:var(--slide-primary,#2d7d46); color:#fff;
  transition:opacity 0.15s; white-space:nowrap;
}}
.audio-play-btn:disabled {{ opacity:0.5; cursor:not-allowed; }}
.audio-status {{ font-size:clamp(12px,1.0vw,14px); color:var(--slide-hint-color,#607d8b); }}
.listening-subtitle {{ font-size:clamp(13px,1.1vw,18px); color:var(--slide-subtitle-color,#546e7a); margin-bottom:clamp(8px,0.8vw,16px); font-style:italic; }}
.speaking-text {{ font-size:clamp(16px,1.6vw,28px); line-height:1.8; color:var(--slide-text,#333); margin-bottom:clamp(8px,0.8vw,16px); }}
.speaking-translation {{ font-size:clamp(13px,1.1vw,18px); color:var(--slide-subtitle-color,#546e7a); margin-bottom:clamp(8px,0.8vw,16px); }}
.speaking-tips {{ font-size:clamp(12px,1.0vw,16px); color:var(--slide-hint-color,#607d8b); margin-top:clamp(8px,0.8vw,16px); padding:clamp(8px,0.8vw,16px); background:var(--slide-card-bg,#fff8e1); border-radius:var(--slide-corner-radius,8px); }}
.ai-prompt {{ font-size:1.7vw; font-weight:500; color:var(--slide-prompt-color,var(--slide-text)); margin-bottom:1.5vw; line-height:1.6; max-width:85%; margin-left:auto; margin-right:auto; }}
.ai-questions-wrap {{ text-align:left; max-width:80%; margin:0 auto; }}
.ai-question-item {{ background:var(--slide-ai-question-bg,rgba(0,0,0,0.04)); border-radius:10px; padding:0.8vw 1.2vw; margin-bottom:0.6vw; border-left:3px solid var(--slide-primary,#2d7d46); }}
.ai-question-row {{ display:flex; align-items:flex-start; gap:0.6vw; }}
.ai-icon {{ font-size:1.4vw; flex-shrink:0; }}
.ai-question-title {{ font-size:1.3vw; font-weight:500; color:var(--slide-ai-question-text,var(--slide-text)); }}
.ai-ask-icon {{ font-size:0.9vw; color:var(--slide-primary,#2d7d46); flex-shrink:0; margin-left:0.6vw; opacity:0; transition:opacity 0.2s; }}
.ai-question-item:hover .ai-ask-icon {{ opacity:1; }}
.ai-hint {{ font-size:1.1vw; color:var(--slide-hint-color,#607d8b); margin-top:0.3vw; }}
.ai-footer {{ margin-top:1.2vw; font-size:1.1vw; color:var(--slide-footer-text,var(--slide-hint-color,#78909c)); border-top:1px solid var(--slide-border,#e0e0e0); padding-top:0.8vw; }}

/* ===== 布局变体：Grid 网格布局 ===== */
.vocab-grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(14vw, 1fr)); gap:0.8vw; }}
.word-card-grid {{ text-align:center; padding:1.2vw 1vw; }}
.word-card-grid .word {{ display:block; font-size:2.0vw; margin-bottom:0.3vw; }}
.word-card-large {{ padding:1.2vw 1.5vw; }}
.word-card-large .word-card-front {{ display:flex; align-items:baseline; gap:0.5vw; margin-bottom:0.3vw; }}
.objective-grid {{ display:grid; grid-template-columns:repeat(2, 1fr); gap:0.8vw; list-style:none; padding:0; }}
.objective-grid-item {{ display:flex; align-items:flex-start; gap:0.6vw; padding:0.8vw 1.0vw; background:var(--slide-card-bg); border-radius:var(--slide-radius); border:1px solid var(--slide-border); font-size:1.4vw; line-height:1.6; }}
.objective-marker {{ display:inline-flex; width:2.0vw; height:2.0vw; border-radius:50%; background:var(--slide-primary); color:#fff; font-size:1.1vw; font-weight:700; align-items:center; justify-content:center; flex-shrink:0; }}

/* ===== 布局变体：Cards 卡片布局 ===== */
.vocab-cards {{ display:flex; flex-direction:column; gap:0.8vw; }}
.dialogue-cards {{ display:flex; flex-direction:column; gap:0.8vw; }}
.dialogue-card {{ border-radius:var(--slide-corner-radius,12px); box-shadow:var(--slide-card-shadow); border:var(--slide-card-border); padding:1.0vw 1.5vw; }}
.dialogue-card-header {{ margin-bottom:0.4vw; padding-bottom:0.3vw; border-bottom:2px solid var(--slide-border); }}
.grammar-card-boxed {{ border:2px solid var(--slide-primary); border-radius:var(--slide-corner-radius,8px); box-shadow:var(--slide-card-shadow); }}
.grammar-card-boxed .grammar-card-header {{ font-size:1.4vw; font-weight:700; color:var(--slide-primary-dark); margin-bottom:0.5vw; }}
.practice-list .options-wrap {{ display:flex; flex-direction:column; gap:0.3vw; }}
.ai-questions-grid {{ display:grid; grid-template-columns:repeat(2, 1fr); gap:0.6vw; }}

/* ===== 增强的卡片悬停效果 ===== */
.word-card:hover, .grammar-card:hover, .question-card:hover {{
  transform: var(--slide-card-hover-transform, translateY(-2px));
  box-shadow: var(--slide-card-hover-shadow, 0 4px 16px rgba(0,0,0,0.12));
  transition: all 0.25s ease;
}}

/* ===== 滚动条美化 ===== */
.slide-body::-webkit-scrollbar {{ width:var(--slide-scrollbar-width, 6px); }}
.slide-body::-webkit-scrollbar-thumb {{ background:var(--slide-scrollbar-color, #c0c0c0); border-radius:3px; }}
.slide-body::-webkit-scrollbar-track {{ background:var(--slide-scrollbar-bg, transparent); }}

/* ===== 文本选中颜色 ===== */
::selection {{ background:var(--slide-selection-bg, rgba(45,125,70,0.15)); color:var(--slide-selection-text, inherit); }}

/* ===== 响应式断点 ===== */
@media (max-width: 768px) {
  .ppt-presentation {{ height:auto; min-height:100vh; }}
  .ppt-slide-container {{ max-width:100%; aspect-ratio:auto; }}
  .ppt-slide {{ padding:12px; }}
  .vocab-grid {{ grid-template-columns:repeat(2,1fr); }}
  .objective-grid {{ grid-template-columns:1fr; }}
  .slide-body {{ font-size:clamp(14px,2.2vw,18px) !important; }}
  .ai-questions-grid {{ grid-template-columns:1fr; }}
  .ai-questions-wrap {{ max-width:100%; }}
}

@media (max-width: 480px) {
  .vocab-grid {{ grid-template-columns:1fr; }}
  .slide-title h1 {{ font-size:clamp(18px,5vw,24px) !important; }}
}

/* ===== 减少动画 ===== */
@media (prefers-reduced-motion) {
  .ppt-slide {{ transition:none !important; }}
  .ppt-slide.active .slide-content > * {{ animation:none !important; opacity:1 !important; }}
}
</style>
</head>
<body>
<div class="ppt-presentation" data-theme="{theme}" data-total="{total}" data-transition="{transition_type}" data-transition-duration="{transition_duration}">
  {slides_html}
</div>
<script>
{backend_base_script}
(function() {{
  // ===== Viewport 自适应 =====
  function recalcViewport() {{
    var root = document.documentElement;
    var w = window.innerWidth;
    var h = window.innerHeight;
    var baseSize = Math.max(14, Math.min(w * 0.018, 32));
    root.style.setProperty('--slide-font-base', baseSize + 'px');
  }}
  window.addEventListener('resize', recalcViewport);
  window.addEventListener('fullscreenchange', recalcViewport);
  recalcViewport();

  // ===== 幻灯片切换动画引擎 =====
  var slides = document.querySelectorAll('.ppt-slide');
  var current = 0;
  var isTransitioning = false;
  var presDiv = document.querySelector('.ppt-presentation');
  var transitionType = presDiv.getAttribute('data-transition') || 'slide';
  var transitionDuration = parseInt(presDiv.getAttribute('data-transition-duration')) || 400;
  var tEasing = 'cubic-bezier(0.4, 0, 0.2, 1)';

  function goToPage(idx, direction) {{
    if (isTransitioning || idx < 0 || idx >= slides.length || idx === current) return;
    isTransitioning = true;
    direction = direction || (idx > current ? 'left' : 'right');

    var currentEl = slides[current];
    var nextEl = slides[idx];

    // 清除上一次动画标记
    nextEl.style.transition = 'none';
    nextEl.style.display = 'none';

    // 强制 reflow
    void nextEl.offsetHeight;

    var dur = transitionDuration + 'ms';
    nextEl.style.transition = 'transform ' + dur + ' ' + tEasing + ', opacity ' + dur + ' ' + tEasing;

    if (transitionType === 'fade') {{
      // 纯淡入淡出
      nextEl.style.display = 'flex';
      nextEl.style.opacity = '0';
      nextEl.style.transform = 'none';
      currentEl.style.transition = 'opacity ' + dur + ' ' + tEasing;
      currentEl.style.opacity = '0';

      requestAnimationFrame(function() {{
        requestAnimationFrame(function() {{
          currentEl.style.display = 'none';
          nextEl.style.opacity = '1';
          slides.forEach(function(s, i) {{ s.classList.toggle('active', i === idx); }});
          current = idx;
          isTransitioning = false;
          notifyParent(idx);
        }});
      }});
    }} else if (transitionType === 'push') {{
      // 推入推出：旧页被推出，新页推入
      var slideOut = direction === 'left' ? 'translateX(-100%)' : 'translateX(100%)';
      var slideInStart = direction === 'left' ? 'translateX(100%)' : 'translateX(-100%)';
      nextEl.style.display = 'flex';
      nextEl.style.opacity = '1';
      nextEl.style.transform = slideInStart;
      currentEl.style.transition = 'transform ' + dur + ' ' + tEasing;

      requestAnimationFrame(function() {{
        requestAnimationFrame(function() {{
          currentEl.style.transform = slideOut;
          nextEl.style.transform = 'translateX(0)';
          setTimeout(function() {{
            currentEl.style.display = 'none';
            currentEl.style.transform = '';
            slides.forEach(function(s, i) {{ s.classList.toggle('active', i === idx); }});
            current = idx;
            isTransitioning = false;
            notifyParent(idx);
          }}, transitionDuration);
        }});
      }});
    }} else {{
      // 默认 slide：滑动+淡入淡出
      nextEl.style.display = 'flex';
      nextEl.style.opacity = '0';
      nextEl.style.transform = direction === 'left' ? 'translateX(80px)' : 'translateX(-80px)';
      currentEl.style.transition = 'transform ' + dur + ' ' + tEasing + ', opacity ' + dur + ' ' + tEasing;
      currentEl.style.opacity = '0';
      currentEl.style.transform = direction === 'left' ? 'translateX(-40px)' : 'translateX(40px)';

      requestAnimationFrame(function() {{
        requestAnimationFrame(function() {{
          currentEl.style.display = 'none';
          nextEl.style.transform = 'translateX(0)';
          nextEl.style.opacity = '1';
          slides.forEach(function(s, i) {{ s.classList.toggle('active', i === idx); }});
          current = idx;
          isTransitioning = false;
          notifyParent(idx);
        }});
      }});
    }}
  }}

  function notifyParent(idx) {{
    try {{
      window.parent.postMessage({{ type: 'slide-change', index: idx, total: slides.length }}, '*');
    }} catch(e) {{}}
  }}

  // ===== 题目选项交互 =====
  window.selectOption = function(el) {
    var qCard = el.closest('.question-card');
    if (!qCard || qCard.classList.contains('answered')) return;
    qCard.classList.add('answered');

    var options = qCard.querySelectorAll('.option-item');
    var selectedIdx = Array.prototype.indexOf.call(options, el);
    var correctIdx = parseInt(qCard.getAttribute('data-correct') || '-1');

    options.forEach(function(o) { o.style.pointerEvents = 'none'; });

    if (selectedIdx === correctIdx) {
      el.classList.add('correct');
    } else {
      el.classList.add('wrong');
      if (correctIdx >= 0 && options[correctIdx]) {
        options[correctIdx].classList.add('correct');
      }
    }

    var explanation = qCard.querySelector('.explanation');
    if (explanation) explanation.style.display = 'block';

    try {
      window.parent.postMessage({
        type: 'answer',
        qIndex: parseInt(qCard.getAttribute('data-q') || '0'),
        selected: selectedIdx,
        correct: selectedIdx === correctIdx
      }, '*');
    } catch(e) {}
  };

  // ===== 音频播放按钮（支持预生成 URL 和懒加载回退）=====
  window.toggleAudio = function(btn) {
    if (btn.dataset.playing === 'true') {
      // Pause
      var aud = document.getElementById('slide-audio');
      if (aud) { aud.pause(); aud.currentTime = 0; }
      btn.innerHTML = '\u25b6 \u64ad\u653e\u97f3\u9891';
      btn.dataset.playing = 'false';
      var st = document.querySelector('.audio-status');
      if (st) st.textContent = '';
      return;
    }
    if (btn.dataset.playing === 'loading') {
      // Stop loading
      var aud = document.getElementById('slide-audio');
      if (aud) { aud.pause(); aud.currentTime = 0; aud.src = ''; }
      btn.innerHTML = '\u25b6 \u64ad\u653e\u97f3\u9891';
      btn.dataset.playing = 'false';
      var st = document.querySelector('.audio-status');
      if (st) st.textContent = '';
      return;
    }
    var bar = btn.closest('.audio-player-bar');
    if (!bar) return;

    // Reuse a single audio element across slides
    var aud = document.getElementById('slide-audio');
    if (!aud) {
      aud = document.createElement('audio');
      aud.id = 'slide-audio';
      document.body.appendChild(aud);
    }

    var cachedUrl = bar.getAttribute('data-audio-url');
    var st = document.querySelector('.audio-status');

    if (cachedUrl) {
      btn.innerHTML = '\u23f8 \u52a0\u8f7d\u4e2d...';
      btn.dataset.playing = 'loading';
      if (st) st.textContent = '\u52a0\u8f7d\u4e2d...';

      // Fetch audio via fetch() to get blob, bypass srcdoc iframe CORS issues
      var base = (window.BACKEND_BASE || '');
      fetch(base + cachedUrl).then(function(resp) {
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        return resp.blob();
      }).then(function(blob) {
        // Ensure correct MIME type for MP3
        var fixedBlob = new Blob([blob], { type: 'audio/mpeg' });
        var url = URL.createObjectURL(fixedBlob);
        aud.src = url;
        aud.load();
        aud.addEventListener('canplay', function() {
          btn.innerHTML = '\u23f8 \u64ad\u653e\u4e2d...';
          btn.dataset.playing = 'true';
          if (st) st.textContent = '\u64ad\u653e\u4e2d...';
          aud.play().catch(function() {});
        }, { once: true });
        aud.addEventListener('error', function() {
          btn.innerHTML = '\u25b6 \u64ad\u653e\u97f3\u9891';
          btn.dataset.playing = 'false';
          if (st) st.textContent = '\u97f3\u9891\u89e3\u7801\u5931\u8d25';
        }, { once: true });
        aud.onended = function() {
          btn.innerHTML = '\u25b6 \u64ad\u653e\u97f3\u9891';
          btn.dataset.playing = 'false';
          if (st) st.textContent = '';
          URL.revokeObjectURL(url);
        };
      }).catch(function(err) {
        btn.innerHTML = '\u25b6 \u64ad\u653e\u97f3\u9891';
        btn.dataset.playing = 'false';
        if (st) st.textContent = '\u52a0\u8f7d\u5931\u8d25: ' + err.message;
      });
      return;
    }

    // Fallback: request TTS via postMessage (lazy)
    var text = bar.getAttribute('data-text');
    if (!text) return;
    btn.innerHTML = '\u23f3 \u6b63\u5728\u5408\u6210\u8bed\u97f3...';
    btn.disabled = true;
    if (st) st.textContent = '\u6b63\u5728\u751f\u6210\u97f3\u9891...';
    try {
      window.parent.postMessage({ type: 'request-tts', text: text }, '*');
    } catch(e) {}
  };

  // ===== 展开/收起口语原文（speaking 类型）=====
  window.toggleTextExpand = function(btn) {
    var wrap = btn.closest('.slide-body').querySelector('.speaking-text-wrap');
    if (!wrap) return;
    var isExpanded = wrap.classList.toggle('expanded');
    btn.classList.toggle('expanded', isExpanded);
    btn.innerHTML = isExpanded ? '\u25b2 \u6536\u8d77\u539f\u6587' : '\u25bc \u67e5\u770b\u539f\u6587';
  };

  window.playAudio = function(btn, url) {
     // Legacy fallback — for postMessage lazy-loaded audio
     var aud = document.getElementById('slide-audio');
     if (!aud) {
       aud = document.createElement('audio');
       aud.id = 'slide-audio';
       document.body.appendChild(aud);
     }
    btn.innerHTML = '\u23f8 \u52a0\u8f7d\u4e2d...';
    btn.dataset.playing = 'loading';
    var st = document.querySelector('.audio-status');
    if (st) st.textContent = '\u52a0\u8f7d\u4e2d...';
    var base = (window.BACKEND_BASE || '');
    // URL 已是绝对路径时不重复拼接 base（用于 postMessage 懒加载场景）
    var fullUrl = (url.indexOf('http://') === 0 || url.indexOf('https://') === 0) ? url : base + url;
    fetch(fullUrl).then(function(r) { return r.blob(); }).then(function(blob) {
       var fixedBlob = new Blob([blob], { type: 'audio/mpeg' });
       var u = URL.createObjectURL(fixedBlob);
      aud.src = u;
      aud.load();
      aud.addEventListener('canplay', function() {
        btn.innerHTML = '\u23f8 \u64ad\u653e\u4e2d...';
        btn.dataset.playing = 'true';
        if (st) st.textContent = '\u64ad\u653e\u4e2d...';
        aud.play().catch(function() {});
      }, { once: true });
      aud.onended = function() {
        btn.innerHTML = '\u25b6 \u64ad\u653e\u97f3\u9891';
        btn.dataset.playing = 'false';
        if (st) st.textContent = '';
        URL.revokeObjectURL(u);
      };
    }).catch(function(err) {
      btn.innerHTML = '\u25b6 \u64ad\u653e\u97f3\u9891';
      btn.dataset.playing = 'false';
      if (st) st.textContent = '\u52a0\u8f7d\u5931\u8d25: ' + err.message;
    });
  };

  // ===== AI 提问：发送 postMessage 到父窗口 =====
  window.askAIQuestion = function(question) {
    try {
      window.parent.postMessage({ type: 'request-ai-chat', question: question }, '*');
    } catch(e) {}
  };

  // ===== 接收 TTS 回复 =====
   window.addEventListener('message', function(e) {
     var data = e.data || {};
     if (data.type === 'tts-audio' && data.url) {
       var btn = document.querySelector('.audio-play-btn');
       if (btn) {
         btn.dataset.audioUrl = data.url;
         btn.disabled = false;
         btn.innerHTML = '\u25b6 \u64ad\u653e\u97f3\u9891';
         document.querySelector('.audio-status').textContent = '\u97f3\u9891\u5df2\u751f\u6210';
         window.playAudio(btn, data.url);
       }
     }
   });

  // ===== 初始化：显示第 0 页 =====
  slides.forEach(function(s, i) {
    if (i === 0) {
      s.style.display = 'flex';
      s.style.opacity = '1';
      s.classList.add('active');
    }
  });

  // ===== 键盘导航 =====
  document.addEventListener('keydown', function(e) {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ') {
      e.preventDefault();
      if (current < slides.length - 1) goToPage(current + 1, 'left');
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (current > 0) goToPage(current - 1, 'right');
    }
  });

  // ===== 点击翻页（跳过题目选项区 + 音频按钮）=====
   document.addEventListener('click', function(e) {
     if (e.target.closest('.ai-question-item')) return;
     if (e.target.closest('.option-item')) return;
     if (e.target.closest('.question-card')) return;
     if (e.target.closest('.audio-play-btn')) return;
    if (e.target.closest('.audio-expand-btn')) return;
     if (current < slides.length - 1) goToPage(current + 1, 'left');
   });

  // ===== 双击全屏 =====
  document.addEventListener('dblclick', function() {{
    if (document.fullscreenElement) {{
      document.exitFullscreen();
    }} else {{
      document.body.requestFullscreen();
    }}
  }});

  // ===== 接收父窗口指令（iframe 内嵌模式）=====
  window.addEventListener('message', function(e) {{
    var data = e.data || {{}};
    if (data.type === 'go-to-page') {{
      goToPage(data.index, data.index > current ? 'left' : 'right');
    }}
    if (data.type === 'next-slide') {{
      if (current < slides.length - 1) goToPage(current + 1, 'left');
    }}
    if (data.type === 'prev-slide') {{
      if (current > 0) goToPage(current - 1, 'right');
    }}
    if (data.type === 'toggle-fullscreen') {{
      if (document.fullscreenElement) {{
        document.exitFullscreen();
      }} else {{
        document.body.requestFullscreen();
      }}
    }}
  }});

  // ===== 通知父窗口已就绪 =====
  try {{
    window.parent.postMessage({{ type: 'slide-ready', total: slides.length }}, '*');
  }} catch(e) {{}}
}})();
</script>
</body>
</html>"""


# ========== 幻灯片 HTML 生成器 ==========

def _render_catalog_slide(page: dict, layout: str = None) -> str:
    """渲染目录导航页 — 带编号的章节列表"""
    c = page.get("content", {})
    sections = c.get("sections", [])
    items_html = "".join(
        f'<li><span class="catalog-num">{i+1}</span><span class="catalog-label">{_e(sec)}</span></li>'
        for i, sec in enumerate(sections)
    )
    list_class = "catalog-list"
    if layout == "full":
        list_class = "catalog-list catalog-list-full"
    return f"""<section class="ppt-slide" data-index="{page.get('_index', 0)}" data-type="catalog" data-layout="{layout or 'list'}">
<div class="slide-header"><h2>{_e(page.get('title', '课程内容'))}</h2></div>
<div class="slide-body slide-content">
<div class="catalog-block">
<div class="label">目录导航</div>
<ul class="{list_class}">{items_html}</ul>
</div>
</div>
</section>"""


def _render_title_slide(page: dict, layout: str = None) -> str:
    c = page.get("content", {})
    main_title = c.get("main_title", page.get("title", "PPT"))
    subtitle = c.get("subtitle", "")
    grade = c.get("grade", "")
    # 支持 cover（左对齐大标题）和 center（居中）两种标题布局
    is_cover = layout == "cover"
    align = "flex-start" if is_cover else "center"
    text_align = "left" if is_cover else "center"
    padding = "4vw 5vw" if is_cover else "0"
    return f"""<section class="ppt-slide" data-index="{page.get('_index', 0)}" data-type="title" data-layout="{layout or 'center'}">
<div class="slide-content" style="display:flex;flex-direction:column;justify-content:center;align-items:{align};height:100%;text-align:{text_align};padding:{padding};">
<h1 class="main-title">{_e(main_title)}</h1>
{subtitle and f'<p class="subtitle">{_e(subtitle)}</p>' or ''}
{grade and f'<p class="grade">{_e(grade)}</p>' or ''}
</div>
</section>"""


def _render_objective_slide(page: dict, layout: str = None) -> str:
    c = page.get("content", {})
    items = c.get("items", [])
    # list 布局：纵向列表，grid 布局：网格排列
    if layout == "grid":
        items_html = "".join(
            f'<div class="objective-grid-item"><span class="objective-marker">{i+1}</span><span>{_e(item)}</span></div>'
            for i, item in enumerate(items)
        )
        list_class = "objective-grid"
    else:
        items_html = "".join(f"<li>{_e(item)}</li>" for item in items)
        list_class = "objective-list"
    return f"""<section class="ppt-slide" data-index="{page.get('_index', 0)}" data-type="objective" data-layout="{layout or 'list'}">
<div class="slide-header"><h2>{_e(page.get('title', '学习目标'))}</h2></div>
<div class="slide-body slide-content">
<ul class="{list_class}">{items_html}</ul>
</div>
</section>"""


def _render_vocabulary_slide(page: dict, layout: str = None) -> str:
    c = page.get("content", {})
    words = c.get("words", [])
    cards = ""
    wrapper_class = "vocab-list"
    if layout == "grid":
        wrapper_class = "vocab-grid"
        for w in words:
            cards += f"""<div class="word-card word-card-grid" data-editable="true">
<div class="word">{_e(w.get('word',''))}</div>
<span class="phonetic">{_e(w.get('phonetic',''))}</span>
<div class="translation">{_e(w.get('translation',''))}</div>
{w.get('example') and f'<div class="example">{_e(w["example"])}</div>' or ''}
</div>"""
    elif layout == "cards":
        wrapper_class = "vocab-cards"
        for w in words:
            cards += f"""<div class="word-card word-card-large" data-editable="true">
<div class="word-card-front">
<span class="word">{_e(w.get('word',''))}</span>
<span class="phonetic">{_e(w.get('phonetic',''))}</span>
</div>
<div class="translation">{_e(w.get('translation',''))}</div>
{w.get('example') and f'<div class="example">{_e(w["example"])}</div>' or ''}
</div>"""
    else:
        for w in words:
            cards += f"""<div class="word-card" data-editable="true">
<span class="word">{_e(w.get('word',''))}</span>
<span class="phonetic">{_e(w.get('phonetic',''))}</span>
<div class="translation">{_e(w.get('translation',''))}</div>
{w.get('example') and f'<div class="example">{_e(w["example"])}</div>' or ''}
</div>"""
    return f"""<section class="ppt-slide" data-index="{page.get('_index', 0)}" data-type="vocabulary" data-layout="{layout or 'list'}">
<div class="slide-header"><h2>{_e(page.get('title', '新词汇'))}</h2></div>
<div class="slide-body slide-content {wrapper_class}">{cards}</div>
</section>"""


def _render_dialogue_slide(page: dict, layout: str = None) -> str:
    c = page.get("content", {})
    dialogues = c.get("dialogues", [])
    bubbles = ""
    wrapper_class = "dialogue-list"
    if layout == "cards":
        wrapper_class = "dialogue-cards"
        for i, d in enumerate(dialogues):
            speaker = d.get("speaker", "A")
            cls = "a" if speaker.upper() in ("A", "T", "TEACHER") else "b"
            bubbles += f"""<div class="dialogue-bubble dialogue-card {cls}">
<div class="dialogue-card-header"><span class="speaker">{_e(speaker)}</span></div>
<div class="text">{_e(d.get('text',''))}</div>
{d.get('translation') and f'<div class="translation">{_e(d["translation"])}</div>' or ''}
</div>"""
    else:
        for d in dialogues:
            speaker = d.get("speaker", "A")
            cls = "a" if speaker.upper() in ("A", "T", "TEACHER") else "b"
            bubbles += f"""<div class="dialogue-bubble {cls}">
<div class="speaker">{_e(speaker)}</div>
<div class="text">{_e(d.get('text',''))}</div>
{d.get('translation') and f'<div class="translation">{_e(d["translation"])}</div>' or ''}
</div>"""
    return f"""<section class="ppt-slide" data-index="{page.get('_index', 0)}" data-type="dialogue" data-layout="{layout or 'list'}">
<div class="slide-header"><h2>{_e(page.get('title', '对话练习'))}</h2></div>
<div class="slide-body slide-content {wrapper_class}" style="display:flex;flex-direction:column;gap:6px;">{bubbles}</div>
</section>"""


def _render_grammar_slide(page: dict, layout: str = None) -> str:
    c = page.get("content", {})
    points = c.get("points", [])
    cards = ""
    wrapper_class = "grammar-list"
    for p in points:
        if layout == "cards":
            cards += f"""<div class="grammar-card grammar-card-boxed">
<div class="grammar-card-header"><span class="icon-rule">[语法]</span> {_e(p.get('rule',''))}</div>
<div class="example">例句：<em>{_e(p.get('example',''))}</em></div>
{p.get('explanation') and f'<div class="explanation">{_e(p["explanation"])}</div>' or ''}
</div>"""
        else:
            cards += f"""<div class="grammar-card">
<div class="rule"><span class="icon-rule">[语法]</span> {_e(p.get('rule',''))}</div>
<div class="example">例句：<em>{_e(p.get('example',''))}</em></div>
{p.get('explanation') and f'<div class="explanation">{_e(p["explanation"])}</div>' or ''}
</div>"""
    return f"""<section class="ppt-slide" data-index="{page.get('_index', 0)}" data-type="grammar" data-layout="{layout or 'list'}">
<div class="slide-header"><h2>{_e(page.get('title', '语法要点'))}</h2></div>
<div class="slide-body slide-content {wrapper_class}">{cards}</div>
</section>"""


def _render_practice_slide(page: dict, layout: str = None) -> str:
    c = page.get("content", {})
    questions = c.get("questions", [])
    cards = ""
    wrapper_class = "practice-list"
    for i, q in enumerate(questions):
        correct_idx = q.get("answer", -1)
        opts = "".join(
            f'<div class="option-item" onclick="selectOption(this)" data-opt="{j}">{chr(65+j)}. {_e(o)}</div>'
            for j, o in enumerate(q.get("options", []))
        )
        explanation = q.get("explanation", "")
        expl_html = f'<div class="explanation" style="display:none;">[解析] {_e(explanation)}</div>' if explanation else ""
        cards += f"""<div class="question-card" data-q="{i}" data-correct="{correct_idx}">
<div class="stem">{i+1}. {_e(q.get('stem',''))}</div>
<div class="options-wrap">{opts}</div>
{expl_html}
</div>"""
    return f"""<section class="ppt-slide" data-index="{page.get('_index', 0)}" data-type="practice" data-layout="{layout or 'list'}">
<div class="slide-header"><h2>{_e(page.get('title', '课堂练习'))}</h2></div>
<div class="slide-body slide-content {wrapper_class}">{cards}</div>
</section>"""


def _render_interactive_slide(page: dict, layout: str = None) -> str:
    c = page.get("content", {})
    activity_type = c.get("activity_type", "game")
    icon_label = {"game": "游戏", "vote": "投票", "roleplay": "角色扮演", "discussion": "讨论"}.get(activity_type, "互动")
    steps = "".join(f"<li>{_e(s)}</li>" for s in c.get("steps", []))
    return f"""<section class="ppt-slide" data-index="{page.get('_index', 0)}" data-type="interactive" data-layout="{layout or 'center'}">
<div class="slide-header"><h2>{_e(page.get('title', '互动活动'))}</h2></div>
<div class="slide-body slide-content" style="text-align:center;">
<div class="activity-icon-badge">{icon_label}</div>
<h3 style="margin:0 0 0.9vw;font-size:1.9vw;">{_e(c.get('description',''))}</h3>
<ol style="text-align:left;line-height:2;font-size:1.4vw;">{steps}</ol>
</div>
</section>"""


def _render_summary_slide(page: dict, layout: str = None) -> str:
    c = page.get("content", {})
    key_points = c.get("key_points", [])
    kp_html = "".join(f"<li>{_e(kp)}</li>" for kp in key_points)
    homework = c.get("homework", "")
    hw_html = f'<div class="homework-box"><span style="font-weight:600;">课后作业：</span>{_e(homework)}</div>' if homework else ""
    return f"""<section class="ppt-slide" data-index="{page.get('_index', 0)}" data-type="summary" data-layout="{layout or 'list'}">
<div class="slide-header"><h2>{_e(page.get('title', '课堂总结'))}</h2></div>
<div class="slide-body slide-content">
<div class="summary-block">
<div class="label">本课重点</div>
<ul style="line-height:2;font-size:1.4vw;">{kp_html}</ul>
</div>
{hw_html}
</div>
</section>"""


def _render_ai_interaction_slide(page: dict, layout: str = None) -> str:
    """渲染人机互动页面 - 引导学生向 AI 提问"""
    c = page.get("content", {})
    prompt_text = c.get("prompt", "你对今天学的内容有什么疑问吗？试试向我提问吧！")
    questions = c.get("questions", [])
    q_html = ""
    wrapper_class = "ai-questions-wrap"
    if layout == "grid":
        wrapper_class = "ai-questions-wrap ai-questions-grid"
    for i, q in enumerate(questions):
        question = q.get("question", "")
        hint = q.get("hint", "")
        hint_html = f'<div class="ai-hint">{_e(hint)}</div>' if hint else ""
        q_html += f"""<div class="ai-question-item" onclick="askAIQuestion(\'{_e(question)}\')" style="cursor:pointer;">
<div class="ai-question-row">
<div class="ai-question-content">
<div class="ai-question-title">{_e(question)}</div>
{hint_html}
</div>
<span class="ai-ask-icon">\u25b6 \u8be2\u95eeAI</span>
</div>
</div>"""
    return f"""<section class="ppt-slide" data-index="{page.get('_index', 0)}" data-type="ai_interaction" data-layout="{layout or 'list'}">
<div class="slide-header"><h2>{_e(page.get('title', '向AI提问'))}</h2></div>
<div class="slide-body slide-content ai-interaction-body">
<div class="ai-prompt">{_e(prompt_text)}</div>
<div class="{wrapper_class}">
{q_html}
</div>
<div class="ai-footer">
点击问题向 AI 提问，或输入自己的问题！
</div>
</div>
</section>"""




def _render_listening_slide(page: dict, layout: str = None) -> str:
    audio_text = _get_field(page, "audio_text")
    audio_url = _get_field(page, "audio_url")
    subtitle = _get_field(page, "subtitle")
    title = page.get("title", "")
    questions = _get_field(page, "questions", [])
    q_html = ""
    for qi, q in enumerate(questions):
        opts_html = ""
        for oi, opt in enumerate(q.get("options", [])):
            opts_html += f'''<div class="option-item" onclick="selectOption(this)" data-q="{qi}" data-opt="{oi}">{chr(65+oi)}. {_e(opt)}</div>'''
        q_html += f'''<div class="question-card" data-correct="{q.get("answer",0)}" data-q="{qi}"><div class="question-stem">{qi+1}. {_e(q.get("stem",""))}</div><div class="options-wrap">{opts_html}</div><div class="explanation">{_e(q.get("explanation",""))}</div></div>'''
    audio_url_attr = f' data-audio-url="{_e(audio_url)}"' if audio_url else ""
    return f'''<section class="ppt-slide" data-index="{page.get('_index',0)}" data-type="listening">
<div class="slide-header"><span class="slide-header-text">{_e(title)}</span></div>
<div class="slide-body slide-content type-listening">
  <div class="audio-player-bar" data-text="{_e(audio_text)}"{audio_url_attr}>
    <button class="audio-play-btn slide-btn slide-btn-primary" onclick="toggleAudio(this)">\u25b6 \u64ad\u653e\u97f3\u9891</button>
    {(audio_text or subtitle) and '<button class="audio-expand-btn" onclick="toggleTextExpand(this)">\u25bc \u67e5\u770b\u539f\u6587</button>'}
    <div class="audio-status"></div>
  </div>
  <div class="speaking-text-wrap" style="display:none;">
    <div class="speaking-text">{_e(audio_text)}</div>
    {subtitle and f'<div class="speaking-translation">{_e(subtitle)}</div>'}
  </div>
  {q_html and f'<div class="listening-questions"><h3>\u542c\u529b\u7406\u89e3\u9898</h3>{q_html}</div>'}
</div>
</section>'''

def _render_speaking_slide(page: dict, layout: str = None) -> str:
    text = _get_field(page, "text")
    audio_url = _get_field(page, "audio_url")
    translation = _get_field(page, "translation")
    tips = _get_field(page, "tips")
    title = page.get("title", "")
    audio_url_attr = f' data-audio-url="{_e(audio_url)}"' if audio_url else ""
    return f'''<section class="ppt-slide" data-index="{page.get('_index',0)}" data-type="speaking">
<div class="slide-header"><span class="slide-header-text">{_e(title)}</span></div>
<div class="slide-body slide-content type-speaking">
  <div class="audio-player-bar" data-text="{_e(text)}"{audio_url_attr}>
    <button class="audio-play-btn slide-btn slide-btn-primary" onclick="toggleAudio(this)">\u25b6 \u64ad\u653e\u793a\u8303\u6717\u8bfb</button>
    <button class="audio-expand-btn" onclick="toggleTextExpand(this)">\u25bc \u67e5\u770b\u539f\u6587</button>
    <div class="audio-status"></div>
  </div>
  <div class="speaking-text-wrap" style="display:none;">
    <div class="speaking-text">{_e(text)}</div>
    {translation and f'<div class="speaking-translation">{_e(translation)}</div>'}
  </div>
  {tips and f'<div class="speaking-tips">{_e(tips)}</div>'}
</div>
</section>'''






# ===== Slide type renderer registry =====

_SLIDE_RENDERERS = {
    "catalog": _render_catalog_slide,
    "title": _render_title_slide,
    "objective": _render_objective_slide,
    "vocabulary": _render_vocabulary_slide,
    "dialogue": _render_dialogue_slide,
    "grammar": _render_grammar_slide,
    "practice": _render_practice_slide,
    "interactive": _render_interactive_slide,
    "ai_interaction": _render_ai_interaction_slide,
    "summary": _render_summary_slide,
    "listening": _render_listening_slide,
    "speaking": _render_speaking_slide,
}


def _e(text: str) -> str:
    """HTML 转义"""
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _get_field(page: dict, key: str, default: str | list = "") -> str | list:
    """Read a field from page-level first, then fall back to page.content[key]."""
    if key in page:
        return page[key]
    content = page.get("content", {})
    if isinstance(content, dict) and key in content:
        return content[key]
    return default


def _safe_format(template: str, **kwargs) -> str:
    """安全的模板替换，使用纯字符串替换而非 str.format() 占位符引擎"""
    for key, value in kwargs.items():
        placeholder = "{" + key + "}"
        if placeholder in template:
            template = template.replace(placeholder, str(value) if value is not None else "")
    # 还原 str.format() 转义的双花括号为单花括号
    # 模板中的 {{ 和 }} 原本是用于在 str.format() 中输出字面量 { 和 }
    template = template.replace("{{", "{").replace("}}", "}")
    return template


def pages_to_html_slides(pages: list[dict], visual_style: str = "") -> str:
    """将 JSON 页面列表转换为 HTML 幻灯片内容，支持布局变体

    Phase 3.5: 新增 visual_style 参数，注入 data-style 属性到每个幻灯片元素。
    """
    style_attr = f' data-style="{visual_style}"' if visual_style else ""
    top_bar_html = '<div class="slide-top-bar"></div>' if visual_style else ""
    slides = []
    for i, page in enumerate(pages):
        page = dict(page)
        page["_index"] = i
        layout = page.get("layout") or page.get("content", {}).get("_layout", None)
        page_type = page.get("type", "title")
        renderer = _SLIDE_RENDERERS.get(page_type, _render_title_slide)
        html = renderer(page, layout=layout)
        if visual_style:
            # 注入 data-style 属性
            html = html.replace(
                '<section class="ppt-slide"',
                f'<section class="ppt-slide"{style_attr}',
                1,
            )
            # 注入 slide-top-bar 元素（紧跟 <section>）
            html = html.replace(
                ">\n",
                ">\n" + top_bar_html + "\n",
                1,
            )
        slides.append(html)
    return "\n".join(slides)


def build_full_html(
    title: str,
    slides_html: str,
    theme_css: str,
    theme_name: str = "classic",
    total_slides: int = 0,
    present_mode: bool = True,
    css_variables: str = "",
    transition_type: str = "slide",
    transition_duration: int = 400,
    visual_style: str = "",
) -> str:
    """构建自包含的完整 HTML 幻灯片

    Args:
        present_mode: True 时添加 postMessage + 题目交互（iframe 授课用）；
                      False 时保留全屏 + 键盘导航（纯导出用）
        css_variables: 主题的 :root CSS 变量定义，注入到默认变量之后以实现覆盖
        transition_type: 页面切换动画类型 (fade/slide/push)
        transition_duration: 切换动画时长（毫秒）
        visual_style: Phase 3.5: 视觉风格名称（如 swiss-minimal/soft-rounded/editorial/...），
                      空字符串时不注入额外风格 CSS
    """
    # Phase 3.5: 视觉风格 CSS 注入
    style_css = ""
    if visual_style:
        gen_style_full, gen_style_vars = _get_style_bridge()
        style_css = gen_style_full(visual_style)

    # 将 css_variables 和 style_css 注入到默认 :root 块与 css_content 之间
    parts = []
    if css_variables:
        parts.append(css_variables.strip())
    if style_css:
        parts.append(style_css.strip())
    if theme_css:
        parts.append(theme_css)
    full_css = "\n".join(parts) if parts else ""

    return _safe_format(
        HTML_TEMPLATE,
        title=_e(title),
        slides_html=slides_html,
        theme_css=full_css,
        theme=_e(theme_name),
        total=str(total_slides),
        transition_type=transition_type,
        transition_duration=str(transition_duration),
    )


class PPTHtmlRenderer:
    """HTML 幻灯片渲染器"""

    @staticmethod
    def render_html_from_pages(
        pages: list[dict],
        title: str,
        theme_css: str,
        theme_name: str = "classic",
        present_mode: bool = True,
        css_variables: str = "",
        transition_type: str = "slide",
        transition_duration: int = 400,
        visual_style: str = "",
    ) -> str:
        """从 JSON 页面数据和主题 CSS 构建完整 HTML

        Phase 3.5: 新增 visual_style 参数，注入视觉风格 CSS。
        """
        slides_html = pages_to_html_slides(pages, visual_style)
        return build_full_html(
            title=title,
            slides_html=slides_html,
            theme_css=theme_css,
            theme_name=theme_name,
            total_slides=len(pages),
            present_mode=present_mode,
            css_variables=css_variables,
            transition_type=transition_type,
            transition_duration=transition_duration,
            visual_style=visual_style,
        )

    @staticmethod
    async def render_from_db(
        db: AsyncSession,
        pages: list[dict],
        title: str,
        theme_name: str = "classic",
        present_mode: bool = True,
        transition_type: str = "slide",
        transition_duration: int = 400,
        visual_style: str = "",
    ) -> str:
        """从数据库主题配置渲染 HTML

        Phase 3.5: 新增 visual_style 参数，透传给 render_html_from_pages。
        """
        theme = await PPTThemeService.get_theme_by_name(db, theme_name)
        if not theme:
            theme = await PPTThemeService.get_theme_by_name(db, "classic")
        theme_css = theme["css_content"] if theme else ""
        theme_vars = theme.get("css_variables", "") if theme else ""
        # 从主题的 style_skill 读取推荐切换动画
        style_skill = theme.get("style_skill") if theme else None
        if style_skill and isinstance(style_skill, dict):
            anim_cfg = style_skill.get("recommended_animations", {})
            if isinstance(anim_cfg, dict):
                transition_type = anim_cfg.get("transition", transition_type)
                transition_duration = anim_cfg.get("duration", transition_duration)
        return PPTHtmlRenderer.render_html_from_pages(
            pages, title, theme_css, theme_name,
            present_mode=present_mode, css_variables=theme_vars,
            transition_type=transition_type,
            transition_duration=transition_duration,
            visual_style=visual_style,
        )
