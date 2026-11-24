// 文档查看页面 — 支持从教学助手来源链接跳转，高亮定位到相关段落
import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { teacherApi } from '../../api/teacher';

export default function DocumentView() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const highlight = searchParams.get('highlight') || '';
  const chunkId = searchParams.get('chunk') || '';

  const [docTitle, setDocTitle] = useState('');
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLSpanElement>(null);

  // 加载文档文本内容
  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    const loadDoc = async () => {
      setLoading(true);
      setError(null);
      try {
        if (!/^[1-9][0-9]*$/.test(id)) throw new Error('无效的文档ID');

        const result = await teacherApi.documents.getTextContent(id);
        if (cancelled) return;

        if (result && result.text) {
          setText(result.text);
          setDocTitle(result.filename || `文档 #${id}`);
        } else {
          setError('无法加载文档内容，文档可能尚未解析。');
        }
      } catch (err: any) {
        if (!cancelled) setError(err?.message || '加载文档失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadDoc();
    return () => { cancelled = true; };
  }, [id]);

  // 滚动到高亮位置
  useEffect(() => {
    if (!loading && text && highlightRef.current) {
      setTimeout(() => {
        highlightRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 200);
    }
  }, [loading, text]);

  // 高亮渲染：在文本中查找 highlight 片段并标记
  const renderContent = useCallback(() => {
    if (!text) return null;

    // 如果有关键词高亮，在文本中查找并标记
    if (highlight && text.includes(highlight)) {
      const idx = text.indexOf(highlight);
      const before = text.slice(Math.max(0, idx - 120), idx);
      const match = text.slice(idx, idx + highlight.length);
      const after = text.slice(idx + highlight.length, idx + highlight.length + 500);

      return (
        <div style={contentTextStyle}>
          {idx > 120 && <span style={{ color: '#9ca3af', fontSize: 12 }}>... </span>}
          {before}
          <span ref={highlightRef} style={highlightStyle}>{match}</span>
          {after}
          {idx + highlight.length + 500 < text.length && (
            <span style={{ color: '#9ca3af', fontSize: 12 }}> ...</span>
          )}
        </div>
      );
    }

    // 没有高亮：显示全文
    return <div style={contentTextStyle}>{text}</div>;
  }, [text, highlight]);

  return (
    <div style={containerStyle}>
      {/* 顶部导航栏 */}
      <div style={headerStyle}>
        <button onClick={() => navigate(-1)} style={backBtnStyle} title="返回">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
        </button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1 style={{ fontSize: 16, fontWeight: 600, color: '#1a2e1a', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            📄 {docTitle}
          </h1>
          {chunkId && (
            <span style={{ fontSize: 11, color: '#6b7280' }}>
              定位片段: {chunkId.slice(0, 40)}{chunkId.length > 40 ? '...' : ''}
            </span>
          )}
        </div>
        {(highlight || chunkId) && (
          <span style={badgeStyle}>🔍 已定位相关段落</span>
        )}
      </div>

      {/* 内容区域 */}
      <div ref={contentRef} style={bodyStyle}>
        {loading && (
          <div style={centerStyle}>
            <div style={spinnerStyle} />
            <p style={{ color: '#6b7280', fontSize: 13, marginTop: 12 }}>加载文档内容中...</p>
          </div>
        )}

        {error && (
          <div style={centerStyle}>
            <p style={{ color: '#dc2626', fontSize: 14 }}>{error}</p>
            <button onClick={() => navigate('/documents')} style={gotoDocsBtnStyle}>
              前往文档列表
            </button>
          </div>
        )}

        {!loading && !error && renderContent()}
      </div>
    </div>
  );
}

// ─── 样式 ──────────────────────────────
const containerStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', height: '100vh',
  background: '#fafafa',
};

const headerStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 12,
  padding: '12px 20px', background: '#fff',
  borderBottom: '1px solid #e5e7eb', flexShrink: 0,
};

const backBtnStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  width: 34, height: 34, borderRadius: 8,
  border: '1px solid #e5e7eb', background: '#fff',
  color: '#374151', cursor: 'pointer', flexShrink: 0,
};

const badgeStyle: React.CSSProperties = {
  padding: '3px 10px', borderRadius: 20, background: '#e6f7e6',
  color: '#2d7d46', fontSize: 11, fontWeight: 500,
  whiteSpace: 'nowrap', flexShrink: 0,
};

const bodyStyle: React.CSSProperties = {
  flex: 1, overflowY: 'auto', padding: '24px 32px',
};

const contentTextStyle: React.CSSProperties = {
  maxWidth: 800, margin: '0 auto',
  background: '#fff', borderRadius: 12,
  padding: '28px 36px',
  border: '1px solid #e5e7eb',
  boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  fontSize: 14, lineHeight: 2,
  color: '#374151', whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

const highlightStyle: React.CSSProperties = {
  background: '#fef3c7',
  color: '#92400e',
  fontWeight: 600,
  padding: '1px 3px',
  borderRadius: 3,
  boxShadow: '0 0 0 2px #fef3c7',
};

const centerStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column',
  alignItems: 'center', justifyContent: 'center',
  height: '100%',
};

const spinnerStyle: React.CSSProperties = {
  width: 32, height: 32,
  border: '3px solid #e5e7eb',
  borderTopColor: '#2d7d46',
  borderRadius: '50%',
  animation: 'spin 0.8s linear infinite',
};

const gotoDocsBtnStyle: React.CSSProperties = {
  marginTop: 16, padding: '8px 20px',
  borderRadius: 20, border: '1px solid #d4edda',
  background: '#e6f7e6', color: '#2d7d46',
  fontSize: 13, cursor: 'pointer',
};
