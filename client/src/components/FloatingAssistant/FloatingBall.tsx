// 悬浮小球组件 — 可拖拽，支持文件拖入态切换
import { useDrag } from './useDrag';
import { IconBulb } from '../../design-system';

interface FloatingBallProps {
  onClick: () => void;
  dropState: 'idle' | 'drop_zone';
}

export default function FloatingBall({ onClick, dropState }: FloatingBallProps) {
  const { pos, isDragging, ballRef, handleMouseDown, handleDoubleClick, wasDragged } = useDrag();

  const handleClick = () => {
    // 如果刚刚拖拽过，不触发点击
    if (wasDragged()) return;
    onClick();
  };

  const isDropZone = dropState === 'drop_zone';

  return (
    <div
      ref={ballRef}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      onMouseDown={handleMouseDown}
      role="button"
      tabIndex={0}
      aria-label="教学助手小e"
      onKeyDown={(e) => { if (e.key === 'Enter') onClick(); }}
      style={{
        // 位置
        position: 'fixed',
        right: pos.right,
        bottom: pos.bottom,
        zIndex: 9998,
        cursor: isDragging ? 'grabbing' : isDropZone ? 'copy' : 'grab',
        userSelect: 'none',

        // 形状
        width: isDropZone ? 180 : 48,
        height: isDropZone ? 56 : 48,
        borderRadius: isDropZone ? 16 : '50%',

        // 视觉
        background: '#2d7d46',
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: isDropZone ? 8 : 0,
        boxShadow: isDropZone
          ? '0 0 20px rgba(45,125,70,0.5), 0 8px 32px rgba(0,0,0,0.25)'
          : '0 4px 16px rgba(0,0,0,0.2)',
        border: isDropZone ? '2px dashed #88c8a0' : 'none',
        opacity: isDragging ? 0.75 : 0.9,
        transition: isDragging
          ? 'none'
          : 'width 200ms ease-out, height 200ms ease-out, border-radius 200ms ease-out, box-shadow 200ms ease-out, opacity 150ms',

        // 呼吸灯
        animation: isDropZone ? 'none' : 'breathe 2s ease-in-out infinite',

        // 文字
        fontSize: 14,
        fontWeight: 500,
        whiteSpace: 'nowrap',
        overflow: 'hidden',
      }}
      onMouseEnter={(e) => {
        if (!isDragging && !isDropZone) {
          e.currentTarget.style.transform = 'scale(1.08)';
          e.currentTarget.style.opacity = '1';
        }
      }}
      onMouseLeave={(e) => {
        if (!isDragging) {
          e.currentTarget.style.transform = 'scale(1)';
          e.currentTarget.style.opacity = isDropZone ? '0.9' : '0.9';
        }
      }}
    >
      {isDropZone ? (
        <>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#88c8a0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <span>松开放文件到小e</span>
        </>
      ) : (
        <IconBulb size={24} color="#fff" />
      )}
    </div>
  );
}
