// 消息气泡组件 — 用户/AI 消息，支持 Markdown 渲染
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { IconBulb } from '../../design-system';
import type { SourceItem } from '../../api/teachingAssistant';
import { ChatExamEvidence, singleExamEvidence } from '../../shared/exams/ChatExamEvidence';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
  sources?: SourceItem[] | null;
}

export default function MessageBubble({ role, content, isStreaming, sources }: MessageBubbleProps) {
  const isUser = role === 'user';
  const evidence = isUser ? undefined : singleExamEvidence(sources);
  if (!content && !isStreaming && !evidence) return null;

  return (
    <div style={{
      display: 'flex',
      flexDirection: isUser ? 'row-reverse' : 'row',
      alignItems: 'flex-start',
      gap: 8,
      marginBottom: 12,
      maxWidth: '100%',
    }}>
      {/* 头像 */}
      <div style={{
        width: 28,
        height: 28,
        borderRadius: '50%',
        background: isUser ? '#5B9E6F' : '#e6f7e6',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        fontSize: 12,
        fontWeight: 600,
        color: isUser ? '#fff' : '#2d7d46',
      }}>
        {isUser ? '我' : <IconBulb size={16} color="#2d7d46" />}
      </div>

      {/* 气泡 */}
      <div style={{
        maxWidth: 'calc(100% - 40px)',
        padding: '10px 14px',
        borderRadius: isUser ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
        background: isUser ? '#2d7d46' : '#f0f4f0',
        color: isUser ? '#fff' : '#1a2e1a',
        fontSize: 14,
        lineHeight: 1.55,
        wordBreak: 'break-word',
        whiteSpace: 'pre-wrap',
      }}>
        {evidence && <ChatExamEvidence evidence={evidence} />}
        {isUser ? (
          <span>{content}</span>
        ) : (
          <div className="floating-assistant-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
            {isStreaming && (
              <span className="streaming-cursor" style={{
                display: 'inline-block',
                width: 2,
                height: 14,
                background: '#2d7d46',
                marginLeft: 2,
                animation: 'blink 0.8s step-end infinite',
                verticalAlign: 'middle',
              }} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
