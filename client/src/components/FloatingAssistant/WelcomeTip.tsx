// 小e首次进入提示气泡 — 引导用户拖文件或语音召唤
import { useEffect, useState } from 'react';
import { IconX } from '../../design-system';

interface WelcomeTipProps {
  ballRect: { right: number; bottom: number } | null;
  onDismiss: () => void;
}

export default function WelcomeTip({ ballRect, onDismiss }: WelcomeTipProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // 等待动画帧确保 DOM 布局就绪
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // 默认定位：球在右下角，引导气泡朝左展开
  const defaultRight = 80;  // 48(球宽) + 8(间隔) + 24(球右边距)
  const defaultBottom = 28;

  // 如果球已经被拖拽过，仍然用默认值 — 因为无法实时跟踪拖拽后的位置
  const right = ballRect?.right != null ? ballRect.right + 56 : defaultRight;
  const bottom = ballRect?.bottom != null ? ballRect.bottom + 4 : defaultBottom;

  return (
    <div
      style={{
        position: 'fixed',
        right,
        bottom,
        zIndex: 9997,
        maxWidth: 310,
        background: '#fff',
        borderRadius: 14,
        boxShadow: '0 6px 24px rgba(0,0,0,0.12), 0 0 0 1px rgba(0,0,0,0.04)',
        padding: '14px 38px 14px 16px',
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0) scale(1)' : 'translateY(10px) scale(0.92)',
        transition: 'opacity 300ms ease-out, transform 300ms cubic-bezier(0.34, 1.56, 0.64, 1)',
        pointerEvents: visible ? 'auto' : 'none',
      }}
    >
      {/* 指向右侧（悬浮球方向）的小三角 */}
      <div
        style={{
          position: 'absolute',
          right: -6,
          top: '50%',
          marginTop: -6,
          width: 0,
          height: 0,
          borderTop: '7px solid transparent',
          borderBottom: '7px solid transparent',
          borderLeft: '8px solid #fff',
          filter: 'drop-shadow(1px 0 2px rgba(0,0,0,0.06))',
        }}
      />

      {/* 文案 */}
      <span style={{ fontSize: 13, lineHeight: 1.6, color: '#374151' }}>
        可以<strong>拖动文件</strong>到这里上传，或者叫我帮忙生成试卷/PPT哦~
      </span>

      {/* 关闭按钮 */}
      <button
        onClick={onDismiss}
        aria-label="关闭提示"
        style={{
          position: 'absolute',
          top: 8,
          right: 10,
          width: 22,
          height: 22,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: 'none',
          background: 'transparent',
          borderRadius: 6,
          cursor: 'pointer',
          color: '#9ca3af',
          transition: 'background 150ms, color 150ms',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = '#f3f4f6';
          e.currentTarget.style.color = '#6b7280';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'transparent';
          e.currentTarget.style.color = '#9ca3af';
        }}
      >
        <IconX size={12} />
      </button>
    </div>
  );
}
