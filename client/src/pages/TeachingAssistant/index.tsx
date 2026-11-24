// 教学助手 — AI 驱动的教师教学辅助对话页面
import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { readEventStream } from '../../api/eventStream';
import { recoverChatReply } from '../../shared/chatRequests';
import { useChatHistory } from '../../shared/chatHistory';
import {
  CHAT_FILE_ACCEPT,
  CHAT_IMAGE_ACCEPT,
  teachingAssistantApi,
  SessionItem,
  MessageData,
  SourceItem,
  type ChatResponse,
} from '../../api/teachingAssistant';
import SkillManager from './SkillManager';
import { MessageSources } from './components/SourceTags';
import { ChatExamEvidence, singleExamEvidence } from '../../shared/exams/ChatExamEvidence';
import { ExamKnowledgeEmpty, useExamKnowledgeAvailability } from '../../shared/exams/ExamKnowledgeEmpty';
import { ChatAttachmentButton, useChatComposer } from '../../shared/ChatAttachments';

/* ========== Design Tokens ========== */
// 现代、洁净的设计语言
// 教师端绿色主题 — 与平台设计系统统一
const T = {
  accent: '#5B9E6F',
  accentGradient: 'linear-gradient(135deg, #2d7d46, #5B9E6F)',
  accentBg: '#e6f7e6',
  green: {
    strong: '#2d7d46',
    mid: '#3d7a4e',
    primary: '#5B9E6F',
    soft: '#88c8a0',
    bg: '#e6f7e6',
    bg2: '#d4edda',
    bg3: '#e8f5e9',
  },
  aiBg: '#e6f7e6',
  aiBorder: '1px solid #d4edda',
  textPri: '#0f172a',
  textSec: '#475569',
  textTer: '#94a3b8',
  border: '#e2e8f0',
  borderLight: '#f1f5f9',
  surface: '#ffffff',
  surfaceSoft: '#f5f7fa',
  surfaceHeader: '#f8fafc',
  shadowSm: '0 1px 3px rgba(0,0,0,0.04)',
  shadowMd: '0 4px 16px rgba(0,0,0,0.06)',
  rSm: 6,
  rMd: 10,
  rLg: 14,
};

