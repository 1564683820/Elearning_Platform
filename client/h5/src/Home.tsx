import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CHAT_FILE_ACCEPT, CHAT_IMAGE_ACCEPT, teachingAssistantApi, type ChatResponse, type MessageData, type SessionItem, type SkillItem, type SourceItem } from '../../src/api/teachingAssistant';
import { readEventStream } from '../../src/api/eventStream';
import { Icon, Sheet, errorText } from './ui';
import { ExamKnowledge } from '../../src/shared/exams/ExamKnowledge';
import { ExamKnowledgeEmpty, useExamKnowledgeAvailability } from '../../src/shared/exams/ExamKnowledgeEmpty';
import { ChatExamEvidence, examSourcePath, singleExamEvidence } from '../../src/shared/exams/ChatExamEvidence';
import { ChatAttachmentButton, useChatComposer } from '../../src/shared/ChatAttachments';
import { SKILL_FILE_ACCEPT, useQASkillUpload } from '../../src/shared/qaSkillUpload';
import { recoverChatReply } from '../../src/shared/chatRequests';
import { useChatHistory } from '../../src/shared/chatHistory';

const initialQuestions = ['最近哪些题最容易错？', '10 月随堂测第 8 题错在哪？'];

function sessionFrom(search: string): string | undefined {
  const id = new URLSearchParams(search).get('session');
  return id && /^[1-9]\d{0,18}$/.test(id) ? id : undefined;
}

function homePath(id?: string) {
  return id ? `/?session=${id}` : '/';
}

function sessionDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const now = new Date();
  if (date.toDateString() === now.toDateString()) {
    return `今天 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}`;
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return '昨天';
  const monthDay = `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
  return date.getFullYear() === now.getFullYear() ? monthDay : `${date.getFullYear()} 年 ${monthDay}`;
}

function SourceList({ sources, sessionId }: { sources: SourceItem[] | null; sessionId?: string }) {
  if (!sources?.length) return null;
  return <ul className="sources">{sources.map((source, index) => <li key={index}>
    {source.type === 'exam_result' ? <Link to={examSourcePath(source, 'h5', sessionId)}>
      <span>{source.title}</span><Icon name="upRight" size={18} />
    </Link> : source.type === 'chat_attachment' ? <ChatAttachmentButton id={source.id} name={source.title} /> : source.title}
  </li>)}</ul>;
}

function AssistantReply({ message, sessionId }: { message: MessageData; sessionId?: string }) {
  const evidence = singleExamEvidence(message.sources);
  return <div className="reply">
    <Icon name="sparkle" size={18} />
    <div className={evidence ? 'reply-card reply-card--evidence' : 'reply-card'}>
      {evidence && <ChatExamEvidence evidence={evidence} />}
      <div className="reply-prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div>
      <SourceList sources={message.sources} sessionId={sessionId} />
    </div>
  </div>;
}

export function Home() {
  const navigate = useNavigate();
  const { pathname, search, state, key: locationKey } = useLocation();
  const settings = pathname === '/settings';
  const [drawer, setDrawer] = useState(false);
  const [attachments, setAttachments] = useState(false);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [sessionId, setSessionId] = useState(() => sessionFrom(search));
  const examKnowledgeAvailable = useExamKnowledgeAvailability(pathname === '/' && !sessionId);
  const pending = useChatComposer('h5', sessionId);
  const question = pending.text;
  const [messages, setMessages] = useState<MessageData[]>([]);
  const history = useChatHistory(sessionId, setMessages);
  const [working, setWorking] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [partial, setPartial] = useState('');
  const [error, setError] = useState('');
  const [failedQuestion, setFailedQuestion] = useState('');
  const loadingHistory = history.initial;
  const [historyError, setHistoryError] = useState('');
  const stream = useRef<AbortController>();
  const active = useRef(sessionId);
  const appliedPrompt = useRef<string>();
  const feed = useRef<HTMLDivElement>(null);
  const newestMessageId = messages.at(-1)?.id;

  useEffect(() => () => stream.current?.abort(), []);
  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight });
  }, [newestMessageId, partial]);
  useEffect(() => {
    if (pathname !== '/' || typeof state?.paperQuestion !== 'string' || locationKey === appliedPrompt.current) return;
    appliedPrompt.current = locationKey;
    pending.setText(state.paperQuestion);
    navigate(homePath(sessionId), { replace: true, state: null });
  }, [locationKey, navigate, pathname, pending, sessionId, state]);

  useEffect(() => {
    const id = sessionFrom(search);
    if (pathname === '/' && id !== active.current) {
      stream.current?.abort();
      setWorking(false);
      setUploading(false);
      chooseSession(id, false);
    }
  }, [pathname, search]);

  async function loadSessions(next = 1) {
    setHistoryError('');
    try {
      const response = await teachingAssistantApi.listSessions(next);
      setSessions(previous => next === 1 ? response.items : [...previous, ...response.items]);
      setTotal(response.total);
      setPage(next);
    } catch (failure) {
      setHistoryError(errorText(failure));
    }
  }

  function chooseSession(id?: string, updateUrl = true) {
    if (id === active.current) {
      setDrawer(false);
      if (updateUrl) navigate(homePath(id), { replace: true });
      return;
    }
    active.current = id;
    setSessionId(id);
    setMessages([]);
    setPartial('');
    setError('');
    setFailedQuestion('');
    setDrawer(false);
    if (updateUrl) navigate(homePath(id), { replace: true });
  }

  async function send(value: string) {
    const message = value.trim();
    if (!message || working || loadingHistory) return;
    pending.setText(message);
    const request = new AbortController();
    stream.current = request;
    setWorking(true);
    setError('');
    setFailedQuestion('');
    let id = sessionId;
    const localId = crypto.randomUUID();
    let requestId: string | undefined;
    function accept(reply: Pick<ChatResponse, 'message_id' | 'user_message_id' | 'content' | 'sources'>) {
      if (!id || active.current !== id || request.signal.aborted) return;
      const conversationId = id;
      setMessages(previous => [
        ...previous.filter(item => item.id !== reply.message_id && item.id !== reply.user_message_id)
          .map(item => item.id === localId && reply.user_message_id ? { ...item, id: reply.user_message_id } : item),
        { id: reply.message_id, conversation_id: conversationId, role: 'assistant', content: reply.content, message_type: 'text',
          sources: reply.sources, created_at: new Date().toISOString() },
      ]);
      pending.clear(conversationId);
      void loadSessions();
    }
    try {
      setUploading(pending.files.length > 0);
      const attached = await pending.upload(id, request.signal);
      setUploading(false);
      if (!id) {
        id = (await teachingAssistantApi.createSession()).id;
        if (request.signal.aborted) return;
        pending.begin(id, message);
        active.current = id;
        setSessionId(id);
        navigate(homePath(id), { replace: true });
      }
      const conversationId = id;
      setMessages(previous => [...previous, { id: localId, conversation_id: conversationId, role: 'user', content: message, message_type: 'text', attachments: attached, sources: null, created_at: new Date().toISOString() }]);
      const parameters = { conversation_id: conversationId, message, attachment_ids: attached.map(item => item.attachment_id) };
      requestId = pending.requestId(conversationId, parameters);
      const response = await teachingAssistantApi.chatStream({ ...parameters, request_id: requestId }, request.signal);
      let content = '';
      let sources: SourceItem[] = [];
      let finished = false;
      for await (const frame of readEventStream(response)) {
        if (frame.data === '[DONE]') continue;
        const payload = JSON.parse(frame.data);
        if (frame.name === 'chunk') {
          content += payload.text ?? payload.content ?? '';
          if (active.current === conversationId) setPartial(content);
        } else if (frame.name === 'sources') {
          sources = Array.isArray(payload) ? payload : payload.sources ?? [];
        } else if (frame.name === 'done') {
          finished = true;
          accept({ message_id: String(payload.message_id ?? crypto.randomUUID()), user_message_id: payload.user_message_id, content, sources });
          break;
        } else if (frame.name === 'error') {
          throw new Error(payload.message || '问答失败');
        }
      }
      if (!finished) throw new Error('连接已中断，请重试');
    } catch (failure) {
      const recovered = !request.signal.aborted && id && requestId ? await recoverChatReply(id, requestId, request.signal) : undefined;
      if (recovered) {
        accept(recovered);
        return;
      }
      if (!request.signal.aborted && active.current === id) {
        setError(errorText(failure));
        setFailedQuestion(requestId ? message : '');
        setMessages(previous => previous.filter(item => item.id !== localId));
      }
    } finally {
      if (!request.signal.aborted) {
        setWorking(false);
        setUploading(false);
        setPartial('');
      }
    }
  }

  function selectFiles(event: FormEvent<HTMLInputElement>) {
    setError(pending.add(Array.from(event.currentTarget.files ?? [])));
    setAttachments(false);
  }

  function editFailedQuestion() {
    if (!failedQuestion) return;
    setFailedQuestion('');
    setError('');
  }

  if (settings) return <Settings back={() => { setDrawer(true); navigate(homePath(sessionId)); }} />;
  if (pathname.startsWith('/sources/')) return <main className="page subpage">
    <Routes><Route path="sources/:examId/:questionNumber?" element={<ExamKnowledge back={homePath(sessionId)} />} /></Routes>
  </main>;

  return <main className="home page">
    <header className="home-heading"><button className="square" aria-label="打开聊天记录" onClick={() => { setDrawer(true); void loadSessions(); }}><Icon name="sidebar" size={22} /></button></header>
    <div className="feed" ref={feed} aria-busy={working || loadingHistory}>
      {!sessionId && !messages.length && !working && (examKnowledgeAvailable === false ? <ExamKnowledgeEmpty /> :
        examKnowledgeAvailable && <div className="prompts"><h2>推荐问题</h2>{initialQuestions.map((item, index) => <button key={item} onClick={() => void send(item)}><Icon name={index ? 'bubble' : 'chart'} /><span>{item}</span><Icon name="right" size={17} /></button>)}</div>)}
      {loadingHistory && <p className="notice">正在加载…</p>}
      {(history.beforeId || history.failure === 'initial') && <button className="plain chat-history-more"
        disabled={history.more} onClick={history.failure === 'initial' ? history.reload : history.loadOlder}>
        {history.more ? '正在加载…' : history.failure ? '加载失败，重试' : '查看更早消息'}
      </button>}
      {messages.map(item => item.role === 'user' ? <div className="question" key={item.id}>{item.content}
        {item.attachments?.map(file => <ChatAttachmentButton key={file.attachment_id} id={file.attachment_id} name={file.file_name} />)}
      </div> : <AssistantReply key={item.id} message={item} sessionId={sessionId} />)}
      {working && <div className="reply"><Icon name="sparkle" size={18} /><div className="reply-card"><ReactMarkdown remarkPlugins={[remarkGfm]}>{partial || (uploading ? '正在上传并解析附件…' : '正在检索…')}</ReactMarkdown></div></div>}
      {failedQuestion && <div className="question chat-failed-question">{failedQuestion}</div>}
      {error && (failedQuestion ? <div className="chat-failure">
        <p className="notice warning" role="alert"><Icon name="warning" size={18} />{error}</p>
        <button className="secondary" onClick={() => void send(question || failedQuestion)}>重试回答</button>
      </div> : <p className="notice failure" role="alert">{error}</p>)}
    </div>
    <div className="compose">
      {!failedQuestion && !!pending.files.length && <div className="file-list">{pending.files.map(file => <button type="button" className="secondary" key={file.id} disabled={working} onClick={() => pending.remove(file.id)} aria-label={`移除 ${file.name}`}><Icon name={file.type.startsWith('image/') ? 'image' : 'files'} size={21} /><span>{file.name}</span><Icon name="close" size={19} /></button>)}</div>}
      <form className="composer" onSubmit={event => { event.preventDefault(); void send(question); }}>
        <input aria-label="输入问题" placeholder="输入问题…" value={working || failedQuestion ? '' : question} disabled={working} onFocus={editFailedQuestion} onChange={event => pending.setText(event.target.value)} />
        <button type="button" className="plain" aria-label="添加文件或图片" disabled={working} onClick={() => { editFailedQuestion(); setAttachments(true); }}><Icon name="plus" size={22} /></button>
        <button className="send" aria-label="发送" disabled={working || loadingHistory || Boolean(failedQuestion) || !question.trim()}><Icon name="up" size={16} /></button>
      </form>
    </div>
    {attachments && <Sheet title="添加附件" variant="attachments" close={() => setAttachments(false)}><div className="attach-actions">
      <label><Icon name="files" size={22} /><span>上传文件</span><input type="file" accept={CHAT_FILE_ACCEPT} multiple onChange={selectFiles} /><Icon name="right" size={19} /></label>
      <label><Icon name="image" size={22} /><span>上传图片</span><input type="file" accept={CHAT_IMAGE_ACCEPT} multiple onChange={selectFiles} /><Icon name="right" size={19} /></label>
    </div></Sheet>}
    {drawer && <div className="overlay"><button className="backdrop" aria-label="关闭聊天记录" onClick={() => setDrawer(false)} /><aside className="drawer" aria-label="聊天记录">
      <header><h2>聊天记录</h2><button className="square" onClick={() => setDrawer(false)} aria-label="关闭侧栏"><Icon name="sidebar" /></button></header>
      <button className="primary wide drawer-new" onClick={() => chooseSession()} disabled={working}><Icon name="edit" />新对话</button>
      <div className="conversation-list">
        {sessions.map(session => {
          const selected = session.id === sessionId;
          const updated = session.updated_at || session.created_at;
          const time = sessionDate(updated);
          return <button key={session.id} className={selected ? 'selected' : ''} aria-current={selected || undefined}
            disabled={working} onClick={() => chooseSession(session.id)}>
            <Icon name="bubble" size={18} />
            <span className="conversation-copy"><strong>{session.title || '新对话'}</strong>
              {time && <time dateTime={updated}>{time}</time>}
            </span>
            {selected && <Icon name="check" size={18} />}
          </button>;
        })}
        {historyError && <button onClick={() => void loadSessions()}>加载失败，重试</button>}
        {sessions.length < total && <button onClick={() => void loadSessions(page + 1)}>加载更多</button>}
      </div>
      <footer><button className="secondary wide drawer-settings" onClick={() => navigate('/settings')}><Icon name="settings" /><span>问答助手设置</span><Icon name="right" size={18} /></button></footer>
    </aside></div>}
  </main>;
}

function Settings({ back }: { back: () => void }) {
  const [items, setItems] = useState<SkillItem[]>();
  const [panel, setPanel] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [revision, setRevision] = useState(0);
  const upload = useQASkillUpload();
  useEffect(() => {
    let current = true;
    setError('');
    void teachingAssistantApi.listSkills('qa').then(result => { if (current) setItems(result.items); }).catch(failure => { if (current) setError(errorText(failure)); });
    return () => { current = false; };
  }, [revision]);

  function close() {
    if (upload.busy) return;
    upload.select();
    setPanel(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const saved = await upload.submit();
    if (!saved) return;
    setItems(previous => [saved, ...(previous ?? []).filter(item => item.id !== saved.id)]);
    setFeedback('Skill 已上传');
    setPanel(false);
    setRevision(count => count + 1);
  }

  return <main className="page subpage settings">
    <header className="heading"><button className="round" aria-label="返回" disabled={upload.busy} onClick={back}><Icon name="left" size={22} /></button><h1>问答助手设置</h1></header>
    <h2>技能</h2>
    {error && <div className="notice failure" role="alert">{error} <button className="plain" onClick={() => setRevision(count => count + 1)}>重试</button></div>}
    {items?.length ? <div className="settings-list">{items.map(item => <div className="list-card" key={item.id}>
      <Icon name="skill" size={19} /><div><strong>{item.name}</strong><small>{item.file_name}</small></div>
    </div>)}</div> : items && !error ? <div className="settings-empty"><span><Icon name="skill" size={24} /></span><p>暂无 Skill</p></div>
      : !error && <p className="notice">正在加载…</p>}
    {feedback && <p className="settings-feedback" role="status">{feedback}</p>}
    <button className="primary wide" onClick={() => { setFeedback(''); setPanel(true); }}>上传 Skill</button>
    {panel && <Sheet title="上传 Skill" variant="skill" close={close}>
      <form onSubmit={submit}>
        <label className="skill-file" data-invalid={Boolean(upload.error)}>
          <Icon name="skill" size={20} /><span>{upload.file?.name || '选择文件'}</span><b>{upload.file ? '更换' : '浏览'}</b>
          <input type="file" aria-label="选择 Skill 文件" accept={SKILL_FILE_ACCEPT} disabled={upload.busy}
            onChange={event => { upload.select(event.currentTarget.files?.[0]); event.currentTarget.value = ''; }} />
        </label>
        {upload.error ? <p className="skill-file-error" role="alert">{upload.error}</p> : !upload.file && <p>支持 .md 或 .markdown</p>}
        <div className="actions"><button type="button" className="secondary" disabled={upload.busy} onClick={close}>取消</button>
          <button className="primary" disabled={!upload.file || Boolean(upload.invalid) || upload.busy}>{upload.busy ? '上传中…' : '上传'}</button></div>
      </form>
    </Sheet>}
  </main>;
}
