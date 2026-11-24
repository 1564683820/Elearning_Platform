// 面板拖拽与调整大小 hook — 让对话框可移动、可缩放
import { useCallback, useEffect, useRef, useState } from 'react';

const STORAGE_PREFIX = 'floating_panel_';

const MIN_WIDTH = 360;
const MIN_HEIGHT = 300;
const DEFAULT_WIDTH = 580;
const DEFAULT_HEIGHT = 640;
const EDGE_MARGIN = 16;
const RESIZE_HANDLE_SIZE = 8;

export interface PanelRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

function loadRect(key: string, maxW: number, maxH: number): PanelRect {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + key);
    if (raw) {
      const r = JSON.parse(raw) as PanelRect;
      r.x = Math.max(EDGE_MARGIN, Math.min(maxW - r.width - EDGE_MARGIN, r.x));
      r.y = Math.max(EDGE_MARGIN, Math.min(maxH - r.height - EDGE_MARGIN, r.y));
      r.width = Math.max(MIN_WIDTH, Math.min(maxW - EDGE_MARGIN * 2, r.width));
      r.height = Math.max(MIN_HEIGHT, Math.min(maxH - EDGE_MARGIN * 2, r.height));
      return r;
    }
  } catch { /* ignore */ }
  return {
    x: maxW - DEFAULT_WIDTH - 24,
    y: maxH - DEFAULT_HEIGHT - 80,
    width: Math.min(DEFAULT_WIDTH, maxW - 48),
    height: Math.min(DEFAULT_HEIGHT, maxH - 120),
  };
}

function saveRect(key: string, rect: PanelRect) {
  localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(rect));
}

type ResizeEdge = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';

type DragMode =
  | { type: 'move' }
  | { type: 'resize'; edge: ResizeEdge };

export function usePanelDrag(instanceKey: string) {
  const [rect, setRect] = useState<PanelRect>(() => {
    const maxW = window.innerWidth;
    const maxH = window.innerHeight;
    return loadRect(instanceKey, maxW, maxH);
  });

  // 用 ref 追踪最新 rect，避免 useEffect 闭包过期
  const rectRef = useRef(rect);
  rectRef.current = rect;

  const dragRef = useRef<{
    mode: DragMode;
    startX: number;
    startY: number;
    origRect: PanelRect;
  } | null>(null);

  const panelRef = useRef<HTMLDivElement>(null);

  // 开始拖拽（标题栏）
  const handleTitleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = {
      mode: { type: 'move' },
      startX: e.clientX,
      startY: e.clientY,
      origRect: rectRef.current,
    };
  }, []);

  // 开始调整大小（边缘拖把）
  const handleResizeMouseDown = useCallback((edge: ResizeEdge, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragRef.current = {
      mode: { type: 'resize', edge },
      startX: e.clientX,
      startY: e.clientY,
      origRect: rectRef.current,
    };
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragRef.current) return;
      const { mode, startX, startY, origRect } = dragRef.current;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      const maxW = window.innerWidth;
      const maxH = window.innerHeight;

      if (mode.type === 'move') {
        setRect({
          ...origRect,
          x: Math.max(EDGE_MARGIN - origRect.width + MIN_WIDTH, Math.min(maxW - origRect.width - EDGE_MARGIN, origRect.x + dx)),
          y: Math.max(EDGE_MARGIN, Math.min(maxH - origRect.height - EDGE_MARGIN, origRect.y + dy)),
        });
      } else if (mode.type === 'resize') {
        const edge = mode.edge;
        let { x, y, width, height } = origRect;

        if (edge.includes('e')) {
          width = Math.max(MIN_WIDTH, Math.min(maxW - x - EDGE_MARGIN, origRect.width + dx));
        }
        if (edge.includes('w')) {
          const newW = Math.max(MIN_WIDTH, Math.min(x + origRect.width - EDGE_MARGIN, origRect.width - dx));
          x = origRect.x + origRect.width - newW;
          width = newW;
        }
        if (edge.includes('s')) {
          height = Math.max(MIN_HEIGHT, Math.min(maxH - y - EDGE_MARGIN, origRect.height + dy));
        }
        if (edge.includes('n')) {
          const newH = Math.max(MIN_HEIGHT, Math.min(y + origRect.height - EDGE_MARGIN, origRect.height - dy));
          y = origRect.y + origRect.height - newH;
          height = newH;
        }

        setRect({ x, y, width, height });
      }
    };

    const handleMouseUp = () => {
      if (!dragRef.current) return;
      // 从 ref 读取最新的 rect，避免闭包过期
      saveRect(instanceKey, rectRef.current);
      dragRef.current = null;
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [instanceKey]); // 不再依赖 rect，避免拖拽中反复重注册 effect

  return {
    panelRef, rect,
    handleTitleMouseDown,
    handleResizeMouseDown,
    RESIZE_HANDLE_SIZE,
    MIN_WIDTH,
    MIN_HEIGHT,
  };
}
