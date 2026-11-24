// SVG 幻灯片查看器 — 浅色主题全屏模态展示 PPTX→SVG 转换结果
import { useState, useMemo, useRef, useEffect } from 'react';
import {
  radius, space, typography, shadows, green,
} from '../../design-system';

interface SlideData {
  index: number;
  svg: string;
}

interface SVGSlideViewerProps {
  slides: SlideData[];
  canvasWidth: number;
  canvasHeight: number;
  onClose: () => void;
  timings?: Record<string, number>;
}

// ─── 浅色主题色板 ──────────────────────────────────────
const LIGHT = {
  overlay: 'rgba(255,255,255,0.88)',
  panelBg: '#ffffff',
  panelBorder: '#eaecef',
  canvasBg: '#f3f4f6',
  toolbarBg: '#ffffff',
  toolbarBorder: '#eaecef',
  statusBg: '#fafbfc',
  thumbBg: '#f8f9fa',
  thumbActive: '#e8f5e9',
  thumbBorder: '#e5e7eb',
  textPrimary: '#1f2937',
  textSecondary: '#6b7280',
  textTertiary: '#9ca3af',
  accent: green.strong,
  accentLight: green.bg,
  accentBg: 'rgba(45,125,70,0.08)',
  btnBg: '#ffffff',
  btnBorder: '#d1d5db',
  btnHover: '#f3f4f6',
  pageBtnActive: green.strong,
  pageBtnInactive: '#e5e7eb',
};

