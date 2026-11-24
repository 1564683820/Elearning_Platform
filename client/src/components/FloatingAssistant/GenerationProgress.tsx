// 生成进度实时展示组件 — 显示技能调用、流式输出、生成成功状态
import { useState, useEffect, useRef } from 'react';

// 注入 CSS 关键帧动画（确保在任何页面都能生效）
const styleId = '__genProgressKeyframes';
if (typeof document !== 'undefined' && !document.getElementById(styleId)) {
  const style = document.createElement('style');
  style.id = styleId;
  style.textContent = `
    @keyframes genSpin {
      from { transform: rotate(0deg); }
      to   { transform: rotate(360deg); }
    }
    @keyframes genBarSlide {
      0%   { transform: translateX(-100%); }
      100% { transform: translateX(350%); }
    }
    @keyframes genCursorBlink {
      from, to { opacity: 1; }
      50%      { opacity: 0; }
    }
  `;
  document.head.appendChild(style);
}

export type GenStatus = 'idle' | 'skill_invoked' | 'generating' | 'success' | 'error';

interface GenerationProgressProps {
  /** 当前进度状态 */
  status: GenStatus;
  /** 技能名称 */
  skillName: string;
  /** 技能类型标签 */
  skillTypeLabel: string;
  /** 生成成功后的链接 URL */
  successUrl?: string;
  /** 生成成功后的链接文本 */
  successLabel?: string;
  /** 实时输出文本（不断追加） */
  streamText?: string;
}

// 模拟状态消息序列
const STATUS_MESSAGES: Record<GenStatus, string[]> = {
  idle: ['准备就绪'],
  skill_invoked: ['加载技能模板中...', '技能规则注入完成'],
  generating: [
    '正在解析生成参数...',
    '正在调用 AI 生成内容...',
    '正在生成内容结构...',
    '正在优化内容排版...',
  ],
  success: ['生成完成'],
  error: ['生成失败'],
};