const containerStyle: React.CSSProperties = { display: 'flex', height: '100%', background: '#f0f2f5', position: 'relative', overflow: 'hidden', borderRadius: T.rMd, boxShadow: T.shadowSm };
const mainAreaStyle: React.CSSProperties = { flex: 1, display: 'flex', flexDirection: 'column', height: '100%', minWidth: 0, position: 'relative' };
const msgAreaStyle: React.CSSProperties = { flex: 1, overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', background: '#f0f2f5' };
const inputAreaStyle: React.CSSProperties = { display: 'flex', alignItems: 'flex-end', gap: 8, padding: '12px 16px 16px', background: T.surface, borderTop: `1px solid ${T.borderLight}`, flexShrink: 0 };
const inputStyle: React.CSSProperties = { flex: 1, border: `1px solid ${T.border}`, borderRadius: T.rSm, outline: 'none', resize: 'none', minHeight: 44, maxHeight: 96, lineHeight: 1.5, fontFamily: 'inherit', fontSize: 14, color: T.textPri, background: '#f8f9fa', padding: '10px 14px', boxSizing: 'border-box', transition: 'border-color 0.15s' };
const sidebarStyle: React.CSSProperties = { width: 320, background: T.surface, borderLeft: `1px solid ${T.borderLight}`, display: 'flex', flexDirection: 'column', flexShrink: 0 };
const sidebarHeaderStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 16px', borderBottom: `1px solid ${T.borderLight}` };

function formatTime(s: string): string {
  const d = new Date(s), now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  if (d.toDateString() === now.toDateString()) return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return `${d.getMonth()+1}/${d.getDate()}`;
}

export default function TeachingAssistant() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  // 不指定班级时自动搜索所有班级，因此不需要班级选择器
  const classId = null as number | null;

  // 构建路径
  const buildPath = useCallback((path: string) => path, []);

  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(sessionId || null);
  const examKnowledgeAvailable = useExamKnowledgeAvailability(!currentSessionId);
  const [messages, setMessages] = useState<MessageData[]>([]);
  const history = useChatHistory(currentSessionId, setMessages);
  const pending = useChatComposer('web', currentSessionId);
  const inputValue = pending.text;
  const [attachmentError, setAttachmentError] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [showSidebar, setShowSidebar] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [intentLabel, setIntentLabel] = useState('');
  const [isBatchMode, setIsBatchMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchDeleteLoading, setBatchDeleteLoading] = useState(false);
  const [showSkillManager, setShowSkillManager] = useState(false);

  const msgEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const newestMessageId = messages[messages.length - 1]?.id;

  const scrollBottom = useCallback(() => {
    setTimeout(() => msgEndRef.current?.scrollIntoView({ behavior:'smooth' }), 50);
  }, []);

  const loadSessions = useCallback(async () => {
    try { setSessions((await teachingAssistantApi.listSessions(1, 50)).items); } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);
  useEffect(() => { scrollBottom(); }, [streamingContent, newestMessageId, scrollBottom]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const handleNewSession = useCallback(async () => {
    if (isStreaming) return;
    try {
      const s = await teachingAssistantApi.createSession(classId);
      setSessions(p => [s, ...p]);
      setAttachmentError('');
      setCurrentSessionId(s.id); setMessages([]); setSuggestedQuestions([]); setSources([]); setStreamingContent('');
      navigate(buildPath(`/teaching-assistant/${s.id}`), { replace: true });
    } catch (err: any) { alert(err.message || '创建会话失败'); }
  }, [navigate, classId, buildPath, isStreaming]);

  const handleSelectSession = useCallback((id: string) => {
    if (currentSessionId === id) return;
    if (isStreaming) {
      abortRef.current?.abort();
      abortRef.current = null;
      setIsStreaming(false);
    }
    setMessages([]);
    setAttachmentError('');
    setCurrentSessionId(id); setSuggestedQuestions([]); setSources([]); setStreamingContent('');
    navigate(buildPath(`/teaching-assistant/${id}`), { replace: true });
  }, [isStreaming, navigate, buildPath, currentSessionId]);

  const handleDeleteSession = useCallback(async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await teachingAssistantApi.deleteSession(id);
      pending.clear(id);
      setSessions(p => p.filter(s => s.id !== id));
      if (currentSessionId === id) { setCurrentSessionId(null); setMessages([]); navigate(buildPath('/teaching-assistant'), { replace: true }); }
    } catch (err: any) { alert(err.message || '删除失败'); }
  }, [currentSessionId, navigate, buildPath, pending]);

  // ── 批量选择 ──
  const handleToggleSelect = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelectedIds(prev => {
      if (prev.size === sessions.length) return new Set();  // 全选状态下再次点击取消全选
      return new Set(sessions.map(s => s.id));
    });
  }, [sessions]);

  const handleBatchDelete = useCallback(async () => {
    if (selectedIds.size === 0) return;
    if (!window.confirm(`确定要批量清除 ${selectedIds.size} 个会话吗？\n\n此操作将同时删除关联消息和向量数据库记录，不可撤销。`)) return;
    setBatchDeleteLoading(true);
    try {
      const r = await teachingAssistantApi.batchDeleteSessions(Array.from(selectedIds));
      selectedIds.forEach(id => pending.clear(id));
      setSessions(p => p.filter(s => !selectedIds.has(s.id)));
      if (currentSessionId && selectedIds.has(currentSessionId)) {
        setCurrentSessionId(null); setMessages([]);
        navigate(buildPath('/teaching-assistant'), { replace: true });
      }
      setSelectedIds(new Set());
      setIsBatchMode(false);
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
    } catch (err: any) {
      alert('批量删除失败，请重试');
    } finally {
      setBatchDeleteLoading(false);
    }
  }, [selectedIds, currentSessionId, navigate, buildPath, pending]);

  // ---------- 流式发送 ----------
  const handleStreamSend = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isStreaming || history.initial || abortRef.current) return;
    setAttachmentError(''); setSuggestedQuestions([]); setSources([]); setStreamingContent(''); setIsStreaming(true); setIntentLabel('小e正在思考...');

    let convId = currentSessionId;

    const localId = crypto.randomUUID();
    const request = new AbortController();
    abortRef.current = request;
    let requestId: string | undefined;
    function accept(reply: Pick<ChatResponse, 'conversation_id' | 'message_id' | 'user_message_id' | 'content' | 'sources' | 'suggested_questions'>) {
      if (request.signal.aborted) return;
      setSuggestedQuestions(reply.suggested_questions);
      setSources(reply.sources);
      setCurrentSessionId(reply.conversation_id);
      setMessages(previous => [
        ...previous.filter(message => message.id !== reply.message_id && message.id !== reply.user_message_id)
          .map(message => message.id === localId && reply.user_message_id ? { ...message, id: reply.user_message_id } : message),
        { id: reply.message_id, conversation_id: reply.conversation_id, role: 'assistant', content: reply.content,
          message_type: 'text', sources: reply.sources, created_at: new Date().toISOString() },
      ]);
      pending.clear(reply.conversation_id);
      void loadSessions();
    }
    try {
      if (pending.files.length) setIntentLabel('正在上传并解析附件…');
      const attached = await pending.upload(convId, request.signal);
      if (!convId) {
        const session = await teachingAssistantApi.createSession(classId);
        request.signal.throwIfAborted();
        pending.begin(session.id, text);
        setSessions(previous => [session, ...previous]);
        setCurrentSessionId(session.id);
        convId = session.id;
        navigate(buildPath(`/teaching-assistant/${session.id}`), { replace: true });
      }
      setMessages(p => [...p, { id: localId, conversation_id: convId!, role:'user', content: text, message_type:'text', attachments: attached, sources: null, created_at: new Date().toISOString() }]);
      const parameters = {
        conversation_id: convId, message: text, class_id: classId, attachment_ids: attached.map(item => item.attachment_id),
      };
      requestId = pending.requestId(convId, parameters);
      const resp = await teachingAssistantApi.chatStream({ ...parameters, request_id: requestId }, request.signal);
      let collectedSources: SourceItem[] = [], accumulatedContent = '';
      let finished = false;

      for await (const frame of readEventStream(resp)) {
        if (frame.data === '[DONE]') continue;
        if (frame.name === 'error') throw new Error(JSON.parse(frame.data).message || '问答失败');
        try {
          const p = JSON.parse(frame.data);
          const ev = frame.name || p.event || p.type;
          if (ev === 'intent') {
            const m: Record<string,string> = { knowledge_lookup:'知识查询', document_query:'文档查询', class_stats:'班级统计', student_analysis:'学生分析', error_summary:'错题总结', teaching_advice:'教学建议', lesson_prep:'备课助手', general_chat:'自由对话' };
            setIntentLabel(m[p.intent] || p.intent);
          } else if (ev === 'status') setIntentLabel(p.message || '处理中...');
          else if (ev === 'searching') setIntentLabel('正在检索...');
          else if (ev === 'chunk') {
            const text = p.text || p.content || '';
            accumulatedContent += text;
            setStreamingContent(prev => prev + text);
          } else if (ev === 'sources') { collectedSources = Array.isArray(p) ? p : p.sources || p.data || []; setSources(collectedSources); }
          else if (ev === 'done') {
            finished = true;
            accept({
              conversation_id: p.conversation_id || p.conversationId || convId,
              message_id: String(p.message_id || crypto.randomUUID()), user_message_id: p.user_message_id,
              content: accumulatedContent, sources: collectedSources, suggested_questions: p.suggested_questions || p.suggestedQuestions || [],
            });
            break;
          }
        } catch { /* ignore non-json */ }
      }
      if (!finished) throw new Error('连接已中断，请重试');
    } catch (error) {
      if (request.signal.aborted) return;
      const recovered = convId && requestId ? await recoverChatReply(convId, requestId, request.signal) : undefined;
      if (request.signal.aborted) return;
      if (recovered) {
        accept(recovered);
        return;
      }
      setMessages(previous => previous.filter(message => message.id !== localId));
      setAttachmentError(error instanceof Error ? error.message : '请求失败，请重试');
    } finally {
      if (abortRef.current === request) {
        setIsStreaming(false); setIntentLabel(''); setStreamingContent(''); abortRef.current = null;
      }
    }
  }, [inputValue, isStreaming, history.initial, currentSessionId, navigate, loadSessions, classId, buildPath, pending]);

  const handleSuggestClick = (q: string) => { pending.setText(q); inputRef.current?.focus(); };

  function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
    setAttachmentError(pending.add(Array.from(event.currentTarget.files ?? [])));
    event.currentTarget.value = '';
  }

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!isStreaming) handleStreamSend(); }
  }, [handleStreamSend, isStreaming]);

  // ---------- 渲染单个消息（用户绿色气泡、AI白色卡片气泡） ----------
  const renderMessage = (msg: MessageData, idx: number) => {
    const isUser = msg.role === 'user';
    const evidence = isUser ? undefined : singleExamEvidence(msg.sources);
    const isLast = !isUser && idx === messages.length - 1;
    return (
      <div key={msg.id} style={{ marginBottom: 16, display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
        <div style={{ maxWidth: '80%', minWidth: 0 }}>
          <div style={{
            padding: isUser ? '10px 16px' : '14px 18px',
            borderRadius: isUser ? '12px 12px 4px 12px' : '4px 12px 12px 12px',
            background: isUser ? T.green.bg2 : '#ffffff',
            color: T.textPri,
            borderLeft: isUser ? 'none' : '3px solid #5B9E6F',
            boxShadow: isUser ? 'none' : '0 1px 4px rgba(0,0,0,0.06)',
            lineHeight: 1.7,
            fontSize: 14,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}>
            {evidence && <ChatExamEvidence evidence={evidence} />}
            {isUser ? msg.content : (
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                code({ className, children, ...props }) {
                  if (!className) return <code style={{ background: T.green.bg2, padding: '2px 6px', borderRadius: 4, fontSize: '0.88em', color: T.green.strong }} {...props}>{children}</code>;
                  return <pre style={{ background: '#1e293b', color: '#e2e8f0', padding: 14, borderRadius: 8, overflow: 'auto', fontSize: 13, lineHeight: 1.5, margin: '8px 0' }}><code className={className} {...props}>{children}</code></pre>;
                },
                a({ href, children }) { return <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: T.accent, textDecoration: 'underline' }}>{children}</a>; },
                p({ children }) { return <p style={{ margin: 0 }}>{children}</p>; },
                ul({ children }) { return <ul style={{ margin: '2px 0', paddingLeft: 20 }}>{children}</ul>; },
                ol({ children }) { return <ol style={{ margin: '2px 0', paddingLeft: 20 }}>{children}</ol>; },
                li({ children }) { return <li style={{ margin: '1px 0' }}>{children}</li>; },
                h1({ children }) { return <div style={{ margin: '4px 0' }}>{children}</div>; },
                h2({ children }) { return <div style={{ margin: '4px 0' }}>{children}</div>; },
                h3({ children }) { return <div style={{ margin: '4px 0' }}>{children}</div>; },
                table({ children }) { return <div style={{ overflow: 'auto', margin: '8px 0' }}><table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>{children}</table></div>; },
                th({ children }) { return <th style={{ border: '1px solid #e2e8f0', padding: '6px 10px', background: '#f8fafc', fontWeight: 600, textAlign: 'left' }}>{children}</th>; },
                td({ children }) { return <td style={{ border: '1px solid #e2e8f0', padding: '6px 10px' }}>{children}</td>; },
              }}>{msg.content}</ReactMarkdown>
            )}
          </div>
          {isUser && msg.attachments && <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 4 }}>
            {msg.attachments.map(file => <ChatAttachmentButton key={file.attachment_id} id={file.attachment_id} name={file.file_name} />)}
          </div>}
          {!isUser && <MessageSources sources={msg.sources} />}

          {isLast && !isStreaming && suggestedQuestions.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 10 }}>
              <span style={{ fontSize: 12, color: T.textTer, fontWeight: 500 }}>推荐问题</span>
              {suggestedQuestions.map((q, i) => (
                <button key={i} onClick={() => handleSuggestClick(q)}
                  style={{ alignSelf: 'flex-start', padding: '6px 14px', background: '#ffffff', border: `1px solid ${T.border}`, borderRadius: 20, fontSize: 13, color: T.green.strong, cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s' }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = T.accent; e.currentTarget.style.background = T.green.bg; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.background = '#ffffff'; }}>
                  {q}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  };

  // SVG icon components
  const SendSvg = () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );

  const HistorySvg = () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
    </svg>
  );

  const CloseSvg = () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );

  const DeleteSvg = () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );

  const PlusSvg = () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );

  // Bot icon for AI assistant
  const BotSvg = () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="10" rx="2" /><circle cx="12" cy="5" r="2" /><path d="M12 7v4" /><line x1="8" y1="16" x2="8" y2="16" /><line x1="16" y1="16" x2="16" y2="16" />
    </svg>
  );

  return (
    <div style={containerStyle}>
      <div style={mainAreaStyle}>
        {/* 顶部浮动操作按钮 */}
        <button onClick={() => navigate(-1)}
          style={{ position: 'absolute', top: 12, left: 12, zIndex: 10, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', border: 'none', borderRadius: '50%', background: '#ffffff', boxShadow: '0 1px 4px rgba(0,0,0,0.08)', cursor: 'pointer', color: T.textPri, fontSize: 18, fontWeight: 600, lineHeight: 1, transition: 'all 0.15s' }}
          aria-label="返回上一级"
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = T.surfaceSoft; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = '#ffffff'; }}>
          ‹
        </button>

        {/* 历史记录按钮 */}
        <button onClick={() => setShowSidebar(!showSidebar)}
          style={{ position: 'absolute', top: 12, right: 12, zIndex: 10, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', border: 'none', borderRadius: '50%', background: showSidebar ? T.green.bg : '#ffffff', boxShadow: '0 1px 4px rgba(0,0,0,0.08)', cursor: 'pointer', color: showSidebar ? T.accent : T.textSec, transition: 'all 0.15s' }}
          aria-label={showSidebar ? '关闭历史记录' : '打开历史记录'}>
          <HistorySvg />
        </button>

        {/* Messages Area */}
        <div style={msgAreaStyle}>
          {history.initial && <p role="status" style={{ textAlign: 'center', color: T.textSec }}>正在加载…</p>}
          {(history.beforeId || history.failure === 'initial') && <button type="button" disabled={history.more}
            onClick={history.failure === 'initial' ? history.reload : history.loadOlder}
            style={{ alignSelf: 'center', border: 0, background: 'transparent', color: T.green.strong, padding: '8px 12px', marginBottom: 12 }}>
            {history.more ? '正在加载…' : history.failure ? '加载失败，重试' : '查看更早消息'}
          </button>}
          {messages.length === 0 && !streamingContent && !isStreaming && !history.initial && !history.failure && (
            examKnowledgeAvailable === false ? <ExamKnowledgeEmpty /> : <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: T.textTer }}>
              <div style={{ width: 72, height: 72, borderRadius: 16, background: T.green.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', color: T.accent, marginBottom: 20, boxShadow: T.shadowMd }}>
                <BotSvg />
              </div>
              <h2 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 600, color: T.textPri }}>你好，我是教学助手</h2>
              <p style={{ margin: 0, fontSize: 14, color: T.textSec, maxWidth: 360, lineHeight: 1.7 }}>
                我可以帮你查询知识点、分析学生数据、总结错题、提供教学建议。
              </p>
              <p style={{ margin: '4px 0 0', fontSize: 13, color: T.textTer, maxWidth: 360 }}>
                点击下方输入框开始对话，或从右侧历史记录进入已有对话。
              </p>
            </div>
          )}
          {messages.map(renderMessage)}
          {streamingContent && (
            <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 16 }}>
              <div style={{ maxWidth: '80%', minWidth: 0 }}>
                <div style={{ padding: '14px 18px', borderRadius: '4px 12px 12px 12px', background: '#ffffff', color: T.textPri, borderLeft: '3px solid #5B9E6F', boxShadow: '0 1px 4px rgba(0,0,0,0.06)', lineHeight: 1.7, fontSize: 14, wordBreak: 'break-word' }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                    code({ className, children, ...props }) {
                      if (!className) return <code style={{ background: T.green.bg2, padding: '2px 6px', borderRadius: 4, fontSize: '0.88em', color: T.green.strong }} {...props}>{children}</code>;
                      return <pre style={{ background: '#1e293b', color: '#e2e8f0', padding: 14, borderRadius: 8, overflow: 'auto', fontSize: 13 }}><code className={className} {...props}>{children}</code></pre>;
                    }
                  }}>{streamingContent}</ReactMarkdown>
                  <span style={{ display: 'inline-block', width: 2, height: 16, background: T.accent, marginLeft: 2, verticalAlign: 'middle', animation: 'cursor-blink 0.8s step-end infinite' }} aria-hidden="true" />
                </div>
              </div>
            </div>
          )}
          {(isStreaming && !streamingContent) && (
            <div style={{ marginBottom: 16, paddingLeft: 0 }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '14px 18px', background: '#ffffff', borderLeft: '3px solid #5B9E6F', boxShadow: '0 1px 4px rgba(0,0,0,0.06)', borderRadius: '4px 12px 12px 12px', fontSize: 13, color: T.textSec }} role="status" aria-label={intentLabel || '小e正在思考中'}>
                {/* 检索中动画：放大镜脉冲 */}
                {intentLabel.includes('检索') ? (
                  <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', animation: 'searchingPulse 1.2s ease-in-out infinite' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={T.accent} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                    </svg>
                  </span>
                ) : intentLabel.includes('生成') ? (
                  <span style={{ display: 'inline-flex', gap: 2, alignItems: 'flex-end' }}>
                    <span style={{ width: 3, height: 10, borderRadius: 2, background: T.accent, animation: 'typingBar 0.8s ease-in-out infinite' }} />
                    <span style={{ width: 3, height: 14, borderRadius: 2, background: T.accent, animation: 'typingBar 0.8s ease-in-out 0.15s infinite' }} />
                    <span style={{ width: 3, height: 8, borderRadius: 2, background: T.accent, animation: 'typingBar 0.8s ease-in-out 0.3s infinite' }} />
                  </span>
                ) : (
                  <>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.green.primary, animation: 'pulse 1.4s ease-in-out infinite' }} />
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.green.primary, animation: 'pulse 1.4s ease-in-out 0.2s infinite' }} />
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.green.primary, animation: 'pulse 1.4s ease-in-out 0.4s infinite' }} />
                  </>
                )}
                <span>{intentLabel || '小e正在思考...'}</span>
              </span>
            </div>
          )}
          <div ref={msgEndRef} />
        </div>

        {attachmentError && <p role="alert" style={{ margin: '4px 20px', color: '#9c392c' }}>{attachmentError}</p>}
        {!!pending.files.length && <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, margin: '6px 20px' }}>
          {pending.files.map(file => <button key={file.id} type="button" disabled={isStreaming}
            onClick={() => pending.remove(file.id)} aria-label={`移除 ${file.name}`}>{file.name} ×</button>)}
        </div>}
        <div style={inputAreaStyle}>
          <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 40, height: 40, border: `1px solid ${T.border}`, borderRadius: T.rSm, cursor: 'pointer', color: T.textSec, flexShrink: 0, position: 'relative', overflow: 'hidden', transition: 'all 0.15s', background: '#ffffff' }}
            aria-label="上传文件"
            onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.borderColor = T.accent; el.style.color = T.accent; el.style.background = T.green.bg; }}
            onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.borderColor = T.border; el.style.color = T.textSec; el.style.background = '#ffffff'; }}>
            <PlusSvg />
            <input type="file" multiple disabled={isStreaming} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', opacity: 0, cursor: 'pointer' }} accept={`${CHAT_FILE_ACCEPT},${CHAT_IMAGE_ACCEPT}`} onChange={handleFileUpload} />
          </label>
          <textarea ref={inputRef} value={isStreaming ? '' : inputValue} disabled={isStreaming} onChange={event => pending.setText(event.target.value)} onKeyDown={handleKeyDown}
            placeholder="输入你的问题…"
            style={inputStyle} rows={1}
            onFocus={e => { e.currentTarget.style.borderColor = T.accent; e.currentTarget.style.boxShadow = `0 0 0 3px ${T.green.bg}`; e.currentTarget.style.background = '#ffffff'; }}
            onBlur={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.background = '#f8f9fa'; }}
            onInput={e => { const t = e.currentTarget; t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 96) + 'px'; }}
            aria-label="消息输入框" />
          <button style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 40, height: 40, border: 'none', borderRadius: T.rSm, background: inputValue.trim() && !isStreaming ? 'linear-gradient(135deg, #2d7d46, #5B9E6F)' : T.border, color: '#ffffff', cursor: inputValue.trim() && !isStreaming ? 'pointer' : 'not-allowed', fontSize: 13, fontWeight: 500, flexShrink: 0, transition: 'all 0.15s', boxShadow: inputValue.trim() && !isStreaming ? '0 2px 8px rgba(93,158,111,0.3)' : 'none' }}
            disabled={!inputValue.trim() || isStreaming} onClick={handleStreamSend} aria-label="发送消息">
            <SendSvg />
          </button>
        </div>
      </div>

      {/* History Sidebar */}
      {showSidebar && (
        <div style={sidebarStyle}>
          <div style={sidebarHeaderStyle}>
            <span style={{ fontSize: 15, fontWeight: 600, color: T.textPri }}>
              {isBatchMode ? `已选 ${selectedIds.size} 项` : '历史会话'}
            </span>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <button style={{
                width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: 'none', background: isBatchMode ? T.green.bg : 'transparent',
                cursor: 'pointer', color: isBatchMode ? T.accent : T.textTer,
                borderRadius: '50%', transition: 'background 0.15s', fontSize: 12, fontWeight: 600,
              }}
                onClick={() => { setIsBatchMode(!isBatchMode); if (!isBatchMode) setSelectedIds(new Set()); }}
                aria-label={isBatchMode ? '退出批量模式' : '批量选择'}
                title={isBatchMode ? '退出批量模式' : '批量选择'}
                onMouseEnter={e => { if (!isBatchMode) (e.currentTarget as HTMLElement).style.background = T.borderLight; }}
                onMouseLeave={e => { if (!isBatchMode) (e.currentTarget as HTMLElement).style.background = 'transparent'; }}>
                ☐
              </button>
              <button style={{
                width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: 'none', background: 'transparent', cursor: 'pointer', color: T.textTer,
                borderRadius: '50%', transition: 'all 0.15s', fontSize: 13,
              }}
                onClick={() => setShowSkillManager(true)} aria-label="技能管理"
                title="技能管理"
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = T.green.bg; (e.currentTarget as HTMLElement).style.color = T.accent; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = T.textTer; }}>
                ⚡
              </button>
              <button style={{
                width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: 'none', background: 'transparent', cursor: 'pointer', color: T.textTer,
                borderRadius: '50%', transition: 'background 0.15s',
              }}
                onClick={() => setShowSidebar(false)} aria-label="关闭侧边栏"
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = T.borderLight; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}>
                <CloseSvg />
              </button>
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 10px' }}>
            {!isBatchMode && (
              <button style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, width: '100%', padding: '8px', border: `1px dashed ${T.border}`, borderRadius: T.rMd, background: 'transparent', color: T.accent, cursor: 'pointer', fontSize: 13, fontWeight: 500, transition: 'all 0.2s', marginBottom: 10 }}
                onClick={handleNewSession}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = T.green.bg; (e.currentTarget as HTMLElement).style.borderColor = T.accent; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.borderColor = T.border; }}>
                <PlusSvg /> 新建对话
              </button>
            )}
            {sessions.length === 0 && (
              <div style={{ fontSize: 13, color: T.textTer, textAlign: 'center', padding: 20 }}>暂无历史会话</div>
            )}
            {sessions.map(s => {
              const isSelected = selectedIds.has(s.id);
              const isCurrent = currentSessionId === s.id;
              return (
                <button key={s.id} style={{
                  padding: isBatchMode ? '8px 12px 8px 8px' : '8px 12px',
                  borderRadius: T.rMd, cursor: 'pointer', marginBottom: 4, border: 'none', width: '100%', textAlign: 'left',
                  display: 'flex', flexDirection: 'column', gap: 2,
                  background: isBatchMode
                    ? (isSelected ? T.green.bg : 'transparent')
                    : (isCurrent ? T.green.bg : 'transparent'),
                  outline: isBatchMode && isSelected ? `2px solid ${T.accent}` : 'none',
                  outlineOffset: -1,
                  transition: 'background 0.15s',
                }} onClick={() => {
                  if (isBatchMode) {
                    setSelectedIds(prev => { const n = new Set(prev); if (n.has(s.id)) n.delete(s.id); else n.add(s.id); return n; });
                  } else {
                    handleSelectSession(s.id);
                  }
                }}
                  onMouseEnter={e => {
                    if ((isBatchMode && !isSelected) || (!isBatchMode && !isCurrent))
                      (e.currentTarget as HTMLElement).style.background = T.borderLight;
                  }}
                  onMouseLeave={e => {
                    if ((isBatchMode && !isSelected) || (!isBatchMode && !isCurrent))
                      (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    {isBatchMode && (
                      <span style={{
                        width: 18, height: 18, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        borderRadius: 4, border: `2px solid ${isSelected ? T.accent : T.border}`,
                        background: isSelected ? T.accent : 'transparent',
                        color: '#fff', fontSize: 11, fontWeight: 700, flexShrink: 0, marginRight: 8,
                        transition: 'all 0.1s',
                      }}>
                        {isSelected ? '✓' : ''}
                      </span>
                    )}
                    <span style={{
                      fontSize: 13, fontWeight: 600, color: T.textPri,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
                    }}>{s.title || `对话 ${s.id}`}</span>
                    {!isBatchMode && (
                      <button style={{ width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center', border: 'none', background: 'transparent', cursor: 'pointer', color: T.textTer, fontSize: 12, opacity: 0, borderRadius: '50%', transition: 'opacity 0.1s', flexShrink: 0 }}
                        className="del-btn" onClick={e => handleDeleteSession(e, s.id)}
                        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '0'; }} aria-label="删除会话">
                        <DeleteSvg />
                      </button>
                    )}
                  </div>
                  {s.summary && <span style={{ fontSize: 12, color: T.textTer, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.summary}</span>}
                  <span style={{ fontSize: 11, color: T.textTer }}>{formatTime(s.created_at)}</span>
                </button>
              );
            })}
          </div>
          {isBatchMode && (
            <div style={{
              padding: '10px 12px', borderTop: `1px solid ${T.borderLight}`,
              display: 'flex', flexDirection: 'column', gap: 8, flexShrink: 0,
            }}>
              <button style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                width: '100%', padding: '7px', border: `1px solid ${T.border}`, borderRadius: T.rMd,
                background: 'transparent', color: T.textPri, cursor: 'pointer', fontSize: 13,
                transition: 'all 0.15s',
              }}
                onClick={handleSelectAll}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = T.borderLight; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}>
                {selectedIds.size === sessions.length ? '取消全选' : '全选'}
              </button>
              <button style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                width: '100%', padding: '8px', border: 'none', borderRadius: T.rMd,
                background: selectedIds.size > 0 ? '#dc3545' : T.border,
                color: '#fff', cursor: selectedIds.size > 0 ? 'pointer' : 'not-allowed',
                fontSize: 13, fontWeight: 600, transition: 'all 0.15s',
              }}
                disabled={selectedIds.size === 0 || batchDeleteLoading}
                onClick={handleBatchDelete}>
                {batchDeleteLoading ? '清除中...' : `清除 ${selectedIds.size} 个会话`}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Animations */}
      <style>{`@keyframes cursor-blink { 50% { opacity: 0; } } @keyframes pulse { 0%,80%,100% { transform: scale(0.8); opacity:0.5; } 50% { transform: scale(1); opacity:1; } } @keyframes searchingPulse { 0%,100% { transform: scale(1); opacity: 0.6; } 50% { transform: scale(1.25); opacity: 1; } } @keyframes typingBar { 0%,100% { opacity: 0.4; transform: scaleY(0.6); } 50% { opacity: 1; transform: scaleY(1.1); } }`}</style>

      {/* Agent Skills 管理弹窗 */}
      <SkillManager visible={showSkillManager} onClose={() => setShowSkillManager(false)} />
    </div>
  );
}