export default function SVGSlideViewer({ slides, canvasWidth, canvasHeight, onClose, timings }: SVGSlideViewerProps) {
  const [currentPage, setCurrentPage] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const aspectRatio = canvasWidth / canvasHeight;

  // 监听 Escape 键关闭
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft') setCurrentPage(p => Math.max(0, p - 1));
      if (e.key === 'ArrowRight') setCurrentPage(p => Math.min(slides.length - 1, p + 1));
      if (e.key === '+' || e.key === '=') setZoom(z => Math.min(3, z + 0.1));
      if (e.key === '-') setZoom(z => Math.max(0.3, z - 0.1));
      if (e.key === '0') setZoom(1);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose, slides.length]);

  // 计算 SVG 缩放后的显示尺寸
  const displaySize = useMemo(() => {
    const maxW = fullscreen ? window.innerWidth * 0.92 : window.innerWidth * 0.82;
    const maxH = fullscreen ? window.innerHeight * 0.90 : window.innerHeight * 0.82;
    let w = maxW;
    let h = w / aspectRatio;
    if (h > maxH) {
      h = maxH;
      w = h * aspectRatio;
    }
    return { width: w * zoom, height: h * zoom };
  }, [aspectRatio, zoom, fullscreen]);

  const slide = slides[currentPage];

  // 从完整 SVG 中裁剪 thumbnail（提取 <svg>...</svg>）
  const extractThumbSvg = (fullSvg: string): string => {
    const match = fullSvg.match(/<svg[\s\S]*?<\/svg>/i);
    return match ? match[0] : '';
  };

  // 去除 <svg> 标签上的 width/height，保留 viewBox，让 SVG 随容器 CSS 缩放
  const prepareSvgForContainer = (fullSvg: string): string => {
    return fullSvg
      .replace(/\s+width\s*=\s*["'][^"']*["']/i, '')
      .replace(/\s+height\s*=\s*["'][^"']*["']/i, '');
  };

  // 预计算缩略图 SVG（剥离 width/height 以适配缩略图容器）
  const thumbSvgs = useMemo(
    () => slides.map(s => prepareSvgForContainer(extractThumbSvg(s.svg))),
    [slides],
  );

  // 主展示区 SVG：去掉 width/height 以适配容器尺寸
  const displaySvg = useMemo(
    () => (slide ? prepareSvgForContainer(slide.svg) : ''),
    [slide],
  );

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: LIGHT.overlay,
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      display: 'flex', zIndex: 1000,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    }}>
      {/* ── 左侧缩略图面板 ── */}
      <div style={{
        width: 280, background: LIGHT.panelBg,
        borderRight: `1px solid ${LIGHT.panelBorder}`,
        display: 'flex', flexDirection: 'column',
        padding: space.sm, gap: 2, overflow: 'auto', flexShrink: 0,
      }}>
        {/* 缩略图标题 */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: `0 ${space.xs}px ${space.sm}px`,
          borderBottom: `1px solid ${LIGHT.panelBorder}`,
          marginBottom: space.xs,
        }}>
          <span style={{
            ...typography.eyebrow, color: LIGHT.textSecondary,
            fontSize: 11, letterSpacing: '0.5px',
          }}>
            幻灯片 · {slides.length} 页
          </span>
          <span style={{
            fontSize: 9, color: LIGHT.textTertiary,
            background: LIGHT.thumbBg, padding: '1px 6px',
            borderRadius: radius.pill, letterSpacing: '0.3px',
          }}>
            PPTX→SVG
          </span>
        </div>

        {/* 缩略图列表 */}
        {slides.map((s, i) => {
          const isActive = currentPage === i;
          const thumbSvg = thumbSvgs[i];
          return (
            <div
              key={s.index}
              onClick={() => setCurrentPage(i)}
              style={{
                padding: '8px 12px', borderRadius: radius.md, cursor: 'pointer',
                background: isActive ? LIGHT.accentBg : 'transparent',
                border: `1px solid ${isActive ? LIGHT.accent : 'transparent'}`,
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.background = '#f9fafb';
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.background = 'transparent';
              }}
            >
              {/* 缩略图预览（含页码角标覆盖层） */}
              <div style={{
                width: '100%', height: 160, borderRadius: 4, overflow: 'hidden',
                position: 'relative',
                background: LIGHT.thumbBg,
                border: `1px solid ${isActive ? LIGHT.accent : LIGHT.thumbBorder}`,
                opacity: isActive ? 1 : 0.65,
                transition: 'all 0.15s',
              }}>
                {thumbSvg ? (
                  <svg viewBox={`0 0 ${canvasWidth} ${canvasHeight}`}
                    preserveAspectRatio="xMidYMid slice"
                    style={{ width: '100%', height: '100%' }}
                    dangerouslySetInnerHTML={{ __html: thumbSvg }}
                  />
                ) : (
                  <span style={{ fontSize: 9, color: LIGHT.textTertiary }}>—</span>
                )}
                {/* 页码角标 */}
                <span style={{
                  position: 'absolute', top: 4, left: 4,
                  width: 20, height: 20, borderRadius: '50%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 9, fontWeight: 600,
                  color: isActive ? '#fff' : LIGHT.textSecondary,
                  background: isActive ? LIGHT.accent : 'rgba(255,255,255,0.85)',
                  backdropFilter: 'blur(4px)',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.12)',
                }}>
                  {s.index}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── 右侧主展示区 ── */}
      <div ref={containerRef} style={{
        flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0,
        background: LIGHT.canvasBg,
      }}>
        {/* 顶部工具栏 */}
        <div style={{
          padding: `${space.sm}px ${space.md}px`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          background: LIGHT.toolbarBg,
          borderBottom: `1px solid ${LIGHT.toolbarBorder}`,
          userSelect: 'none',
        }}>
          {/* 左侧信息 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: space.sm }}>
            <div style={{
              width: 28, height: 28, borderRadius: radius.md,
              background: LIGHT.accentBg, display: 'flex', alignItems: 'center',
              justifyContent: 'center',
            }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke={LIGHT.accent} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="1" width="12" height="14" rx="1.5" />
                <path d="M5 5h6" /><path d="M5 8h4" /><path d="M5 11h5" />
              </svg>
            </div>
            <span style={{
              ...typography.subhead, fontWeight: 600, color: LIGHT.textPrimary,
              fontSize: 15,
            }}>
              PPTX 预览
            </span>
            <span style={{
              fontSize: 13, color: LIGHT.textTertiary,
              background: LIGHT.thumbBg, padding: '2px 10px',
              borderRadius: radius.pill,
            }}>
              第 {currentPage + 1} / {slides.length} 页
            </span>
          </div>

          {/* 右侧控制区 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: space.sm }}>
            {/* 缩放控制 */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 2,
              background: LIGHT.thumbBg, borderRadius: radius.md,
              padding: 2,
            }}>
              <button onClick={() => setZoom(z => Math.max(0.3, z - 0.1))}
                style={lightBtnStyle} title="缩小" aria-label="缩小">−</button>
              <span style={{
                color: LIGHT.textSecondary, fontSize: 12, minWidth: 40,
                textAlign: 'center', fontWeight: 500,
              }}>
                {Math.round(zoom * 100)}%
              </span>
              <button onClick={() => setZoom(z => Math.min(3, z + 0.1))}
                style={lightBtnStyle} title="放大" aria-label="放大">+</button>
              <button onClick={() => setZoom(1)} style={{
                ...lightBtnStyle, fontSize: 10,
                borderLeft: `1px solid ${LIGHT.btnBorder}`,
                marginLeft: 2, paddingLeft: 6, borderRadius: 0,
              }} title="重置缩放" aria-label="重置缩放">100%</button>
            </div>

            {/* 分隔线 */}
            <div style={{ width: 1, height: 24, background: LIGHT.panelBorder }} />

            {/* 全屏切换 */}
            <button onClick={() => setFullscreen(!fullscreen)} style={{
              ...toolIconBtnStyle,
              background: fullscreen ? LIGHT.accentBg : 'transparent',
              color: fullscreen ? LIGHT.accent : LIGHT.textSecondary,
              borderColor: fullscreen ? LIGHT.accent : 'transparent',
            }} title={fullscreen ? '退出全屏' : '全屏展示'} aria-label={fullscreen ? '退出全屏' : '全屏展示'}>
              {fullscreen ? (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M6 1H1v5" /><path d="M10 1h5v5" /><path d="M6 15H1v-5" /><path d="M10 15h5v-5" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M6 3H3v3" /><path d="M10 3h3v3" /><path d="M6 13H3v-3" /><path d="M10 13h3v-3" />
                </svg>
              )}
            </button>

            {/* 翻页控制 */}
            <div style={{
              display: 'flex', gap: 2, alignItems: 'center',
              background: LIGHT.thumbBg, borderRadius: radius.md, padding: 2,
            }}>
              <button
                onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
                disabled={currentPage === 0}
                style={{
                  ...navIconStyle,
                  opacity: currentPage === 0 ? 0.35 : 1,
                  cursor: currentPage === 0 ? 'not-allowed' : 'pointer',
                }}
                title="上一页" aria-label="上一页"
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M10 3L5 8l5 5" />
                </svg>
              </button>

              <div style={{ display: 'flex', gap: 2 }}>
                {slides.length <= 10 ? (
                  slides.map((_, i) => (
                    <button key={i} onClick={() => setCurrentPage(i)}
                      style={{
                        ...pageBtnStyle,
                        background: currentPage === i ? LIGHT.pageBtnActive : LIGHT.pageBtnInactive,
                        color: currentPage === i ? '#fff' : LIGHT.textSecondary,
                      }}
                      aria-label={`第 ${i + 1} 页`}
                    >
                      {i + 1}
                    </button>
                  ))
                ) : (
                  <span style={{ color: LIGHT.textSecondary, fontSize: 12, padding: '0 6px', fontWeight: 500 }}>
                    {currentPage + 1}
                  </span>
                )}
              </div>

              <button
                onClick={() => setCurrentPage(Math.min(slides.length - 1, currentPage + 1))}
                disabled={currentPage >= slides.length - 1}
                style={{
                  ...navIconStyle,
                  opacity: currentPage >= slides.length - 1 ? 0.35 : 1,
                  cursor: currentPage >= slides.length - 1 ? 'not-allowed' : 'pointer',
                }}
                title="下一页" aria-label="下一页"
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M6 3l5 5-5 5" />
                </svg>
              </button>
            </div>

            {/* 关闭按钮 */}
            <button onClick={onClose} style={closeBtnStyle} aria-label="关闭预览">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="3" y1="3" x2="13" y2="13" /><line x1="13" y1="3" x2="3" y2="13" />
              </svg>
              <span style={{ marginLeft: 6 }}>关闭</span>
            </button>
          </div>
        </div>

        {/* SVG 展示区 */}
        <div style={{
          flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
          overflow: 'auto', padding: space.sm,
          background: `radial-gradient(ellipse at center, #f9fafb 0%, ${LIGHT.canvasBg} 100%)`,
        }}>
          {slide ? (
            <div
              dangerouslySetInnerHTML={{ __html: displaySvg }}
              style={{
                width: displaySize.width,
                height: displaySize.height,
                background: '#ffffff',
                boxShadow: fullscreen ? shadows.modal : '0 4px 24px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.04)',
                borderRadius: 6,
                overflow: 'hidden',
                transition: 'width 0.25s ease, height 0.25s ease, box-shadow 0.25s ease',
              }}
            />
          ) : (
            <div style={{ textAlign: 'center', color: LIGHT.textTertiary }}>
              <svg width="40" height="40" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" style={{ marginBottom: 12, opacity: 0.5 }}>
                <rect x="2" y="1" width="12" height="14" rx="1.5" />
                <path d="M5 5h6" /><path d="M5 8h4" /><path d="M5 11h5" />
              </svg>
              <p style={{ fontSize: 14, margin: 0 }}>暂无幻灯片内容</p>
            </div>
          )}
        </div>

        {/* 底部状态栏 */}
        <div style={{
          padding: `8px ${space.md}px`,
          background: LIGHT.statusBg,
          borderTop: `1px solid ${LIGHT.toolbarBorder}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span style={{ color: LIGHT.textTertiary, fontSize: 11, display: 'flex', alignItems: 'center', gap: 6 }}>
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
              <rect x="1" y="3" width="14" height="10" rx="1.5" />
              <path d="M4 1v2" /><path d="M8 1v2" /><path d="M12 1v2" />
            </svg>
            <span>{canvasWidth}×{canvasHeight}</span>
            <span style={{ opacity: 0.4 }}>·</span>
            <span>{slides.length} 页幻灯片</span>
            {timings?.total_ms ? (
              <>
                <span style={{ opacity: 0.4 }}>·</span>
                <span>{timings.total_ms}ms</span>
              </>
            ) : null}
          </span>
          <span style={{
            color: LIGHT.textTertiary, fontSize: 11, display: 'flex', gap: 12, alignItems: 'center',
          }}>
            {timings && (
              <>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{
                    width: 6, height: 6, borderRadius: '50%', background: LIGHT.accent,
                    display: 'inline-block',
                  }} />
                  SVG→PPTX {timings.pptx_gen_ms || '-'}ms
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{
                    width: 6, height: 6, borderRadius: '50%', background: green.primary,
                    display: 'inline-block',
                  }} />
                  PPTX→SVG {timings.pptx_to_svg_ms || '-'}ms
                </span>
              </>
            )}
            <span style={{
              padding: '1px 8px', background: LIGHT.thumbBg, borderRadius: radius.pill,
              fontSize: 10,
            }}>
              键盘导航 ← → 切换
            </span>
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── 样式 ──────────────────────────────────────────────

// 缩放按钮
const lightBtnStyle: React.CSSProperties = {
  width: 28, height: 28, borderRadius: radius.sm, border: 'none',
  background: 'transparent', color: LIGHT.textSecondary, cursor: 'pointer',
  fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontWeight: 500, lineHeight: 1, transition: 'all 0.12s',
};

// 工具栏图标按钮
const toolIconBtnStyle: React.CSSProperties = {
  width: 32, height: 32, borderRadius: radius.md, border: '1px solid transparent',
  background: 'transparent', cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  transition: 'all 0.12s',
  color: LIGHT.textSecondary,
};

// 翻页导航按钮
const navIconStyle: React.CSSProperties = {
  width: 28, height: 28, borderRadius: radius.sm, border: 'none',
  background: 'transparent', cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  transition: 'all 0.12s',
  color: LIGHT.textPrimary,
};

// 页码按钮
const pageBtnStyle: React.CSSProperties = {
  width: 22, height: 22, borderRadius: radius.sm, border: 'none',
  cursor: 'pointer', fontSize: 10, fontWeight: 600,
  transition: 'all 0.12s', lineHeight: 1,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};

// 关闭按钮
const closeBtnStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  padding: '6px 14px', fontSize: 13, fontWeight: 500, cursor: 'pointer',
  background: LIGHT.panelBg, color: LIGHT.textSecondary,
  border: `1px solid ${LIGHT.btnBorder}`,
  borderRadius: radius.md, transition: 'all 0.15s', whiteSpace: 'nowrap',
};
