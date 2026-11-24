// PPTX 预览查看器 — 支持剧场模式/全屏覆盖/进度条/触摸滑动/键盘导航
import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { radius, space, typography, green } from '../../design-system';

interface SlideData {
  index: number;
  svg: string;
}

interface PPTXViewerProps {
  slides: SlideData[];
  canvasWidth: number;
  canvasHeight: number;
  onClose: () => void;
  timings?: Record<string, number>;
  collection?: { id: string | number; title: string }[];
  currentCollectionId?: string | number;
  onSwitchCollection?: (id: string | number) => void;
}

const T = {
  overlay: 'rgba(255,255,255,0.88)',
  panelBg: '#ffffff',
  panelBorder: '#eaecef',
  canvasBg: '#f3f4f6',
  toolbarBg: '#ffffff',
  toolbarBorder: '#eaecef',
  statusBg: '#fafbfc',
  thumbBg: '#f8f9fa',
  thumbBorder: '#e5e7eb',
  textPrimary: '#1f2937',
  textSecondary: '#6b7280',
  textTertiary: '#9ca3af',
  accent: green.strong,
  accentBg: 'rgba(45,125,70,0.08)',
  btnBg: '#ffffff',
  btnBorder: '#d1d5db',
  pageBtnActive: green.strong,
  pageBtnInactive: '#e5e7eb',
  overlayNavBg: 'rgba(0,0,0,0.35)',
  overlayNavHover: 'rgba(0,0,0,0.55)',
  progressFill: green.strong,
};

