// 悬浮球拖拽 hook — 支持鼠标/触摸拖拽，localStorage 持久化位置
import { useCallback, useEffect, useRef, useState } from 'react';

const STORAGE_KEY = 'floating_assistant_pos';
const DEFAULT_RIGHT = 20;
const DEFAULT_BOTTOM = 80;
const EDGE_MARGIN = 8;
const DRAG_THRESHOLD = 5; // 超过此 px 才算拖拽，避免误触

export interface BallPosition {
  right: number;
  bottom: number;
}

function loadPosition(): BallPosition {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      // 校验：位置必须在可视范围（不要跑出屏幕）
      const BALL_SIZE = 48;
      const MAX_RIGHT = window.innerWidth - BALL_SIZE - EDGE_MARGIN;
      const MAX_BOTTOM = window.innerHeight - BALL_SIZE - EDGE_MARGIN;
      if (
        typeof parsed.right !== 'number' || typeof parsed.bottom !== 'number' ||
        parsed.right < -100 || parsed.right > MAX_RIGHT + 100 ||
        parsed.bottom < -100 || parsed.bottom > MAX_BOTTOM + 100
      ) {
        return { right: DEFAULT_RIGHT, bottom: DEFAULT_BOTTOM };
      }
      return parsed;
    }
  } catch { /* ignore */ }
  return { right: DEFAULT_RIGHT, bottom: DEFAULT_BOTTOM };
}

function savePosition(pos: BallPosition) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(pos));
}

export function useDrag() {
  const [pos, setPos] = useState<BallPosition>(loadPosition);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<{
    startX: number; startY: number;
    elX: number; elY: number;
    moved: boolean;
  } | null>(null);
  const ballRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      elX: window.innerWidth - pos.right,
      elY: window.innerHeight - pos.bottom,
      moved: false,
    };
    setIsDragging(true);
  }, [pos]);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!dragRef.current) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    if (!dragRef.current.moved && Math.abs(dx) + Math.abs(dy) > DRAG_THRESHOLD) {
      dragRef.current.moved = true;
    }
    const newLeft = dragRef.current.elX + dx;
    const newTop = dragRef.current.elY + dy;
    // 边界限制
    const clampedLeft = Math.max(EDGE_MARGIN, Math.min(window.innerWidth - 48 - EDGE_MARGIN, newLeft));
    const clampedTop = Math.max(EDGE_MARGIN, Math.min(window.innerHeight - 48 - EDGE_MARGIN, newTop));
    const newRight = window.innerWidth - clampedLeft - 48;
    const newBottom = window.innerHeight - clampedTop - 48;
    setPos({ right: newRight, bottom: newBottom });
  }, []);

  const handleMouseUp = useCallback(() => {
    if (!dragRef.current) return;
    savePosition(pos);
    setIsDragging(false);
    dragRef.current = null;
  }, [pos]);

  // 双击复位
  const handleDoubleClick = useCallback(() => {
    const defaultPos = { right: DEFAULT_RIGHT, bottom: DEFAULT_BOTTOM };
    setPos(defaultPos);
    savePosition(defaultPos);
  }, []);

  const wasDragged = useCallback(() => {
    return dragRef.current?.moved ?? false;
  }, []);

  useEffect(() => {
    if (!isDragging) return;
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  return {
    pos, isDragging,
    ballRef,
    handleMouseDown,
    handleDoubleClick,
    wasDragged,
  };
}
