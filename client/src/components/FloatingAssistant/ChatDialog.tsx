// 对话弹窗组件 — 消息列表 + 输入框 + SSE 流式对话
import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { teachingAssistantApi, SourceItem } from '../../api/teachingAssistant';
import MessageBubble from './MessageBubble';
import { examSourcePath } from '../../shared/exams/ChatExamEvidence';
import PptInfoForm from './PptInfoForm';
import ExamInfoForm from './ExamInfoForm';
import { IconX, IconPlus } from '../../design-system';
import { usePanelDrag } from './usePanelDrag';

interface ChatDialogProps {
  onClose: () => void;
}

interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  actionCard?: ActionCardData | null;
  sources?: SourceItem[] | null;
}

interface ActionCardData {
  type: 'action_card';
  action_type: 'ppt' | 'exam';
  data: PptCardData | ExamCardData;
}

interface PptCardData {
  action_type: 'ppt';
  outline: string[];
  knowledge_points: string[];
  suggested_title: string;
  suggested_grade: string;
  suggested_lesson_type: string;
}

interface ExamCardData {
  action_type: 'exam';
  question_types: Record<string, number>;
  knowledge_points: string[];
  suggested_title: string;
  suggested_grade: string;
  suggested_difficulty: string;
}

export default function ChatDialog({ onClose }: ChatDialogProps) {
  const { panelRef, rect, handleTitleMouseDown, handleResizeMouseDown } = usePanelDrag('chat_dialog');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingCard, setStreamingCard] = useState<ActionCardData | null>(null);
  const [streamingSources, setStreamingSources] = useState<SourceItem[]>([]);
  const [statusLabel, setStatusLabel] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [showPptForm, setShowPptForm] = useState(false);
  const [pendingPptQuery, setPendingPptQuery] = useState('');
  const [showExamForm, setShowExamForm] = useState(false);
  const [pendingExamQuery, setPendingExamQuery] = useState('');

  const msgEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // 用 ref 同步 streamingCard，避免回调闭包读到 stale 值
  const streamingCardRef = useRef<ActionCardData | null>(null);

  // 用 ref 同步 streamingSources，避免回调闭包读到 stale 值
  const streamingSourcesRef = useRef<SourceItem[]>([]);

  // 检测用户输入是否为 PPT 制作请求（无具体主题时弹出表单）
  const isPptRequestWithoutDetails = useCallback((text: string): boolean => {
    const t = text.trim().toLowerCase();
    const pptKeywords = ['ppt', '课件', '幻灯片', '制作课件', '做课件', '生成课件'];
    const hasPptKeyword = pptKeywords.some(kw => t.includes(kw));

    const hasSpecificTopic =
      /关于.+的/.test(t) ||
      /以.+为主题/.test(t) ||
      /主题[是为：:]\s*\S+/.test(t) ||
      t.length > 20;

    return hasPptKeyword && !hasSpecificTopic;
  }, []);

  // 检测用户输入是否为试卷生成请求（无详细信息时弹出表单）
  const isExamRequestWithoutDetails = useCallback((text: string): boolean => {
    const t = text.trim().toLowerCase();

    // 排除：查询已有试卷内容（原文/翻译/答案/第X题/第X篇/历年真题等），直接放过
    const isQueryIntent =
      /(原文|翻译|答案|范文|赏析|解析)/.test(t) ||
      /第[一二三四五六七八九十\d]+[题篇段]/.test(t) ||
      /(给出|提供|查找|搜索|看看|查询|找一下|找找|\d{4}年).*(试卷|试题|题目|考题|真题|高考|中考)/.test(t) ||
      /\d{4}年/.test(t);  // 带年份的通常是查询历年真题内容

    if (isQueryIntent) return false;

    // 试卷创建意图关键词（需要行动动词+试卷，或独立出卷/出题/考试卷）
    const examKeywords = ['出卷', '出题', '生成试卷', '生成考卷', '做试卷', '来一份试卷', '考试卷'];
    const hasExamKeyword = examKeywords.some(kw => t.includes(kw)) ||
      /(出|生成|制作|创建|做|来).*(一套|一份|个|张).*(试卷|考题|考试卷|考卷)/.test(t);

    if (!hasExamKeyword) return false;

    // 检测是否包含具体信息（包含知识点、题材、年级、题型等细节）
    const hasExamDetails =
      /关于.+的/.test(t) ||                     // "关于现在进行时的试卷"
      /知识点/.test(t) ||                        // 提到了知识点
      /年级/.test(t) ||                          // 提到了年级
      /[题型].*[道题]/.test(t) ||                // "选择题5道"
      /(选择|填空|判断|阅读|写作|听力).*\d/.test(t) ||  // 题型+数量
      t.length > 30;                            // 较长的描述通常包含足够信息

    return !hasExamDetails;
  }, []);

  // 检查登录状态
  useEffect(() => {
    const token = localStorage.getItem('token');
    setIsLoggedIn(!!token);
  }, []);

  // 自动创建/恢复会话
  useEffect(() => {
    const initSession = async () => {
      setIsLoadingHistory(true);
      try {
        const s = await teachingAssistantApi.createSession(null);
        setSessionId(s.id);
      } catch {
        // 忽略
      } finally {
        setIsLoadingHistory(false);
      }
    };
    initSession();
  }, []);

  const scrollBottom = useCallback(() => {
    setTimeout(() => msgEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }, []);

  useEffect(() => {
    scrollBottom();
  }, [messages, streamingContent, scrollBottom]);

  // 自动聚焦输入框
  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 300);
  }, []);

  // Esc 关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  const handleNewSession = useCallback(async () => {
    if (isStreaming) {
      abortRef.current?.abort();
      setIsStreaming(false);
    }
    try {
      const s = await teachingAssistantApi.createSession(null);
      setSessionId(s.id);
      setMessages([]);
      setStreamingContent('');
      setStreamingCard(null);
      setStreamingSources([]);
      setStatusLabel('');
    } catch { /* ignore */ }
    setShowPptForm(false);
    setPendingPptQuery('');
    setShowExamForm(false);
    setPendingExamQuery('');
  }, [isStreaming]);

  // PPT 表单提交成功
  const handlePptFormSuccess = useCallback((pptId: number) => {
    setShowPptForm(false);
    setPendingPptQuery('');
    setMessages(prev => [...prev, {
      id: Date.now(),
      role: 'assistant',
      content: `✅ PPT 课件已创建成功！[查看PPT](/ppt/edit/${pptId})`,
    }]);
  }, []);

  // 取消 PPT 表单，回到输入状态
  const handlePptFormCancel = useCallback(() => {
    setShowPptForm(false);
    setPendingPptQuery('');
    setTimeout(() => inputRef.current?.focus(), 100);
  }, []);

  // 用 ref 同步 streamingCard，避免闭包中读到 stale 值
  useEffect(() => {
    streamingCardRef.current = streamingCard;
  }, [streamingCard]);

  // 用 ref 同步 streamingSources
  useEffect(() => {
    streamingSourcesRef.current = streamingSources;
  }, [streamingSources]);

  // ─── 共用的 SSE 流消费逻辑 ──────────────────────────
  // 不使用 useCallback，靠 ref 读取最新 streamingCard
  const consumeSSEStream = useCallback(async (convId: string, msg: string) => {
    abortRef.current = new AbortController();
    try {
      const resp = await teachingAssistantApi.chatStream({
        conversation_id: convId,
        message: msg,
        class_id: null,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const reader = resp.body?.getReader();
      if (!reader) throw new Error('无法读取响应流');

      const decoder = new TextDecoder();
      let buf = '';
      let currentEvent = '';
      let accumulatedContent = '';
      let finalConvId = convId;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
            continue;
          }
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (data === '[DONE]') continue;
          try {
            const p = JSON.parse(data);
            const ev = currentEvent || p.event || p.type;
            currentEvent = '';

            if (ev === 'intent') {
              const m: Record<string,string> = {
                knowledge_lookup:'知识查询', document_query:'文档查询',
                class_stats:'班级统计', student_analysis:'学生分析',
                error_summary:'错题总结', teaching_advice:'教学建议',
                lesson_prep:'备课助手', general_chat:'自由对话'
              };
              setStatusLabel(m[p.intent] || p.intent);
            } else if (ev === 'status') {
              setStatusLabel(p.message || '处理中...');
            } else if (ev === 'searching') {
              setStatusLabel('正在检索...');
            } else if (ev === 'chunk') {
              setStatusLabel('AI 正在生成回答...');
              const textChunk = p.text || p.content || '';
              accumulatedContent += textChunk;
              setStreamingContent(prev => prev + textChunk);
            } else if (ev === 'action_card_start') {
              const card: ActionCardData = { type: 'action_card', action_type: p.action_type, data: p };
              setStreamingCard(card);
              streamingCardRef.current = card;
            } else if (ev === 'action_card_data') {
              const card: ActionCardData = {
                type: 'action_card',
                action_type: p.action_type || p.data?.action_type,
                data: p.data || p,
              };
              setStreamingCard(card);
              streamingCardRef.current = card;
            } else if (ev === 'action_card_end') {
              // 卡片数据已就绪
            } else if (ev === 'sources') {
              const items: SourceItem[] = p.sources || p.items || [];
              setStreamingSources(items);
            } else if (ev === 'done' || ev === 'complete') {
              finalConvId = p.conversation_id || p.conversationId || convId;
              setSessionId(finalConvId);

              const cardData = streamingCardRef.current;
              const sources = streamingSourcesRef.current;
              if (cardData) {
                setMessages(prev => [...prev, {
                  id: p.message_id || Date.now(),
                  role: 'assistant',
                  content: accumulatedContent,
                  actionCard: cardData,
                  sources: sources.length > 0 ? sources : null,
                }]);
              } else if (accumulatedContent) {
                setMessages(prev => [...prev, {
                  id: p.message_id || Date.now(),
                  role: 'assistant',
                  content: accumulatedContent,
                  sources: sources.length > 0 ? sources : null,
                }]);
              }
              setStreamingContent('');
              setStreamingCard(null);
              setStreamingSources([]);
              setStatusLabel('');
              streamingCardRef.current = null;
              streamingSourcesRef.current = [];
            }
          } catch { /* ignore non-json */ }
        }
      }

      // fallback：流结束但没有 done 事件时兜底
      if (accumulatedContent) {
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last?.role === 'assistant') return prev;
          const cardData = streamingCardRef.current;
          const sources = streamingSourcesRef.current;
          return [...prev, {
            id: Date.now(),
            role: 'assistant',
            content: accumulatedContent,
            actionCard: cardData,
            sources: sources.length > 0 ? sources : null,
          }];
        });
        setStreamingContent('');
        setStreamingCard(null);
        setStreamingSources([]);
        streamingCardRef.current = null;
        streamingSourcesRef.current = [];
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      setMessages(prev => [...prev, {
        id: Date.now(),
        role: 'assistant',
        content: `**出错了**：${err.message || '请求失败，请重试'}`,
      }]);
    } finally {
      setIsStreaming(false);
      setStatusLabel('');
      abortRef.current = null;
    }
  }, []);

  // 试卷表单提交成功 — 直接显示跳转链接
  const handleExamFormSuccess = useCallback((examId: number) => {
    setShowExamForm(false);
    setPendingExamQuery('');
    setMessages(prev => [...prev, {
      id: Date.now(),
      role: 'assistant',
      content: `✅ 试卷已创建成功！[查看试卷](/exams/create?id=${examId})`,
    }]);
  }, []);

  // 取消试卷表单
  const handleExamFormCancel = useCallback(() => {
    setShowExamForm(false);
    setPendingExamQuery('');
    setTimeout(() => inputRef.current?.focus(), 100);
  }, []);

  const handleSend = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isStreaming || isLoadingHistory || !isLoggedIn) return;

    // 检测 PPT 制作请求（无具体主题）
    if (isPptRequestWithoutDetails(text)) {
      setPendingPptQuery(text);
      setShowPptForm(true);
      setInputValue('');
      setMessages(prev => [...prev, { id: Date.now(), role: 'user', content: text }]);
      return;
    }

    // 检测试卷生成请求（无详细信息）
    if (isExamRequestWithoutDetails(text)) {
      setPendingExamQuery(text);
      setShowExamForm(true);
      setInputValue('');
      setMessages(prev => [...prev, { id: Date.now(), role: 'user', content: text }]);
      return;
    }

    setInputValue('');
    setStreamingContent('');
    setStreamingCard(null);
    setStreamingSources([]);
    streamingCardRef.current = null;
    streamingSourcesRef.current = [];
    setStatusLabel('思考中...');
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', content: text }]);
    setIsStreaming(true);

    let convId = sessionId;
    if (!convId) {
      try {
        const s = await teachingAssistantApi.createSession(null);
        setSessionId(s.id);
        convId = s.id;
      } catch {
        setIsStreaming(false);
        return;
      }
    }

    await consumeSSEStream(convId, text);
  }, [inputValue, isStreaming, isLoadingHistory, isLoggedIn, sessionId, isPptRequestWithoutDetails, isExamRequestWithoutDetails]);

  // 键盘发送
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isLoggedIn) {
    const unloggedStyle: React.CSSProperties = {
      position: 'fixed', left: rect.x, top: rect.y,
      width: rect.width, height: rect.height,
      zIndex: 9999, background: '#fff', borderRadius: 16,
      boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
      border: '1px solid rgba(0,0,0,0.08)',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
      animation: 'dialogIn 250ms cubic-bezier(0.34, 1.56, 0.64, 1)',
    };
    return (
      <div ref={panelRef} style={unloggedStyle}>
        <div style={headerStyle}>
          <span style={{ fontSize: 15, fontWeight: 600, color: '#1a2e1a' }}>小e助手</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <IconPlus size={16} color="#6b7280" />
            <div onClick={onClose} style={{ cursor: 'pointer', display: 'flex' }}>
              <IconX size={16} color="#6b7280" />
            </div>
          </div>
        </div>
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          padding: 24, textAlign: 'center',
        }}>
          <IconBulb size={48} color="#2d7d46" />
          <p style={{ margin: '16px 0 8px', fontSize: 16, fontWeight: 600, color: '#1a2e1a' }}>
            请先登录
          </p>
          <p style={{ margin: 0, fontSize: 13, color: '#6b7280', marginBottom: 20 }}>
            登录后方可使用小e助手
          </p>
          <button
            onClick={() => { window.location.href = `${import.meta.env.BASE_URL}login`; }}
            style={{
              padding: '10px 32px',
              borderRadius: 50,
              border: 'none',
              background: '#2d7d46',
              color: '#fff',
              fontSize: 14,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            去登录
          </button>
        </div>
      </div>
    );
  }

  const containerStyle: React.CSSProperties = {
    position: 'fixed',
    left: rect.x,
    top: rect.y,
    width: rect.width,
    height: rect.height,
    zIndex: 9999,
    background: '#fff',
    borderRadius: 16,
    boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
    border: '1px solid rgba(0,0,0,0.08)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    animation: 'dialogIn 250ms cubic-bezier(0.34, 1.56, 0.64, 1)',
  };

  return (
    <div ref={panelRef} style={containerStyle}>
      {/* 头部 — 拖拽把手 */}
      <div
        style={headerStyle}
        onMouseDown={handleTitleMouseDown}
      >
        <span style={{ fontSize: 15, fontWeight: 600, color: '#1a2e1a' }}>
          小e助手
          {isStreaming && (
            <span style={{
              marginLeft: 8, fontSize: 11, color: '#2d7d46',
              fontWeight: 400,
            }}>
              {statusLabel || '思考中...'}
            </span>
          )}
        </span>
        <div style={{ display: 'flex', gap: 6 }}>
          <div
            onClick={handleNewSession}
            title="新建会话"
            style={{ cursor: 'pointer', display: 'flex', padding: 2 }}
          >
            <IconPlus size={16} color="#6b7280" />
          </div>
          <div
            onClick={onClose}
            style={{ cursor: 'pointer', display: 'flex', padding: 2 }}
          >
            <IconX size={16} color="#6b7280" />
          </div>
        </div>
      </div>

      {/* 消息列表 */}
      <div style={msgListStyle}>
        {messages.length === 0 && !isLoadingHistory && (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            padding: '40px 24px', textAlign: 'center',
          }}>
            <IconBulb size={40} color="#2d7d46" />
            <p style={{ marginTop: 12, fontSize: 14, color: '#6b7280', lineHeight: 1.6 }}>
              我是小e，你的教学助手<br />
              可以问我问题、让我做PPT或出试卷
            </p>
            <div style={{
              marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'center',
            }}>
              {['帮我做一份PPT', '出一套试卷', '总结错题报告'].map(q => (
                <div
                  key={q}
                  onClick={() => {
                    setInputValue(q);
                    setTimeout(() => inputRef.current?.focus(), 0);
                  }}
                  style={{
                    padding: '6px 14px',
                    borderRadius: 50,
                    border: '1px solid #d4edda',
                    background: '#e6f7e6',
                    color: '#2d7d46',
                    fontSize: 12,
                    cursor: 'pointer',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = '#d4edda'; }}
                  onMouseLeave={e => { e.currentTarget.style.background = '#e6f7e6'; }}
                >
                  {q}
                </div>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id}>
            <MessageBubble role={msg.role} content={msg.content} sources={msg.sources} />
            {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
              <SourcesTags sources={msg.sources} />
            )}
          </div>
        ))}

        {/* PPT 信息填写表单 */}
        {showPptForm && (
          <div style={{ marginLeft: 36, marginBottom: 12 }}>
            <PptInfoForm onSuccess={handlePptFormSuccess} onCancel={handlePptFormCancel} />
          </div>
        )}

        {/* 试卷信息填写表单 */}
        {showExamForm && (
          <div style={{ marginLeft: 36, marginBottom: 12 }}>
            <ExamInfoForm onSuccess={handleExamFormSuccess} onCancel={handleExamFormCancel} />
          </div>
        )}

        {/* 流式消息 */}
        {streamingContent && (
          <MessageBubble role="assistant" content={streamingContent} isStreaming />
        )}

        {/* 流式来源标签 */}
        {streamingSources.length > 0 && (
          <SourcesTags sources={streamingSources} />
        )}

        {/* 思考动画指示器 — 流式中但尚未收到内容时显示 */}
        {isStreaming && !streamingContent && (
          <div style={{ marginBottom: 8 }} role="status" aria-label={statusLabel || '小e正在思考中'}>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '10px 14px', background: '#ffffff',
              borderLeft: '3px solid #5B9E6F',
              boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
              borderRadius: '4px 10px 10px 10px',
              fontSize: 12, color: '#6b7280',
            }}>
              {statusLabel.includes('检索') ? (
                <span className="think-search-icon">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2d7d46" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                  </svg>
                </span>
              ) : statusLabel.includes('生成') ? (
                <span style={{ display: 'inline-flex', gap: 2, alignItems: 'flex-end' }}>
                  <span className="think-typing-bar" style={{ animationDelay: '0s' }} />
                  <span className="think-typing-bar" style={{ animationDelay: '0.15s' }} />
                  <span className="think-typing-bar" style={{ animationDelay: '0.3s' }} />
                </span>
              ) : (
                <>
                  <span className="think-dot" />
                  <span className="think-dot think-dot2" />
                  <span className="think-dot think-dot3" />
                </>
              )}
              <span>{statusLabel || '小e正在思考...'}</span>
            </span>
          </div>
        )}

        <div ref={msgEndRef} />
      </div>

      {/* 输入区 */}
      <div style={inputAreaStyle}>
        <textarea
          ref={inputRef}
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息，回车发送..."
          disabled={isStreaming}
          rows={1}
          style={{
            flex: 1,
            border: '1px solid #e2e8f0',
            borderRadius: 8,
            outline: 'none',
            resize: 'none',
            minHeight: 36,
            maxHeight: 80,
            lineHeight: 1.5,
            fontFamily: 'inherit',
            fontSize: 13,
            color: '#0f172a',
            background: '#f8f9fa',
            padding: '8px 12px',
            boxSizing: 'border-box',
            transition: 'border-color 0.15s',
          }}
          onFocus={e => { e.currentTarget.style.borderColor = '#5B9E6F'; }}
          onBlur={e => { e.currentTarget.style.borderColor = '#e2e8f0'; }}
        />
        <button
          onClick={handleSend}
          disabled={!inputValue.trim() || isStreaming || isLoadingHistory}
          style={{
            width: 36,
            height: 36,
            borderRadius: '50%',
            border: 'none',
            background: inputValue.trim() && !isStreaming ? '#2d7d46' : '#e2e8f0',
            color: '#fff',
            cursor: inputValue.trim() && !isStreaming ? 'pointer' : 'default',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            transition: 'background 0.15s',
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
          </svg>
        </button>
      </div>

      {/* ── 调整大小把手 ── */}
      <div onMouseDown={e => handleResizeMouseDown('n', e)} style={{ position: 'absolute', top: -2, left: RESIZE_HANDLE_SIZE, right: RESIZE_HANDLE_SIZE, height: RESIZE_HANDLE_SIZE, cursor: 'n-resize', zIndex: 10 }} />
      <div onMouseDown={e => handleResizeMouseDown('s', e)} style={{ position: 'absolute', bottom: -2, left: RESIZE_HANDLE_SIZE, right: RESIZE_HANDLE_SIZE, height: RESIZE_HANDLE_SIZE, cursor: 's-resize', zIndex: 10 }} />
      <div onMouseDown={e => handleResizeMouseDown('w', e)} style={{ position: 'absolute', left: -2, top: RESIZE_HANDLE_SIZE, bottom: RESIZE_HANDLE_SIZE, width: RESIZE_HANDLE_SIZE, cursor: 'w-resize', zIndex: 10 }} />
      <div onMouseDown={e => handleResizeMouseDown('e', e)} style={{ position: 'absolute', right: -2, top: RESIZE_HANDLE_SIZE, bottom: RESIZE_HANDLE_SIZE, width: RESIZE_HANDLE_SIZE, cursor: 'e-resize', zIndex: 10 }} />
      {/* 角 */}
      <div onMouseDown={e => handleResizeMouseDown('nw', e)} style={{ position: 'absolute', top: -4, left: -4, width: 14, height: 14, cursor: 'nw-resize', zIndex: 11 }} />
      <div onMouseDown={e => handleResizeMouseDown('ne', e)} style={{ position: 'absolute', top: -4, right: -4, width: 14, height: 14, cursor: 'ne-resize', zIndex: 11 }} />
      <div onMouseDown={e => handleResizeMouseDown('sw', e)} style={{ position: 'absolute', bottom: -4, left: -4, width: 14, height: 14, cursor: 'sw-resize', zIndex: 11 }} />
      <div onMouseDown={e => handleResizeMouseDown('se', e)} style={{ position: 'absolute', bottom: -4, right: -4, width: 14, height: 14, cursor: 'se-resize', zIndex: 11 }} />
    </div>
  );
}