export default function PPTXViewer({
  slides, canvasWidth, canvasHeight, onClose, timings,
  collection, currentCollectionId, onSwitchCollection,
}: PPTXViewerProps) {
  const [currentPage, setCurrentPage] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const [theaterMode, setTheaterMode] = useState(false);
  const [showOverlay, setShowOverlay] = useState(true);
  const [isFsNative, setIsFsNative] = useState(false);
  const viewerRef = useRef<HTMLDivElement>(null);
  const overlayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const aspectRatio = canvasWidth / canvasHeight;
  const totalPages = slides.length;

  // ── 键盘快捷键 ──
  useEffect(() => {
    const hk = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isFsNative) { document.exitFullscreen(); return; }
        onClose(); return;
      }
      if (e.key === 'ArrowLeft') setCurrentPage(p => Math.max(0, p - 1));
      if (e.key === 'ArrowRight') setCurrentPage(p => Math.min(totalPages - 1, p + 1));
      if (e.key === 't' || e.key === 'T') setTheaterMode(p => !p);
      if (e.key === 'f' || e.key === 'F') { e.preventDefault(); toggleFs(); }
      if (e.key === '+' || e.key === '=') setZoom(z => Math.min(3, z + 0.1));
      if (e.key === '-') setZoom(z => Math.max(0.3, z - 0.1));
      if (e.key === '0') setZoom(1);
      if (e.key === 'Home') setCurrentPage(0);
      if (e.key === 'End') setCurrentPage(totalPages - 1);
    };
    window.addEventListener('keydown', hk);
    return () => window.removeEventListener('keydown', hk);
  }, [onClose, totalPages, isFsNative]);

  // ── Native 全屏 ──
  const toggleFs = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().then(() => setIsFsNative(true)).catch(() => setFullscreen(true));
    } else {
      document.exitFullscreen().then(() => setIsFsNative(false));
    }
  }, []);

  useEffect(() => {
    const cb = () => { setIsFsNative(!!document.fullscreenElement); if (!document.fullscreenElement) setFullscreen(false); };
    document.addEventListener('fullscreenchange', cb);
    return () => document.removeEventListener('fullscreenchange', cb);
  }, []);

  // ── 全屏覆盖层自动隐藏 ──
  useEffect(() => {
    if (!fullscreen && !isFsNative) { setShowOverlay(true); return; }
    setShowOverlay(true);
    overlayTimerRef.current = setTimeout(() => setShowOverlay(false), 3000);
    const onMove = () => {
      setShowOverlay(true);
      if (overlayTimerRef.current) clearTimeout(overlayTimerRef.current);
      overlayTimerRef.current = setTimeout(() => setShowOverlay(false), 3000);
    };
    window.addEventListener('mousemove', onMove);
    return () => { window.removeEventListener('mousemove', onMove); if (overlayTimerRef.current) clearTimeout(overlayTimerRef.current); };
  }, [fullscreen, isFsNative, currentPage]);

  // ── 触摸滑动 ──
  useEffect(() => {
    const el = viewerRef.current;
    if (!el) return;
    let sx = 0, sy = 0;
    const ts = (e: TouchEvent) => { sx = e.touches[0].clientX; sy = e.touches[0].clientY; };
    const te = (e: TouchEvent) => {
      const dx = e.changedTouches[0].clientX - sx;
      const dy = e.changedTouches[0].clientY - sy;
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
        setCurrentPage(p => Math.max(0, dx > 0 ? p - 1 : Math.min(totalPages - 1, p + 1)));
      }
    };
    el.addEventListener('touchstart', ts, { passive: true });
    el.addEventListener('touchend', te, { passive: true });
    return () => { el.removeEventListener('touchstart', ts); el.removeEventListener('touchend', te); };
  }, [totalPages]);

  // ── 计算显示尺寸 ──
  const displaySize = useMemo(() => {
    const isFs = fullscreen || isFsNative;
    const wF = isFs ? 0.92 : (theaterMode ? 0.95 : 0.82);
    const hF = isFs ? 0.90 : (theaterMode ? 0.93 : 0.82);
    const maxW = window.innerWidth * wF;
    const maxH = window.innerHeight * hF;
    let w = maxW, h = w / aspectRatio;
    if (h > maxH) { h = maxH; w = h * aspectRatio; }
    return { width: w * zoom, height: h * zoom };
  }, [aspectRatio, zoom, fullscreen, isFsNative, theaterMode]);

  const slide = slides[currentPage];
  const progressPct = totalPages > 1 ? ((currentPage + 1) / totalPages) * 100 : 0;

  const extractThumbSvg = (s: string) => { const m = s.match(/<svg[\s\S]*?<\/svg>/i); return m ? m[0] : ''; };
  const prepSvg = (s: string) => s.replace(/\s+width\s*=\s*["'][^"']*["']/i, '').replace(/\s+height\s*=\s*["'][^"']*["']/i, '');
  const thumbSvgs = useMemo(() => slides.map(s => prepSvg(extractThumbSvg(s.svg))), [slides]);
  const displaySvg = useMemo(() => (slide ? prepSvg(slide.svg) : ''), [slide]);
  const goTo = (p: number) => setCurrentPage(Math.max(0, Math.min(totalPages - 1, p)));

  return (
    <div style={{
      position: 'fixed', inset: 0, background: T.overlay,
      backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
      display: 'flex', zIndex: 1000,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    }}>
      {/* ── 左侧缩略图（剧场模式隐藏） ── */}
      {!theaterMode && (
        <div style={{
          width: 280, background: T.panelBg,
          borderRight: `1px solid ${T.panelBorder}`,
          display: 'flex', flexDirection: 'column',
          padding: space.sm, gap: 2, overflow: 'auto', flexShrink: 0,
        }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: `0 ${space.xs}px ${space.sm}px`,
            borderBottom: `1px solid ${T.panelBorder}`, marginBottom: space.xs,
          }}>
            <span style={{ ...typography.eyebrow, color: T.textSecondary, fontSize: 11, letterSpacing: '0.5px' }}>
              幻灯片 · {totalPages} 页
            </span>
            <span style={{ fontSize: 9, color: T.textTertiary, background: T.thumbBg, padding: '1px 6px', borderRadius: radius.pill }}>
              PPTX→SVG
            </span>
          </div>
          {slides.map((s, i) => {
            const active = currentPage === i;
            return (
              <div key={s.index} onClick={() => setCurrentPage(i)}
                style={{
                  padding: '8px 12px', borderRadius: radius.md, cursor: 'pointer',
                  background: active ? T.accentBg : 'transparent',
                  border: `1px solid ${active ? T.accent : 'transparent'}`,
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={e => { if (!active) e.currentTarget.style.background = '#f9fafb'; }}
                onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}
              >
                <div style={{
                  width: '100%', height: 110, borderRadius: 4, overflow: 'hidden',
                  position: 'relative', background: T.thumbBg,
                  border: `1px solid ${active ? T.accent : T.thumbBorder}`,
                  opacity: active ? 1 : 0.65, transition: 'all 0.15s',
                }}>
                  {thumbSvgs[i] ? (
                    <svg viewBox={`0 0 ${canvasWidth} ${canvasHeight}`}
                      preserveAspectRatio="xMidYMid slice"
                      style={{ width: '100%', height: '100%' }}
                      dangerouslySetInnerHTML={{ __html: thumbSvgs[i] }}
                    />
                  ) : (
                    <span style={{ fontSize: 9, color: T.textTertiary }}>—</span>
                  )}
                  <span style={{
                    position: 'absolute', top: 4, left: 4, width: 20, height: 20,
                    borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 9, fontWeight: 600,
                    color: active ? '#fff' : T.textSecondary,
                    background: active ? T.accent : 'rgba(255,255,255,0.85)',
                    backdropFilter: 'blur(4px)', boxShadow: '0 1px 3px rgba(0,0,0,0.12)',
                  }}>
                    {s.index}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── 右侧主展示 ── */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0,
        background: T.canvasBg, position: 'relative',
      }}>
        {/* 进度条 */}
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, zIndex: 10, background: '#e5e7eb' }}>
          <div style={{
            height: '100%', width: `${progressPct}%`, background: T.progressFill,
            transition: 'width 0.3s ease', borderRadius: '0 2px 2px 0',
          }} />
        </div>

        {/* 顶部工具栏 */}
        <div style={{
          padding: `${space.sm}px ${space.md}px`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          background: T.toolbarBg, borderBottom: `1px solid ${T.toolbarBorder}`,
          userSelect: 'none',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: space.sm }}>
            <div style={{
              width: 28, height: 28, borderRadius: radius.md, background: T.accentBg,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke={T.accent} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="1" width="12" height="14" rx="1.5" />
                <path d="M5 5h6" /><path d="M5 8h4" /><path d="M5 11h5" />
              </svg>
            </div>
            <span style={{ ...typography.subhead, fontWeight: 600, color: T.textPrimary, fontSize: 15 }}>PPTX 预览</span>
            {/* 集合切换 */}
            {collection && collection.length > 1 && (
              <select value={String(currentCollectionId ?? '')}
                onChange={e => onSwitchCollection?.(e.target.value)}
                style={{
                  marginLeft: 8, fontSize: 12, padding: '3px 8px', borderRadius: radius.sm,
                  border: `1px solid ${T.btnBorder}`, background: T.btnBg, color: T.textSecondary,
                  cursor: 'pointer', outline: 'none',
                }}
              >
                {collection.map(c => <option key={String(c.id)} value={String(c.id)}>{c.title}</option>)}
              </select>
            )}
            <span style={{ fontSize: 13, color: T.textTertiary, background: T.thumbBg, padding: '2px 10px', borderRadius: radius.pill, whiteSpace: 'nowrap' }}>
              第 {currentPage + 1} / {totalPages} 页
            </span>
          </div>

          {/* 右侧控件 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: space.sm }}>
            {/* 剧场模式 */}
            <BtnIcon active={theaterMode} accent={T.accent} onClick={() => setTheaterMode(p => !p)}
              title={theaterMode ? '显示侧栏 (T)' : '剧场模式 (T)'}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                {theaterMode ? (
                  <><rect x="2" y="3" width="12" height="10" rx="1" /><path d="M6 3v10" /></>
                ) : (
                  <><rect x="3" y="3" width="10" height="10" rx="1" /><path d="M3 7h3" /><path d="M3 10h2" /></>
                )}
              </svg>
            </BtnIcon>

            {/* 缩放 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 2, background: T.thumbBg, borderRadius: radius.md, padding: 2 }}>
              <ZoomBtn onClick={() => setZoom(z => Math.max(0.3, z - 0.1))} title="缩小" label="−" />
              <span style={{ color: T.textSecondary, fontSize: 12, minWidth: 40, textAlign: 'center', fontWeight: 500 }}>{Math.round(zoom * 100)}%</span>
              <ZoomBtn onClick={() => setZoom(z => Math.min(3, z + 0.1))} title="放大" label="+" />
              <button onClick={() => setZoom(1)} style={{
                ...zoomBtnS, fontSize: 10, borderLeft: `1px solid ${T.btnBorder}`,
                marginLeft: 2, paddingLeft: 6, borderRadius: 0,
              }} title="重置缩放">100%</button>
            </div>

            <div style={{ width: 1, height: 24, background: T.panelBorder }} />

            {/* 全屏 */}
            <BtnIcon active={fullscreen || isFsNative} accent={T.accent} onClick={toggleFs} title="全屏 (F)">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                {(fullscreen || isFsNative) ? (
                  <><path d="M6 1H1v5" /><path d="M10 1h5v5" /><path d="M6 15H1v-5" /><path d="M10 15h5v-5" /></>
                ) : (
                  <><path d="M6 3H3v3" /><path d="M10 3h3v3" /><path d="M6 13H3v-3" /><path d="M10 13h3v-3" /></>
                )}
              </svg>
            </BtnIcon>

            {/* 翻页 */}
            <div style={{ display: 'flex', gap: 2, alignItems: 'center', background: T.thumbBg, borderRadius: radius.md, padding: 2 }}>
              <NavBtn onClick={() => goTo(0)} disabled={currentPage === 0} title="首页">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M12 3L7 8l5 5" /><path d="M5 3v10" />
                </svg>
              </NavBtn>
              <NavBtn onClick={() => goTo(currentPage - 1)} disabled={currentPage === 0} title="上一页 (←)">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 3L5 8l5 5" /></svg>
              </NavBtn>
              <div style={{ display: 'flex', gap: 2 }}>
                {totalPages <= 10 ? slides.map((_, i) => (
                  <button key={i} onClick={() => setCurrentPage(i)} style={{
                    ...pageBtnS, background: currentPage === i ? T.pageBtnActive : T.pageBtnInactive,
                    color: currentPage === i ? '#fff' : T.textSecondary,
                  }}>{i + 1}</button>
                )) : (
                  <span style={{ color: T.textSecondary, fontSize: 12, padding: '0 6px', fontWeight: 500 }}>{currentPage + 1}</span>
                )}
              </div>
              <NavBtn onClick={() => goTo(currentPage + 1)} disabled={currentPage >= totalPages - 1} title="下一页 (→)">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 3l5 5-5 5" /></svg>
              </NavBtn>
              <NavBtn onClick={() => goTo(totalPages - 1)} disabled={currentPage >= totalPages - 1} title="末页">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 3l5 5-5 5" /><path d="M11 3v10" /></svg>
              </NavBtn>
            </div>

            {/* 跳转输入 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 2, background: T.thumbBg, borderRadius: radius.md, padding: '2px 6px' }}>
              <input type="number" min={1} max={totalPages} value={currentPage + 1}
                onChange={e => { const v = parseInt(e.target.value, 10); if (v >= 1 && v <= totalPages) goTo(v - 1); }}
                style={{ width: 36, fontSize: 11, border: 'none', background: 'transparent', textAlign: 'center', outline: 'none', color: T.textSecondary, fontWeight: 500, padding: '2px 0' }}
              />
              <span style={{ fontSize: 10, color: T.textTertiary }}>/ {totalPages}</span>
            </div>

            {/* 关闭 */}
            <button onClick={onClose} style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              padding: '6px 14px', fontSize: 13, fontWeight: 500, cursor: 'pointer',
              background: T.panelBg, color: T.textSecondary, border: `1px solid ${T.btnBorder}`,
              borderRadius: radius.md, transition: 'all 0.15s', whiteSpace: 'nowrap',
            }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="3" y1="3" x2="13" y2="13" /><line x1="13" y1="3" x2="3" y2="13" />
              </svg>
              <span style={{ marginLeft: 6 }}>关闭</span>
            </button>
          </div>
        </div>

        {/* ─── SVG 展示区 ─── */}
        <div ref={viewerRef} style={{
          flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
          overflow: 'auto', padding: space.sm,
          background: `radial-gradient(ellipse at center, #f9fafb 0%, ${T.canvasBg} 100%)`,
        }}>
          {slide ? (
            <div dangerouslySetInnerHTML={{ __html: displaySvg }} style={{
              width: displaySize.width, height: displaySize.height, background: '#ffffff',
              boxShadow: (fullscreen || isFsNative) ? '0 2px 12px rgba(0,0,0,0.15)' : '0 4px 24px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.04)',
              borderRadius: 6, overflow: 'hidden', transition: 'width 0.25s ease, height 0.25s ease, box-shadow 0.25s ease',
            }} />
          ) : (
            <div style={{ textAlign: 'center', color: T.textTertiary }}>
              <svg width="40" height="40" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" style={{ marginBottom: 12, opacity: 0.5 }}>
                <rect x="2" y="1" width="12" height="14" rx="1.5" /><path d="M5 5h6" /><path d="M5 8h4" /><path d="M5 11h5" />
              </svg>
              <p style={{ fontSize: 14, margin: 0 }}>暂无幻灯片内容</p>
            </div>
          )}
        </div>

        {/* ─── 底部状态栏 ─── */}
        <div style={{
          padding: `8px ${space.md}px`, background: T.statusBg,
          borderTop: `1px solid ${T.toolbarBorder}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span style={{ color: T.textTertiary, fontSize: 11, display: 'flex', alignItems: 'center', gap: 6 }}>
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
              <rect x="1" y="3" width="14" height="10" rx="1.5" /><path d="M4 1v2" /><path d="M8 1v2" /><path d="M12 1v2" />
            </svg>
            <span>{canvasWidth}×{canvasHeight}</span>
            <span style={{ opacity: 0.4 }}>·</span>
            <span>{totalPages} 页幻灯片</span>
            {timings?.total_ms ? <><span style={{ opacity: 0.4 }}>·</span><span>{timings.total_ms}ms</span></> : null}
          </span>
          <span style={{ color: T.textTertiary, fontSize: 11, display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ padding: '1px 8px', background: T.thumbBg, borderRadius: radius.pill, fontSize: 10, display: 'flex', gap: 8 }}>
              <span>← → 翻页</span><span>F 全屏</span><span>T 剧场</span><span>Esc 关闭</span>
            </span>
          </span>
        </div>

        {/* ─── 全屏覆盖导航 ─── */}
        {(fullscreen || isFsNative) && (
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
            justifyContent: 'space-between', pointerEvents: 'none', zIndex: 20,
            opacity: showOverlay ? 1 : 0, transition: 'opacity 0.4s ease',
          }}>
            <FsNavBtn side="left" onClick={() => goTo(currentPage - 1)} disabled={currentPage === 0}>
              <svg width="28" height="28" viewBox="0 0 16 16" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" style={{ filter: 'drop-shadow(0 1px 3px rgba(0,0,0,0.3))' }}>
                <path d="M10 3L5 8l5 5" />
              </svg>
            </FsNavBtn>
            <FsNavBtn side="right" onClick={() => goTo(currentPage + 1)} disabled={currentPage >= totalPages - 1}>
              <svg width="28" height="28" viewBox="0 0 16 16" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" style={{ filter: 'drop-shadow(0 1px 3px rgba(0,0,0,0.3))' }}>
                <path d="M6 3l5 5-5 5" />
              </svg>
            </FsNavBtn>
          </div>
        )}

        {/* ─── 全屏底部关闭条 ─── */}
        {(fullscreen || isFsNative) && (
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0, zIndex: 20,
            display: 'flex', justifyContent: 'center', padding: '16px 0',
            opacity: showOverlay ? 1 : 0, transition: 'opacity 0.4s ease',
            pointerEvents: showOverlay ? 'auto' : 'none',
          }}>
            <button onClick={onClose} style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 20px', fontSize: 13, fontWeight: 500,
              background: 'rgba(0,0,0,0.55)', color: '#fff', border: 'none',
              borderRadius: radius.pill, cursor: 'pointer',
              backdropFilter: 'blur(8px)', boxShadow: '0 2px 12px rgba(0,0,0,0.2)',
            }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="3" y1="3" x2="13" y2="13" /><line x1="13" y1="3" x2="3" y2="13" />
              </svg>
              退出全屏 (Esc)
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── 子组件 ──────────────────────────────────────────

function BtnIcon({ active, accent, onClick, title, children }: any) {
  return (
    <button onClick={onClick} style={{
      width: 32, height: 32, borderRadius: radius.md, border: '1px solid transparent',
      background: active ? 'rgba(45,125,70,0.08)' : 'transparent',
      color: active ? accent : '#6b7280', cursor: 'pointer',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      transition: 'all 0.12s',
    }} title={title}>
      {children}
    </button>
  );
}

const zoomBtnS: React.CSSProperties = {
  width: 28, height: 28, borderRadius: radius.sm, border: 'none',
  background: 'transparent', color: '#6b7280', cursor: 'pointer',
  fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontWeight: 500, lineHeight: 1, transition: 'all 0.12s',
};

function ZoomBtn({ onClick, title, label }: any) {
  return (
    <button onClick={onClick} style={zoomBtnS} title={title}>{label}</button>
  );
}

const navS: React.CSSProperties = {
  width: 28, height: 28, borderRadius: radius.sm, border: 'none',
  background: 'transparent', cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  transition: 'all 0.12s', color: '#1f2937',
};

function NavBtn({ onClick, disabled, title, children }: any) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      ...navS, opacity: disabled ? 0.35 : 1, cursor: disabled ? 'not-allowed' : 'pointer',
    }} title={title}>
      {children}
    </button>
  );
}

const pageBtnS: React.CSSProperties = {
  width: 22, height: 22, borderRadius: radius.sm, border: 'none',
  cursor: 'pointer', fontSize: 10, fontWeight: 600,
  transition: 'all 0.12s', lineHeight: 1,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};

function FsNavBtn({ side, onClick, disabled, children }: any) {
  return (
    <div onClick={onClick} style={{
      pointerEvents: disabled ? 'none' : 'auto', cursor: disabled ? 'default' : 'pointer',
      width: 80, height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: `linear-gradient(to ${side}, ${T.overlayNavBg}, transparent)`,
      opacity: disabled ? 0.3 : 1, transition: 'background 0.2s',
    }}
      onMouseEnter={e => { if (!disabled) e.currentTarget.style.background = `linear-gradient(to ${side}, ${T.overlayNavHover}, transparent)`; }}
      onMouseLeave={e => { e.currentTarget.style.background = `linear-gradient(to ${side}, ${T.overlayNavBg}, transparent)`; }}
    >
      {children}
    </div>
  );
}