export default function GenerationProgress({
  status,
  skillName,
  skillTypeLabel,
  successUrl,
  successLabel,
  streamText,
}: GenerationProgressProps) {
  const [visibleMsgIdx, setVisibleMsgIdx] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 根据状态阶段渐进显示状态消息
  useEffect(() => {
    const msgs = STATUS_MESSAGES[status];
    if (status === 'idle' || status === 'success') {
      setVisibleMsgIdx(msgs.length);
      return;
    }
    // 逐条显示
    setVisibleMsgIdx(1);
    timerRef.current = setInterval(() => {
      setVisibleMsgIdx(prev => {
        const next = prev + 1;
        if (next >= msgs.length) {
          if (timerRef.current) clearInterval(timerRef.current);
          return msgs.length;
        }
        return next;
      });
    }, 1200);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [status]);

  // 技能调用成功的展示
  if (status === 'skill_invoked') {
    return (
      <div style={boxStyle}>
        <div style={headerRowStyle}>
          <span style={iconGreenStyle}>✓</span>
          <span style={skillCallTextStyle}>
            调用「{skillName}」{skillTypeLabel}技能成功
          </span>
        </div>
        {/* 逐条状态消息 */}
        <div style={msgListStyle}>
          {STATUS_MESSAGES['skill_invoked'].slice(0, visibleMsgIdx).map((msg, i) => (
            <div key={i} style={statusMsgStyle}>
              <span style={dotStyle}>●</span>
              {msg}
            </div>
          ))}
        </div>
        {/* 进度条 */}
        <div style={barWrapStyle}>
          <div style={barInnerStyle} />
        </div>
      </div>
    );
  }

  // 生成中
  if (status === 'generating') {
    return (
      <div style={boxStyle}>
        <div style={headerRowStyle}>
          <span style={iconSpinStyle}>⟳</span>
          <span style={genTitleStyle}>正在{skillTypeLabel}生成中...</span>
        </div>
        {/* 逐条状态消息 */}
        <div style={msgListStyle}>
          {STATUS_MESSAGES['generating'].slice(0, visibleMsgIdx).map((msg, i) => (
            <div key={i} style={{
              ...statusMsgStyle,
              color: i < visibleMsgIdx - 1 ? '#2d7d46' : '#6b7280',
              fontWeight: i === visibleMsgIdx - 1 ? 500 : 400,
            }}>
              <span style={{
                ...dotStyle,
                color: i < visibleMsgIdx - 1 ? '#2d7d46' : '#9ca3af',
              }}>{i < visibleMsgIdx - 1 ? '✓' : '●'}</span>
              {msg}
            </div>
          ))}
        </div>
        {/* 实时输出小框 */}
        {streamText && (
          <div style={streamBoxStyle}>
            <div style={streamLabelStyle}>输出预览</div>
            <div style={streamContentStyle}>
              {streamText}
              <span style={cursorBlinkStyle}>|</span>
            </div>
          </div>
        )}
        {/* 进度条 */}
        <div style={barWrapStyle}>
          <div style={barAnimStyle} />
        </div>
      </div>
    );
  }

  // 生成成功
  if (status === 'success') {
    return (
      <div style={{ ...boxStyle, borderColor: '#86efac' }}>
        <div style={headerRowStyle}>
          <span style={iconGreenStyle}>✓</span>
          <span style={successTitleStyle}>
            {skillTypeLabel}生成成功！
          </span>
        </div>
        {successUrl && (
          <a
            href={successUrl}
            style={viewLinkStyle}
            onClick={(e) => {
              // 阻止冒泡，使链接正常工作
              e.stopPropagation();
            }}
          >
            📂 {successLabel || '点击查看'}
          </a>
        )}
        {/* 进度条（已满） */}
        <div style={barWrapStyle}>
          <div style={{ ...barInnerStyle, width: '100%', background: '#86efac' }} />
        </div>
      </div>
    );
  }

  // 生成失败（含验证失败）
  if (status === 'error') {
    return (
      <div style={{ ...boxStyle, borderColor: '#fca5a5', background: '#fef2f2' }}>
        <div style={headerRowStyle}>
          <span style={iconErrorStyle}>✕</span>
          <span style={{ color: '#b91c1c', fontWeight: 700, fontSize: 13 }}>
            {skillTypeLabel}生成失败
          </span>
        </div>
        {streamText && (
          <div style={{ ...streamBoxStyle, borderColor: '#fecaca', background: '#fff' }}>
            <div style={streamContentStyle}>{streamText}</div>
          </div>
        )}
        <div style={barWrapStyle}>
          <div style={{ ...barInnerStyle, background: '#fca5a5', width: '100%' }} />
        </div>
      </div>
    );
  }

  // idle / fallback
  return null;
}


// ===== 新增：按题型并行生成进度组件 =====

interface PerTypeState {
  label: string;
  count: number;
  status: 'pending' | 'generating' | 'success' | 'error';
  error?: string;
}

interface GenerationProgressStreamProps {
  /** 题型配置 [{qtype, label, count}, ...] */
  types: { qtype: string; label: string; count: number }[];
  /** 各题型当前状态映射 { qtype: PerTypeState } */
  typeResults: Record<string, PerTypeState>;
  /** 实时流式输出文本 */
  streamText?: string;
  /** 整体错误信息 */
  error?: string;
  /** 生成完成状态 */
  success?: boolean;
  /** 生成成功后的链接 URL */
  successUrl?: string;
  /** 成功链接文本 */
  successLabel?: string;
}

function PerTypeProgress({
  typeInfo,
  result,
}: {
  typeInfo: { qtype: string; label: string; count: number };
  result?: PerTypeState;
}) {
  const status = result?.status || 'pending';
  const isReading = typeInfo.qtype === 'reading';

  let iconSpan: React.ReactNode;
  if (status === 'success') {
    iconSpan = <span style={perTypeIconDoneStyle}>✓</span>;
  } else if (status === 'error') {
    iconSpan = <span style={perTypeIconErrStyle}>✕</span>;
  } else if (status === 'generating') {
    iconSpan = <span style={perTypeIconSpinStyle}>⟳</span>;
  } else {
    iconSpan = <span style={perTypeIconPendingStyle}>○</span>;
  }

  const barColor = status === 'success' ? '#22c55e'
    : status === 'error' ? '#ef4444'
    : status === 'generating' ? '#3b82f6'
    : '#e2e8f0';

  return (
    <div style={perTypeRowStyle}>
      <div style={perTypeHeaderStyle}>
        {iconSpan}
        <span style={perTypeLabelStyle}>{typeInfo.label}</span>
        <span style={perTypeCountStyle}>
          {typeInfo.count}{isReading ? '篇' : '道'}
        </span>
        {status === 'generating' && (
          <span style={perTypeStatusTextStyle}>生成中...</span>
        )}
        {status === 'success' && (
          <span style={perTypeStatusDoneStyle}>✓ 完成</span>
        )}
        {status === 'error' && (
          <span style={perTypeStatusErrStyle}>{result?.error || '失败'}</span>
        )}
      </div>
      <div style={perTypeBarWrapStyle}>
        <div style={{
          ...perTypeBarInnerStyle,
          width: status === 'success' ? '100%'
            : status === 'error' ? '60%'
            : status === 'generating' ? '40%'
            : '0%',
          background: barColor,
          animation: status === 'generating' ? 'genBarSlide 1.2s ease-in-out infinite' : 'none',
        }} />
      </div>
    </div>
  );
}

export function GenerationProgressStream({
  types,
  typeResults,
  streamText,
  error,
  success,
  successUrl,
  successLabel,
}: GenerationProgressStreamProps) {
  const total = types.length;
  const done = types.filter(t => typeResults[t.qtype]?.status === 'success').length;
  const failed = types.filter(t => typeResults[t.qtype]?.status === 'error').length;
  const percent = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div style={boxStyle}>
      <div style={headerRowStyle}>
        {error ? (
          <span style={iconErrorStyle}>✕</span>
        ) : success ? (
          <span style={iconGreenStyle}>✓</span>
        ) : (
          <span style={iconSpinStyle}>⟳</span>
        )}
        <span style={{
          color: error ? '#b91c1c' : success ? '#166534' : '#2d7d46',
          fontWeight: 700, fontSize: 13,
        }}>
          {error ? '试卷生成失败'
            : success ? '试卷生成成功！'
            : '正在按题型并行生成...'}
        </span>
      </div>

      <div style={barWrapStyle}>
        <div style={{
          ...barInnerStyle,
          width: error || success ? '100%' : `${Math.max(percent, 5)}%`,
          background: error ? '#fca5a5' : success ? '#86efac' : '#22c55e',
          transition: 'width 0.4s ease',
        }} />
      </div>

      <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2, marginBottom: 6 }}>
        {done}/{total} 题型完成{failed > 0 ? `，${failed} 个失败` : ''}
      </div>

      <div style={perTypeListStyle}>
        {types.map((t) => (
          <PerTypeProgress
            key={t.qtype}
            typeInfo={t}
            result={typeResults[t.qtype]}
          />
        ))}
      </div>

      {streamText && (
        <div style={streamBoxStyle}>
          <div style={streamLabelStyle}>AI 输出预览</div>
          <div style={{
            ...streamContentStyle,
            maxHeight: 60, overflowY: 'auto',
          }}>
            {streamText}
            {!success && !error && <span style={cursorBlinkStyle}>|</span>}
          </div>
        </div>
      )}

      {error && (
        <div style={{
          marginTop: 6, padding: '6px 8px', background: '#fef2f2',
          border: '1px solid #fecaca', borderRadius: 6,
          color: '#b91c1c', fontSize: 11,
        }}>
          {error}
        </div>
      )}

      {success && successUrl && (
        <a href={successUrl} style={viewLinkStyle}
          onClick={(e) => e.stopPropagation()}>
          📂 {successLabel || '点击查看试卷'}
        </a>
      )}
    </div>
  );
}