const RESIZE_HANDLE_SIZE = 8;

// 小e图标占位
function IconBulb({ size, color }: { size: number; color: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a7 7 0 0 0-7 7c0 2.8 1.5 5.2 3.5 6.5V17h7v-1.5C17.5 14.2 19 11.8 19 9a7 7 0 0 0-7-7z" />
      <path d="M10 20h4" />
    </svg>
  );
}

// ─── Styles ──────────────────────────────
const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '12px 16px',
  borderBottom: '1px solid #f0f0f0',
  flexShrink: 0,
  minHeight: 48,
};

const msgListStyle: React.CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '12px 14px',
  background: '#fafafa',
  display: 'flex',
  flexDirection: 'column',
};

const inputAreaStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '10px 14px',
  background: '#f5f5f5',
  borderTop: '1px solid #e8e8e8',
  flexShrink: 0,
};

// 可点击来源标签组件
function SourcesTags({ sources }: { sources: SourceItem[] }) {
  const navigate = useNavigate();

  if (!sources || sources.length === 0) return null;

  const handleSourceClick = (src: SourceItem) => {
    if (src.type === 'exam_result') {
      navigate(examSourcePath(src, 'web'));
      return;
    }
    const params = new URLSearchParams();
    if (src.snippet) params.set('highlight', src.snippet);
    if (src.chunk_id) params.set('chunk', src.chunk_id);
    const query = params.toString();
    navigate(`/documents/view/${src.id}${query ? `?${query}` : ''}`);
  };

  return (
    <div style={{
      marginLeft: 36, marginBottom: 12,
      display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center',
    }}>
      <span style={{ fontSize: 11, color: '#9ca3af', flexShrink: 0 }}>📎 来源：</span>
      {sources.map((src, idx) => (
        <span
          key={`${src.id}-${src.chunk_id || idx}`}
          onClick={() => handleSourceClick(src)}
          title={src.snippet || src.title}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            padding: '3px 10px',
            background: '#e6f7e6',
            borderRadius: 20,
            fontSize: 11,
            color: '#2d7d46',
            cursor: 'pointer',
            maxWidth: 220,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            border: '1px solid #d4edda',
            transition: 'background 0.15s',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLSpanElement).style.background = '#d4edda'; }}
          onMouseLeave={e => { (e.currentTarget as HTMLSpanElement).style.background = '#e6f7e6'; }}
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          {src.title}
        </span>
      ))}
    </div>
  );
}
