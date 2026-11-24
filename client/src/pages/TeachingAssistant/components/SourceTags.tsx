// 教学助手 — 来源标签组件
// 将消息中引用的文档/试卷/知识库来源渲染为可点击的标签
import { useLocation, useNavigate } from 'react-router-dom';
import { SourceItem } from '../../../api/teachingAssistant';
import { ChatAttachmentButton } from '../../../shared/ChatAttachments';
import { examSourcePath } from '../../../shared/exams/ChatExamEvidence';

// 设计令牌 - 与主组件 TeachingAssistant 保持一致
const T = {
  green: {
    strong: '#2d7d46',
    primary: '#5B9E6F',
    bg3: '#e8f5e9',
  },
};

// 来源类型中文标签映射
function typeLabel(type: string): string {
  if (type === 'doc_试卷') return '试卷';
  if (type === 'exam_result') return '批改记录';
  if (type === 'vector_knowledge') return '知识库';
  return '文档';
}

// 标签组件共享样式
const tagBase: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  padding: '3px 10px', background: T.green.bg3, borderRadius: 20,
  fontSize: 11, color: T.green.strong, cursor: 'pointer',
  maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis',
  whiteSpace: 'nowrap', transition: 'background 0.15s',
};

const dot: React.CSSProperties = {
  width: 6, height: 6, borderRadius: '50%',
  background: T.green.primary, flexShrink: 0,
};

const wrap: React.CSSProperties = {
  display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8,
};

// ---------- 单个来源标签 ----------
interface SourceTagProps {
  src: SourceItem;
  showDot?: boolean;
  showSnippet?: boolean;
}

function SourceTag({ src, showDot = true, showSnippet = true }: SourceTagProps) {
  const navigate = useNavigate();
  const location = useLocation();

  if (src.type === 'chat_attachment') return <ChatAttachmentButton id={src.id} name={src.title} />;

  const label = typeLabel(src.type);
  const title = `${src.title}${showSnippet && src.snippet ? `\n${src.snippet}` : ''}`;

  const handleClick = () => {
    if (src.type === 'exam_result') {
      navigate(examSourcePath(src, 'web'), { state: { from: location.pathname + location.search } });
      return;
    }
    navigate(`/documents/view/${src.id}?highlight=${encodeURIComponent(src.snippet || '')}&chunk=${encodeURIComponent(src.chunk_id || '')}`);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      title={title}
      style={{ ...tagBase, border: 0 }}
      onMouseEnter={e => { e.currentTarget.style.background = '#c6e6c6'; }}
      onMouseLeave={e => { e.currentTarget.style.background = T.green.bg3; }}
    >
      {showDot && <span style={dot} />}
      {label}: {src.title}
    </button>
  );
}

// ---------- 消息中展示的来源标签列表（带圆点指示器） ----------
interface MessageSourcesProps {
  sources: SourceItem[] | null;
}

export function MessageSources({ sources }: MessageSourcesProps) {
  if (!sources || sources.length === 0) return null;
  return (
    <div style={wrap}>
      {sources.map((src, i) => (
        <SourceTag key={i} src={src} showDot showSnippet />
      ))}
    </div>
  );
}

// ---------- 流式响应中的来源标签列表（无圆点、无 snippet） ----------
interface StreamingSourcesProps {
  sources: SourceItem[];
}

export function StreamingSources({ sources }: StreamingSourcesProps) {
  if (!sources || sources.length === 0) return null;
  return (
    <div style={wrap}>
      {sources.map((src, i) => (
        <SourceTag key={i} src={src} showDot={false} showSnippet={false} />
      ))}
    </div>
  );
}