// ===== 按题型进度组件的样式 =====

const perTypeListStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  marginBottom: 6,
};

const perTypeRowStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #e5e7eb',
  borderRadius: 6,
  padding: '6px 8px',
};

const perTypeHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 5,
  marginBottom: 4,
};

const perTypeLabelStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: '#374151',
  minWidth: 48,
};

const perTypeCountStyle: React.CSSProperties = {
  fontSize: 10,
  color: '#9ca3af',
  marginRight: 'auto',
};

const perTypeStatusTextStyle: React.CSSProperties = {
  fontSize: 10,
  color: '#3b82f6',
  fontWeight: 500,
};

const perTypeStatusDoneStyle: React.CSSProperties = {
  fontSize: 10,
  color: '#16a34a',
  fontWeight: 500,
};

const perTypeStatusErrStyle: React.CSSProperties = {
  fontSize: 10,
  color: '#dc2626',
  fontWeight: 500,
};

const perTypeIconSpinStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 16,
  height: 16,
  fontSize: 12,
  color: '#3b82f6',
  animation: 'genSpin 1s linear infinite',
  flexShrink: 0,
};

const perTypeIconDoneStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 16,
  height: 16,
  borderRadius: '50%',
  background: '#22c55e',
  color: '#fff',
  fontSize: 10,
  fontWeight: 700,
  flexShrink: 0,
};

const perTypeIconErrStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 16,
  height: 16,
  borderRadius: '50%',
  background: '#ef4444',
  color: '#fff',
  fontSize: 10,
  fontWeight: 700,
  flexShrink: 0,
};

const perTypeIconPendingStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 16,
  height: 16,
  fontSize: 14,
  color: '#d1d5db',
  flexShrink: 0,
};

const perTypeBarWrapStyle: React.CSSProperties = {
  width: '100%',
  height: 3,
  borderRadius: 2,
  background: '#f3f4f6',
  overflow: 'hidden',
};

const perTypeBarInnerStyle: React.CSSProperties = {
  height: '100%',
  borderRadius: 2,
  transition: 'width 0.3s ease',
};


// ========== 样式 ==========

const boxStyle: React.CSSProperties = {
  background: '#f4faf4',
  border: '1px solid #bbf7d0',
  borderRadius: 10,
  padding: '10px 14px',
  marginBottom: 8,
  fontSize: 12,
  lineHeight: 1.5,
};

const headerRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  marginBottom: 6,
};

const iconGreenStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 18,
  height: 18,
  borderRadius: '50%',
  background: '#22c55e',
  color: '#fff',
  fontSize: 11,
  fontWeight: 700,
  flexShrink: 0,
};

const iconErrorStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 18,
  height: 18,
  borderRadius: '50%',
  background: '#ef4444',
  color: '#fff',
  fontSize: 11,
  fontWeight: 700,
  flexShrink: 0,
};

const iconSpinStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 18,
  height: 18,
  fontSize: 14,
  color: '#2d7d46',
  animation: 'genSpin 1s linear infinite',
  flexShrink: 0,
};

const skillCallTextStyle: React.CSSProperties = {
  color: '#166534',
  fontWeight: 600,
  fontSize: 12,
};

const genTitleStyle: React.CSSProperties = {
  color: '#2d7d46',
  fontWeight: 600,
  fontSize: 12,
};

const successTitleStyle: React.CSSProperties = {
  color: '#166534',
  fontWeight: 700,
  fontSize: 13,
};

const msgListStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 3,
  marginBottom: 8,
};

const statusMsgStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 5,
  fontSize: 11,
  color: '#6b7280',
};

const dotStyle: React.CSSProperties = {
  fontSize: 8,
  flexShrink: 0,
};

const barWrapStyle: React.CSSProperties = {
  width: '100%',
  height: 3,
  borderRadius: 2,
  background: '#e2e8f0',
  overflow: 'hidden',
  marginTop: 6,
};

const barInnerStyle: React.CSSProperties = {
  width: '100%',
  height: '100%',
  borderRadius: 2,
  background: '#22c55e',
};

const barAnimStyle: React.CSSProperties = {
  width: '40%',
  height: '100%',
  borderRadius: 2,
  background: '#22c55e',
  animation: 'genBarSlide 1.2s ease-in-out infinite',
};

const streamBoxStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #d4edda',
  borderRadius: 6,
  padding: '6px 8px',
  marginTop: 4,
  maxHeight: 80,
  overflowY: 'auto',
};

const streamLabelStyle: React.CSSProperties = {
  fontSize: 10,
  color: '#9ca3af',
  marginBottom: 2,
};

const streamContentStyle: React.CSSProperties = {
  fontSize: 11,
  color: '#374151',
  lineHeight: 1.5,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

const cursorBlinkStyle: React.CSSProperties = {
  color: '#22c55e',
  fontWeight: 700,
  animation: 'genCursorBlink 0.8s step-end infinite',
};

const viewLinkStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '6px 16px',
  borderRadius: 50,
  background: '#22c55e',
  color: '#fff',
  fontSize: 12,
  fontWeight: 600,
  textDecoration: 'none',
  marginTop: 4,
  cursor: 'pointer',
};
