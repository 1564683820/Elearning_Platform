// 后台上传迷你条 — 默认右上角，可拖拽，点击展开进度弹窗
import { useCallback, useEffect, useRef, useState } from 'react';

interface UploadBadgeProps {
  fileCount: number;
  onClick: () => void;
}

const STORAGE_KEY = 'upload_badge_pos';
const DEFAULT_TOP = 16;
const DEFAULT_RIGHT = 20;
const EDGE_MARGIN = 4;

interface BadgePos {
  top: number;
  right: number;
}

function loadPos(): BadgePos {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { top: DEFAULT_TOP, right: DEFAULT_RIGHT };
}

function savePos(pos: BadgePos) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(pos));
}

export default function UploadBadge({ fileCount, onClick }: UploadBadgeProps) {
  const [pos, setPos] = useState<BadgePos>(loadPos);
  const [isDragging, setIsDragging] = useState(false);
  const [dotIndex, setDotIndex] = useState(0);
  const dragRef = useRef<{
    startX: number; startY: number;
    originTop: number; originRight: number;
    moved: boolean;
  } | null>(null);

  // 动态点动画
  useEffect(() => {
    const timer = setInterval(() => setDotIndex(i => (i + 1) % 4), 600);
    return () => clearInterval(timer);
  }, []);

  const dots = '.'.repeat(dotIndex) + ' '.repeat(3 - dotIndex);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      originTop: pos.top,
      originRight: pos.right,
      moved: false,
    };
    setIsDragging(true);
  }, [pos]);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!dragRef.current) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    if (!dragRef.current.moved && Math.abs(dx) + Math.abs(dy) > 5) {
      dragRef.current.moved = true;
    }
    // 从 right/top 计算：正 dx 往右拖 → right 减小
    const newRight = Math.max(EDGE_MARGIN, Math.min(window.innerWidth - 120, dragRef.current.originRight - dx));
    const newTop = Math.max(EDGE_MARGIN, Math.min(window.innerHeight - 50, dragRef.current.originTop + dy));
    setPos({ right: newRight, top: newTop });
  }, []);

  const handleMouseUp = useCallback(() => {
    if (!dragRef.current) return;
    savePos(pos);
    setIsDragging(false);
    dragRef.current = null;
  }, [pos]);

  useEffect(() => {
    if (!isDragging) return;
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  const handleClick = () => {
    if (dragRef.current?.moved) return;
    onClick();
  };

  return (
    <div
      onClick={handleClick}
      onMouseDown={handleMouseDown}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') onClick(); }}
      style={{
        position: 'fixed',
        right: pos.right,
        top: pos.top,
        zIndex: 9999,
        background: '#1a3a22',
        color: '#88c8a0',
        padding: '6px 14px',
        borderRadius: 14,
        fontSize: 12,
        fontWeight: 500,
        cursor: isDragging ? 'grabbing' : 'grab',
        boxShadow: '0 3px 12px rgba(0,0,0,0.3)',
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        border: '1px solid rgba(136,200,160,0.25)',
        userSelect: 'none',
        transition: isDragging ? 'none' : 'box-shadow 0.15s',
        animation: 'badgeSlideUp 300ms cubic-bezier(0.34, 1.56, 0.64, 1)',
        opacity: isDragging ? 0.7 : 1,
      }}
      onMouseEnter={e => {
        if (!isDragging) {
          e.currentTarget.style.boxShadow = '0 5px 18px rgba(0,0,0,0.4)';
        }
      }}
      onMouseLeave={e => {
        if (!isDragging) {
          e.currentTarget.style.boxShadow = '0 3px 12px rgba(0,0,0,0.3)';
        }
      }}
    >
      {/* 旋转图标 — 缩小版 */}
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#88c8a0" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ animation: 'badgeSpin 1.5s linear infinite', flexShrink: 0 }}>
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
      </svg>
      <span>
        <span style={{ fontWeight: 600, color: '#fff' }}>{fileCount}</span> 个上传中<span style={{ fontFamily: 'monospace', minWidth: 14, display: 'inline-block' }}>{dots}</span>
      </span>
    </div>
  );
}
