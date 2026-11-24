// 课堂播放页 — 全屏 iframe 嵌入 + postMessage 双向通信 + 互动工具栏（投票/答题/弹幕）
import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { teacherApi } from '../../api/teacher';
import client from '../../api/client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/* 通用弹窗组件 */
function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div style={s.overlay}>
      <div style={s.modalCard}>
        <div style={s.modalHdr}>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: '#333' }}>{title}</h3>
          <button onClick={onClose} style={s.closeBtn}>&times;</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function Presenter() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const sinceIdRef = useRef('');

  const [ppt, setPpt] = useState<any>(null);
  const [session, setSession] = useState<any>(null);
  const [htmlContent, setHtmlContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [loadingDetail, setLoadingDetail] = useState('正在初始化...');
  const [retryCount, setRetryCount] = useState(0); // 渲染重试计数
  const [currentPage, setCurrentPage] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [danmakuList, setDanmakuList] = useState<any[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [danmakuInput, setDanmakuInput] = useState('');

  /* 投票 */
  const [voteResults, setVoteResults] = useState<any>(null);
  const [showVoteModal, setShowVoteModal] = useState(false);
  const [voteQ, setVoteQ] = useState('');
  const [voteOpts, setVoteOpts] = useState(['', '']);
  const [currentVoteId, setCurrentVoteId] = useState<string | null>(null);

  /* 答题 */
  const [quizResults, setQuizResults] = useState<any>(null);
  const [showQuizModal, setShowQuizModal] = useState(false);
  const [quizQ, setQuizQ] = useState('');
  const [quizOpts, setQuizOpts] = useState(['', '', '', '']);
  const [quizAns, setQuizAns] = useState(0);
  const [currentQuizId, setCurrentQuizId] = useState<string | null>(null);
  /* 多题支持 */
  const [quizQuestions, setQuizQuestions] = useState<any[]>([]);
  const [currentQuizIndex, setCurrentQuizIndex] = useState(0);

  /* AI 问答 */
  const [showAIChat, setShowAIChat] = useState(false);
  const [aiMessages, setAiMessages] = useState<{ role: string; content: string }[]>([]);
  const [aiInput, setAiInput] = useState('');
  const [aiSending, setAiSending] = useState(false);

  /* 加载课堂会话和 PPT（get_ppt 已支持自动渲染空 html_content） */
  useEffect(() => {
    if (!sessionId) { setLoading(false); return; }
    console.log('[Presenter] 开始加载课堂 sessionId=', sessionId);
    setLoadingDetail('正在获取课堂信息...');
    (async () => {
      try {
        const report = await teacherApi.ppt.getReport(sessionId);
        console.log('[Presenter] getReport 返回:', report);
        const sess = report?.session;
        setSession(sess);
        console.log('[Presenter] session=', sess);
        if (!sess?.ppt_id) {
          console.warn('[Presenter] session 无 ppt_id');
          setLoadError('课堂数据异常：未关联 PPT');
          setLoading(false);
          return;
        }
        console.log('[Presenter] 获取 PPT ppt_id=', sess.ppt_id);
        setLoadingDetail('正在加载PPT内容...');
        const d = await teacherApi.ppt.get(sess.ppt_id);
        console.log('[Presenter] get ppt 返回:', {
          id: d?.id,
          title: d?.title,
          htmlContentLen: d?.html_content?.length,
          pagesCount: Array.isArray(d?.pages_json) ? d.pages_json.length : 'N/A',
          themeName: d?.theme_name,
        });
        setPpt(d);
        if (d?.html_content) {
          const origin = window.location.origin;
          // 注：{backend_base_script} 占位符本身在 <script> 标签内，
          // 只需注入 JS 代码，不能嵌套 <script> 标签，否则浏览器会提前闭合外层 script
          const backendBaseCode = `window.BACKEND_BASE='${origin}';`;
          const backendBaseScript = `<script>window.BACKEND_BASE='${origin}';<\/script>`;
          let enhancedHtml = d.html_content;
          if (enhancedHtml.includes('{backend_base_script}')) {
            enhancedHtml = enhancedHtml.replace('{backend_base_script}', backendBaseCode);
          } else {
            // 容错：注入到 </head> 之前（这里不在 <script> 内，所以用完整 script 标签）
            enhancedHtml = enhancedHtml.replace('</head>', backendBaseScript + '\n</head>');
          }
          console.log('[Presenter] 设置 htmlContent 长度=', enhancedHtml.length);
          setHtmlContent(enhancedHtml);
        } else {
          // html_content 为空，尝试强制触发后端渲染
          console.warn('[Presenter] html_content 为空，尝试强制渲染...');
          setLoadingDetail('PPT内容为空，正在重新生成...');
          try {
            // 调用 export 端点触发渲染（export 会强制重新生成 html_content）
            const exported = await teacherApi.ppt.export(sess.ppt_id);
            if (exported?.html_content) {
              const origin = window.location.origin;
              const backendBaseCode = `window.BACKEND_BASE='${origin}';`;
              const backendBaseScript = `<script>window.BACKEND_BASE='${origin}';<\/script>`;
              let enhancedHtml = exported.html_content;
              if (enhancedHtml.includes('{backend_base_script}')) {
                enhancedHtml = enhancedHtml.replace('{backend_base_script}', backendBaseCode);
              } else {
                enhancedHtml = enhancedHtml.replace('</head>', backendBaseScript + '\n</head>');
              }
              console.log('[Presenter] export 返回 htmlContent 长度=', enhancedHtml.length);
              setHtmlContent(enhancedHtml);
              // 重新获取 PPT 详情以更新缓存
              teacherApi.ppt.get(sess.ppt_id).then(updated => setPpt(updated)).catch(() => {});
            } else {
              setLoadError('PPT 内容渲染失败，页面数据可能不完整。请返回编辑页检查页面内容。');
            }
          } catch (exportErr: any) {
            console.error('[Presenter] 强制渲染也失败:', exportErr);
            setLoadError('PPT 渲染失败: ' + (exportErr.message || '未知错误') + '。请返回编辑页重新生成PPT。');
          }
        }
      } catch (e: any) {
        console.error('[Presenter] 加载失败:', e);
        setLoadError('加载失败: ' + (e.message || '未知错误'));
      } finally {
        setLoading(false);
        console.log('[Presenter] 加载完成，loading 设为 false');
      }
    })();
  }, [sessionId]);

  /* 弹幕轮询 */
  useEffect(() => {
    if (!sessionId || !session) return;
    const t = setInterval(async () => {
      try {
        const res = await teacherApi.ppt.getDanmaku(sessionId, { since_id: sinceIdRef.current, limit: 20 });
        if (res.items?.length) {
          setDanmakuList(prev => [...prev, ...res.items].slice(-100));
          sinceIdRef.current = res.items[res.items.length - 1].id;
        }
      } catch { /* ignore */ }
    }, 2000);
    return () => clearInterval(t);
  }, [sessionId, session]);

  /* 答题结果轮询（每 3 秒刷新） */
  useEffect(() => {
    if (!sessionId || menuOpen !== 'quiz' || !currentQuizId) return;
    const t = setInterval(async () => {
      try {
        const r = await teacherApi.ppt.getQuizResults(sessionId, currentQuizId);
        if (r) setQuizResults(r);
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(t);
  }, [sessionId, menuOpen, currentQuizId]);

  /* 投票结果轮询（每 3 秒刷新） */
  useEffect(() => {
    if (!sessionId || menuOpen !== 'vote' || !currentVoteId) return;
    const t = setInterval(async () => {
      try {
        const r = await teacherApi.ppt.getVoteResults(sessionId, currentVoteId);
        if (r) setVoteResults(r);
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(t);
  }, [sessionId, menuOpen, currentVoteId]);

  /* postMessage 通信 */
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      const d = e.data || {};
      if (d.type === 'slide-ready') setTotalPages(d.total || 0);
      else if (d.type === 'slide-change') {
        setCurrentPage(d.index || 0);
        if (sessionId) teacherApi.ppt.syncPage(sessionId, d.index).catch(() => {});
      } else if (d.type === 'answer') {
        recordSlideAnswer(d.qIndex, d.selected, d.correct);
      } else if (d.type === 'request-tts') {
        // TTS: generate audio from iframe prompt
        generateSlideAudio(d.text).then(url => {
          if (url) postToIframe({ type: 'tts-audio', url });
        });
      } else if (d.type === 'request-image') {
        // Image: generate illustration from iframe prompt
        generateSlideImage(d.prompt).then(url => {
          if (url) postToIframe({ type: 'image-generated', url });
        });
      } else if (d.type === 'request-ai-chat') {
        // AI 提问：打开 AI 问答弹窗并预填问题
        setShowAIChat(true);
        setAiInput(d.question || '');
        if (d.question) {
          sendAIMessage(d.question);
        }
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [sessionId, currentPage]);

  /* AI 问答 */
  const sendAIMessage = async (text: string) => {
    if (!text.trim() || aiSending) return;
    setAiSending(true);
    const userMsg = { role: 'user', content: text.trim() };
    setAiMessages(prev => [...prev, userMsg]);
    setAiInput('');
    try {
      // 添加 PPT 当前页上下文（含完整内容）
      let slideContext = '';
      if (ppt?.pages_json?.[currentPage]) {
        const page = ppt.pages_json[currentPage];
        const contentStr = page.content ? JSON.stringify(page.content, null, 0).slice(0, 2000) : '';
        slideContext = `【PPT上下文】课程名称：${ppt.title || ''}，科目：${ppt.subject || '英语'}，年级：${ppt.grade || ''}，主题：${ppt.theme_name || ''}。当前页标题："${page.title}"，类型：${page.type}，内容：${contentStr || '无'}`;
      }
      const chatHistory = aiMessages
        .filter(m => m.role !== 'system')
        .slice(-10)
        .concat([userMsg]);
      const payload = slideContext
        ? { messages: [{ role: 'system', content: slideContext }, ...chatHistory] }
        : { messages: chatHistory };
      const res = await client.post('/ai/chat', payload);
      const reply = res.data?.data?.content || '抱歉，我没有理解你的问题，请换个方式再问一遍。';
      setAiMessages(prev => [...prev, { role: 'assistant', content: reply }]);
    } catch (e: any) {
      setAiMessages(prev => [...prev, { role: 'assistant', content: '抱歉，回复生成失败，请稍后重试。' + (e.message ? '(' + e.message + ')' : '') }]);
    } finally {
      setAiSending(false);
    }
  };

  const handleAISend = () => {
    if (aiInput.trim() && !aiSending) sendAIMessage(aiInput);
  };

  const handleAIKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAISend(); }
  };

  const handleOpenAIChat = () => {
    setShowAIChat(true);
    if (aiMessages.length === 0) {
      const currentTitle = ppt?.pages_json?.[currentPage]?.title || '';
      setAiMessages([
        { role: 'assistant', content: `你好！我是 AI 学习助手小e${currentTitle ? '，当前在「' + currentTitle + '」页' : ''}，有什么可以帮你的吗？` }
      ]);
    }
  };

  const generateSlideAudio = async (text: string): Promise<string | null> => {
    try {
      const res = await teacherApi.ppt.tts({ text });
      // 将相对 URL 转换为绝对 URL，确保 srcdoc iframe 能正确 fetch
      const absoluteUrl = new URL(res.url, window.location.origin).toString();
      return absoluteUrl;
    } catch (e: any) {
      console.error('TTS failed:', e);
      return null;
    }
  };

  const generateSlideImage = async (prompt: string): Promise<string | null> => {
    try {
      const res = await teacherApi.ppt.generateImage({ prompt });
      return res.url;
    } catch (e: any) {
      console.error('Image gen failed:', e);
      return null;
    }
  };

  const postToIframe = useCallback((data: any) => {
    iframeRef.current?.contentWindow?.postMessage(data, '*');
  }, []);

  const goToPage = useCallback((idx: number) => {
    if (totalPages === 0) return;
    postToIframe({ type: 'go-to-page', index: Math.max(0, Math.min(idx, totalPages - 1)) });
  }, [postToIframe, totalPages]);

  const prevPage = useCallback(() => postToIframe({ type: 'prev-slide' }), [postToIframe]);
  const nextPage = useCallback(() => postToIframe({ type: 'next-slide' }), [postToIframe]);

  const recordSlideAnswer = async (qIdx: number, selected: number, correct: boolean) => {
    if (!sessionId) return;
    try {
      await teacherApi.ppt.recordSlideAnswer(sessionId, { page_index: currentPage, question_index: qIdx, selected, correct });
    } catch { /* ignore */ }
  };

  const toggleFullscreen = () => { postToIframe({ type: 'toggle-fullscreen' }); };

  /* 投票 */
  const handleCreateVote = async () => {
    if (!sessionId || !voteQ.trim() || voteOpts.filter(o => o.trim()).length < 2) return alert('请填写问题和至少两个选项');
    try {
      const v = await teacherApi.ppt.createVote(sessionId, { question: voteQ, options: voteOpts.filter(o => o.trim()) });
      setShowVoteModal(false); setVoteQ(''); setVoteOpts(['', '']);
      setCurrentVoteId(v.id);
      const r = await teacherApi.ppt.getVoteResults(sessionId, v.id);
      if (r) { setVoteResults(r); setMenuOpen('vote'); }
    } catch (e: any) { alert('创建投票失败: ' + e.message); }
  };

  /* 答题 */
  /* 从当前 PPT 页面的 practice 类型自动提取所有题目 */
  const autoFillQuizFromPage = useCallback(() => {
    if (!ppt?.pages_json || !Array.isArray(ppt.pages_json) || currentPage >= ppt.pages_json.length) return;
    const page = ppt.pages_json[currentPage];
    if (page?.type !== 'practice') return;
    const questions = page.content?.questions;
    if (!questions || questions.length === 0) return;
    // 保存所有题目，重置索引
    setQuizQuestions(questions);
    setCurrentQuizIndex(0);
    // 加载第一个题目
    loadQuestionByIndex(questions, 0);
  }, [ppt, currentPage]);

  /* 按索引加载题目内容到编辑区 */
  const loadQuestionByIndex = (questions: any[], index: number) => {
    const q = questions[index];
    if (!q) return;
    setQuizQ(q.stem || '');
    const opts = q.options || [];
    // 填充最多 4 个选项
    const filled = [...opts, '', '', '', ''].slice(0, 4);
    setQuizOpts(filled as string[]);
    setQuizAns(typeof q.answer === 'number' ? q.answer : 0);
  };

  /* 切换题目 */
  const handleQuizQuestionChange = (index: number) => {
    setCurrentQuizIndex(index);
    loadQuestionByIndex(quizQuestions, index);
  };

  const handleCreateQuiz = async () => {
    if (!sessionId || !quizQ.trim() || quizOpts.filter(o => o.trim()).length < 2) return alert('请填写问题和选项');
    try {
      const q = await teacherApi.ppt.createQuiz(sessionId, { question: quizQ, options: quizOpts.filter(o => o.trim()), correct_answer: quizAns });
      setShowQuizModal(false); setQuizQ(''); setQuizOpts(['', '', '', '']); setQuizAns(0);
      setCurrentQuizId(q.id);
      const r = await teacherApi.ppt.getQuizResults(sessionId, q.id);
      if (r) { setQuizResults(r); setMenuOpen('quiz'); }
    } catch (e: any) { alert('创建答题失败: ' + e.message); }
  };

  const handleSendDanmaku = () => {
    if (!danmakuInput.trim() || !sessionId) return;
    const content = danmakuInput;
    setDanmakuInput('');
    // 本地先显示（即时反馈）
    setDanmakuList(p => [...p, { id: `dan_${Date.now()}`, student_name: '教师', content, timestamp: new Date().toISOString() }].slice(-100));
    // 异步写入后端，学生端轮询方能获取
    teacherApi.ppt.sendDanmaku(sessionId, { content, student_name: '教师' })
      .catch(e => console.error('发送弹幕失败', e));
  };

  const handlePause = async () => {
    if (!sessionId) return;
    try {
      if (isPaused) { await teacherApi.ppt.resumeSession(sessionId); setIsPaused(false); }
      else { await teacherApi.ppt.pauseSession(sessionId); setIsPaused(true); }
    } catch { /* ignore */ }
  };

  const handleEndClass = async () => {
    if (!sessionId || !window.confirm('确定结束本次课堂？')) return;
    try { await teacherApi.ppt.endClassroom(sessionId); navigate(`/ppt/report/${sessionId}`); }
    catch (e: any) { alert('结束失败: ' + e.message); }
  };

  const closeVote = async (vid: string) => {
    if (!sessionId) return;
    try { await teacherApi.ppt.closeVote(sessionId, vid); setMenuOpen(null); setCurrentVoteId(null); }
    catch { /* ignore */ }
  };

  /* 键盘快捷键 */
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); nextPage(); }
      if (e.key === 'ArrowLeft') { e.preventDefault(); prevPage(); }
      if (e.key === 'f' || e.key === 'F') { toggleFullscreen(); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [nextPage, prevPage]);

  /* 全局动画（加载/错误状态也需要 spinner 动画） */
  const globalKeyframes = (
    <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
  );
  if (loading) return <div style={s.ctr}>{globalKeyframes}<div style={s.spnr} /><p style={{ marginTop: 16, color: '#aaa' }}>{loadingDetail}</p></div>;
  if (!session) return <div style={s.ctr}><p style={{ color: '#ff9800', fontSize: 16 }}>课堂不存在</p><p style={{ color: '#888', fontSize: 13, marginTop: 8 }}>该课堂会话可能已过期或已被删除</p></div>;
  if (loadError) return <div style={s.ctr}><p style={{ color: '#e53935', fontSize: 16 }}>{loadError}</p><div style={{ marginTop: 16, display: 'flex', gap: 12 }}><button onClick={() => navigate(-1)} style={{ padding: '8px 20px', background: '#5B9E6F', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>返回上一页</button><button onClick={() => window.location.reload()} style={{ padding: '8px 20px', background: '#666', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>刷新重试</button></div></div>;
  if (!htmlContent) return <div style={s.ctr}><p style={{ color: '#ff9800', fontSize: 16 }}>暂无 PPT 内容</p><p style={{ color: '#888', fontSize: 13, marginTop: 8 }}>PPT 数据已加载但内容为空，请返回重新生成</p><div style={{ marginTop: 16 }}><button onClick={() => navigate(-1)} style={{ padding: '8px 20px', background: '#5B9E6F', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>返回编辑页</button></div></div>;

  return (
    <div style={s.wrap}>
      {/* 全局 keyframe 动画 */}
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes dotPulse { 0%,100% { opacity: 0.3; } 50% { opacity: 1; } }`}</style>

      {/* 顶栏 */}
      <div style={s.hdr}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontWeight: 700, fontSize: 15 }}>{session.title || '课堂'}</span>
          <span style={{ fontSize: 13, color: '#888' }}>{totalPages > 0 ? `第 ${currentPage + 1}/${totalPages} 页` : ''}</span>
          {isPaused && <span style={{ color: '#ff9800', fontSize: 13 }}>已暂停</span>}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select value={currentPage} onChange={e => goToPage(Number(e.target.value))} style={s.sel}>
            {Array.from({ length: totalPages }, (_, i) => <option key={i} value={i}>第 {i + 1} 页</option>)}
          </select>
          <button onClick={handlePause} style={{ ...s.tBtn, background: isPaused ? '#ff9800' : 'rgba(255,255,255,0.1)' }}>
            {isPaused ? '恢复' : '暂停'}
          </button>
          <button onClick={toggleFullscreen} style={s.tBtn}>全屏</button>
          <button onClick={handleEndClass} style={{ ...s.tBtn, background: '#e53935', fontWeight: 600 }}>结束</button>
        </div>
      </div>

      {/* iframe 区域 */}
      <div style={s.iframeWrap}>
        <div style={s.iframeBox}>
          {htmlContent ? (
            <iframe ref={iframeRef} srcDoc={htmlContent} title="PPT" style={s.iframe}
              sandbox="allow-scripts allow-same-origin"
              onError={() => console.error('[Presenter] iframe 加载失败')}
              onLoad={() => console.log('[Presenter] iframe 加载完成')} />
          ) : <div style={{ color: '#999' }}>暂无幻灯片内容</div>}
        </div>
        {/* 弹幕层 */}
        {menuOpen !== 'vote' && menuOpen !== 'quiz' && danmakuList.length > 0 && (
          <div style={s.danLayer}>
            {danmakuList.slice(-15).map((d: any, i: number) => (
              <div key={d.id || i} style={s.danItem}>
                {d.student_name && <span style={{ color: '#5B9E6F', fontWeight: 600 }}>{d.student_name}: </span>}
                {d.content}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 底部工具栏 */}
      <div style={s.tBar}>
        <button onClick={prevPage} disabled={currentPage <= 0} style={s.nBtn}>上一页</button>
        <button onClick={nextPage} disabled={currentPage >= totalPages - 1} style={s.nBtn}>下一页</button>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 3, marginRight: 12 }}>
          {Array.from({ length: Math.min(totalPages, 30) }, (_, i) => (
            <div key={i} onClick={() => goToPage(i)} style={{
              width: 8, height: 8, borderRadius: '50%', cursor: 'pointer',
              background: i === currentPage ? '#5B9E6F' : '#555',
            }} />
          ))}
        </div>
        <button onClick={() => { setMenuOpen(menuOpen === 'vote' ? null : 'vote'); setShowVoteModal(true); setVoteResults(null); }}
          style={{ ...s.tBtn, background: menuOpen === 'vote' ? '#ff9800' : 'rgba(255,255,255,0.1)' }}>投票</button>
        <button onClick={() => { setMenuOpen(menuOpen === 'quiz' ? null : 'quiz'); setShowQuizModal(true); setQuizResults(null); autoFillQuizFromPage(); }}
          style={{ ...s.tBtn, background: menuOpen === 'quiz' ? '#ff9800' : 'rgba(255,255,255,0.1)' }}>答题</button>
        <button onClick={handleOpenAIChat}
          style={{ ...s.tBtn, background: showAIChat ? '#7c4dff' : 'rgba(255,255,255,0.1)' }}>AI 提问</button>
        {menuOpen !== 'vote' && menuOpen !== 'quiz' && !showAIChat && (
          <div style={{ display: 'flex', gap: 4, background: 'rgba(255,255,255,0.1)', borderRadius: 6, padding: '2px 4px' }}>
            <input value={danmakuInput} onChange={e => setDanmakuInput(e.target.value)} placeholder="发送弹幕..."
              onKeyDown={e => e.key === 'Enter' && handleSendDanmaku()} style={s.danIn} />
            <button onClick={handleSendDanmaku} style={s.sndBtn}>发送</button>
          </div>
        )}
      </div>

      {/* 投票弹窗 */}
      {showVoteModal && (
        <Modal title="创建投票" onClose={() => setShowVoteModal(false)}>
          <input value={voteQ} onChange={e => setVoteQ(e.target.value)} placeholder="投票问题" style={s.inp} />
          {voteOpts.map((o, i) => (
            <div key={i} style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
              <span style={{ lineHeight: '36px', width: 20 }}>{String.fromCharCode(65 + i)}.</span>
              <input value={o} onChange={e => { const t = [...voteOpts]; t[i] = e.target.value; setVoteOpts(t); }} placeholder={`选项 ${i + 1}`} style={s.inp} />
            </div>
          ))}
          {voteOpts.length < 6 && (
            <button onClick={() => setVoteOpts([...voteOpts, ''])} style={s.addBtn}>+ 添加选项</button>
          )}
          <button onClick={handleCreateVote} style={s.crtBtn('#ff9800')}>发布投票</button>
        </Modal>
      )}

      {/* 答题弹窗 */}
      {showQuizModal && (
        <Modal title={`创建课堂答题 · 第 ${currentPage + 1} 页`} onClose={() => setShowQuizModal(false)}>
          {ppt?.pages_json?.[currentPage]?.type !== 'practice' && (
            <div style={{ fontSize: 12, color: '#888', marginBottom: 8, fontStyle: 'italic' }}>
              当前页不是练习题页，已清空题目。
            </div>
          )}
          {/* 多题下拉选择器 */}
          {quizQuestions.length > 1 && (
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: '#666', display: 'block', marginBottom: 4 }}>选择题目：</label>
              <select
                value={currentQuizIndex}
                onChange={e => handleQuizQuestionChange(Number(e.target.value))}
                style={{ ...s.sel, width: '100%', color: '#333', background: '#f5f5f5', border: '1px solid #ddd', borderRadius: 6, padding: '6px 8px', fontSize: 13, outline: 'none', cursor: 'pointer' }}
              >
                {quizQuestions.map((_, i) => (
                  <option key={i} value={i}>题目 {i + 1}</option>
                ))}
              </select>
            </div>
          )}
          <input value={quizQ} onChange={e => setQuizQ(e.target.value)} placeholder="题目（已自动识别当前页练习）" style={s.inp} />
          {quizOpts.map((o, i) => (
            <div key={i} style={{ display: 'flex', gap: 4, marginBottom: 4, alignItems: 'center' }}>
              <input type="radio" name="quizAns" checked={quizAns === i} onChange={() => setQuizAns(i)} />
              <span style={{ width: 16 }}>{String.fromCharCode(65 + i)}.</span>
              <input value={o} onChange={e => { const t = [...quizOpts]; t[i] = e.target.value; setQuizOpts(t); }} placeholder={`选项 ${i + 1}`} style={s.inp} />
              {quizAns === i && <span style={{ fontSize: 11, color: '#2d7d46' }}>✓ 正确答案</span>}
            </div>
          ))}
          <button onClick={handleCreateQuiz} style={s.crtBtn('#1565c0')}>
            {quizQuestions.length > 1 ? `发布题目 ${currentQuizIndex + 1} 答题` : '发布答题'}
          </button>
        </Modal>
      )}

      {/* 投票结果面板 */}
      {menuOpen === 'vote' && voteResults && !showVoteModal && (
        <Panel>
          <div style={{ fontWeight: 700, marginBottom: 12, fontSize: 15 }}>投票: {voteResults.question}</div>
          {voteResults.options?.map((opt: any, i: number) => {
            const total = voteResults.options.reduce((s: number, o: any) => s + (o.count || 0), 0) || 1;
            const pct = Math.round(((opt.count || 0) / total) * 100);
            return (
              <div key={i} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 2 }}>
                  <span>{String.fromCharCode(65 + i)}. {opt.label}</span>
                  <span>{opt.count || 0} 票 ({pct}%)</span>
                </div>
                <div style={{ height: 6, background: '#eee', borderRadius: 3 }}>
                  <div style={{ width: `${pct}%`, height: '100%', background: '#ff9800', borderRadius: 3, transition: 'width 0.5s' }} />
                </div>
              </div>
            );
          })}
          <button onClick={() => closeVote(voteResults.id)} style={s.clsBtn}>关闭投票</button>
        </Panel>
      )}

      {/* 答题结果面板 */}
      {menuOpen === 'quiz' && quizResults && !showQuizModal && (
        <Panel>
          <div style={{ fontWeight: 700, marginBottom: 12, fontSize: 15 }}>答题: {quizResults.question}</div>
          <div style={{ marginBottom: 8, fontSize: 13, color: '#888' }}>
            共 {quizResults.total_answers} 人作答，正确率{' '}
            {quizResults.total_answers > 0 ? Math.round((quizResults.correct_count / quizResults.total_answers) * 100) : 0}%
          </div>
          {(quizResults.options || []).map((opt: string, i: number) => {
            const total = quizResults.total_answers || 1;
            const cnt = (quizResults.option_counts || [])[i] || 0;
            const pct = Math.round((cnt / total) * 100);
            return (
              <div key={i} style={{ marginBottom: 6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span>{String.fromCharCode(65 + i)}. {opt}</span>
                  <span>{cnt} 人 ({pct}%)</span>
                </div>
                <div style={{ height: 6, background: '#eee', borderRadius: 3 }}>
                  <div style={{ width: `${pct}%`, height: '100%', background: i === quizAns ? '#4caf50' : '#90caf9', borderRadius: 3 }} />
                </div>
              </div>
            );
          })}
          <button onClick={() => setMenuOpen(null)} style={s.clsBtn2}>关闭</button>
        </Panel>
      )}

      {/* AI 问答弹窗 */}
      {showAIChat && (
        <div style={s.aiChatOverlay} onClick={() => setShowAIChat(false)}>
          <div style={s.aiChatModal} onClick={e => e.stopPropagation()}>
            <div style={s.aiChatHeader}>
              <div>
                <span style={{ fontWeight: 700, fontSize: 15, color: '#333' }}>AI 问答</span>
                {ppt?.pages_json?.[currentPage] && (
                  <span style={{ fontSize: 12, color: '#888', marginLeft: 8 }}>
                    当前页: {ppt.pages_json[currentPage].title || ppt.pages_json[currentPage].type}
                  </span>
                )}
              </div>
              <button onClick={() => setShowAIChat(false)} style={s.closeBtn}>&times;</button>
            </div>
            <div style={s.aiChatBody}>
              {aiMessages.map((msg, i) => (
                <div key={i} style={{
                  display: 'flex',
                  marginBottom: 12,
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}>
                  {msg.role !== 'user' && (
                    <div style={s.aiAvatar}>AI</div>
                  )}
                  <div style={{
                    maxWidth: '75%',
                    padding: '10px 14px',
                    borderRadius: msg.role === 'user' ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
                    background: msg.role === 'user' ? '#5B9E6F' : '#f0f0f0',
                    color: msg.role === 'user' ? '#fff' : '#333',
                    fontSize: 14,
                    lineHeight: 1.6,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}>
                    {msg.role === 'user' ? msg.content : (
                      <ReactMarkdown children={msg.content}
                        remarkPlugins={[remarkGfm]}
                        components={{
                          table: ({ node, ...props }) => <table style={{ borderCollapse: 'collapse', width: '100%', margin: '8px 0', fontSize: 13 }} {...props} />,
                          th: ({ node, ...props }) => <th style={{ border: '1px solid #ccc', padding: '6px 10px', background: '#e8e8e8', textAlign: 'left' }} {...props} />,
                          td: ({ node, ...props }) => <td style={{ border: '1px solid #ccc', padding: '6px 10px' }} {...props} />,
                          code: ({ node, className, children, ...props }: any) => {
                            const isInline = !className;
                            return isInline
                              ? <code style={{ background: '#e8e8e8', padding: '2px 6px', borderRadius: 4, fontSize: 13, color: '#d63384' }} {...props}>{children}</code>
                              : <pre style={{ background: '#2d2d2d', color: '#f8f8f2', padding: 12, borderRadius: 8, fontSize: 13, lineHeight: 1.5, overflow: 'auto' }}><code {...props}>{children}</code></pre>;
                          },
                          ol: ({ node, ...props }) => <ol style={{ paddingLeft: 20, margin: '4px 0' }} {...props} />,
                          ul: ({ node, ...props }) => <ul style={{ paddingLeft: 20, margin: '4px 0' }} {...props} />,
                          li: ({ node, ...props }) => <li style={{ marginBottom: 2 }} {...props} />,
                          h1: ({ node, ...props }) => <h1 style={{ fontSize: 16, fontWeight: 700, margin: '8px 0 4px' }} {...props} />,
                          h2: ({ node, ...props }) => <h2 style={{ fontSize: 15, fontWeight: 700, margin: '8px 0 4px' }} {...props} />,
                          h3: ({ node, ...props }) => <h3 style={{ fontSize: 14, fontWeight: 600, margin: '6px 0 3px' }} {...props} />,
                          p: ({ node, ...props }) => <p style={{ margin: '4px 0' }} {...props} />,
                          a: ({ node, ...props }) => <a style={{ color: '#1a73e8' }} target="_blank" rel="noopener noreferrer" {...props} />,
                          blockquote: ({ node, ...props }) => <blockquote style={{ borderLeft: '3px solid #5B9E6F', paddingLeft: 12, margin: '6px 0', color: '#555' }} {...props} />,
                        }}
                      />
                    )}
                  </div>
                  {msg.role === 'user' && (
                    <div style={s.userAvatar}>我</div>
                  )}
                </div>
              ))}
              {aiSending && (
                <div style={{ display: 'flex', marginBottom: 12 }}>
                  <div style={s.aiAvatar}>AI</div>
                  <div style={{ padding: '10px 14px', borderRadius: 18, background: '#f0f0f0', color: '#999', fontSize: 14 }}>
                    思考中<span style={{ animation: 'dotPulse 1.5s infinite' }}>...</span>
                  </div>
                </div>
              )}
            </div>
            <div style={s.aiChatFooter}>
              <input
                value={aiInput} onChange={e => setAiInput(e.target.value)}
                onKeyDown={handleAIKeyDown}
                placeholder="输入关于PPT内容的问题..." style={s.aiChatInput}
                disabled={aiSending}
              />
              <button onClick={handleAISend} disabled={!aiInput.trim() || aiSending}
                style={{ ...s.aiSendBtn, opacity: !aiInput.trim() || aiSending ? 0.5 : 1 }}>发送</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* 侧边面板 */
function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      position: 'absolute', right: 24, top: 64,
      width: 300, maxHeight: 'calc(100% - 160px)', overflowY: 'auto',
      background: 'rgba(255,255,255,0.95)', color: '#333',
      borderRadius: 12, padding: 16,
      boxShadow: '0 4px 20px rgba(0,0,0,0.3)', zIndex: 20,
      backdropFilter: 'blur(10px)',
    }}>
      {children}
    </div>
  );
}

/* 样式 */
const s: Record<string, React.CSSProperties | any> = {
  wrap: { display: 'flex', flexDirection: 'column', height: '100vh', background: '#1a1a2e', color: '#fff', position: 'relative' },
  ctr: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', color: '#999', background: '#1a1a2e' },
  spnr: { width: 40, height: 40, border: '3px solid #444', borderTop: '3px solid #5B9E6F', borderRadius: '50%', animation: 'spin 0.8s linear infinite' },
  hdr: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 20px', background: 'rgba(0,0,0,0.3)', zIndex: 10 },
  iframeWrap: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 8, position: 'relative', overflow: 'hidden', background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)' },
  iframeBox: { width: '100%', maxWidth: 'calc(100vh * 16 / 9)', aspectRatio: '16 / 9', borderRadius: 12, overflow: 'hidden', boxShadow: '0 8px 40px rgba(0,0,0,0.5)', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  iframe: { width: '100%', height: '100%', border: 'none' },
  tBar: { background: 'rgba(0,0,0,0.3)', padding: '8px 20px', display: 'flex', alignItems: 'center', gap: 8, zIndex: 10 },
  nBtn: { padding: '8px 16px', background: 'rgba(255,255,255,0.08)', border: 'none', borderRadius: 6, color: '#fff', cursor: 'pointer', fontSize: 13 },
  tBtn: { padding: '6px 14px', background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 6, color: '#fff', cursor: 'pointer', fontSize: 13 },
  sel: { padding: '4px 8px', borderRadius: 6, border: 'none', background: 'rgba(255,255,255,0.15)', color: '#fff', fontSize: 13, outline: 'none', cursor: 'pointer' },
  danLayer: { position: 'absolute', top: 60, right: 20, width: 280, pointerEvents: 'none', zIndex: 15 },
  danItem: { padding: '4px 10px', marginBottom: 4, borderRadius: 12, background: 'rgba(0,0,0,0.5)', color: '#fff', fontSize: 13, animation: 'fadeIn 0.3s' },
  danIn: { padding: '6px 10px', border: 'none', borderRadius: 4, background: 'rgba(255,255,255,0.15)', color: '#fff', fontSize: 13, width: 150, outline: 'none' },
  sndBtn: { padding: '6px 10px', background: '#5B9E6F', border: 'none', borderRadius: 4, color: '#fff', cursor: 'pointer', fontSize: 12 },
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 },
  modalCard: { background: '#fff', borderRadius: 12, padding: 24, width: 400, maxWidth: '90vw' },
  modalHdr: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  closeBtn: { background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#999' },
  inp: { width: '100%', padding: 8, marginBottom: 8, border: '1px solid #ddd', borderRadius: 6, boxSizing: 'border-box', fontSize: 13 },
  addBtn: { padding: '4px 12px', background: '#f5f5f5', border: '1px solid #ddd', borderRadius: 6, cursor: 'pointer', fontSize: 12, marginTop: 4 },
  crtBtn: (c: string) => ({ width: '100%', padding: 10, background: c, color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, marginTop: 12 }),
  clsBtn: { padding: '6px 12px', background: '#2d7d46', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, marginTop: 8 },
  clsBtn2: { padding: '6px 12px', background: '#555', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, marginTop: 8 },
  /* AI 问答样式 */
  aiChatOverlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200 },
  aiChatModal: { width: 450, height: 500, maxWidth: '90vw', maxHeight: '80vh', background: '#fff', borderRadius: 16, display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '0 8px 40px rgba(0,0,0,0.3)' },
  aiChatHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid #eee' },
  aiChatBody: { flex: 1, padding: '14px 18px', overflowY: 'auto', display: 'flex', flexDirection: 'column' },
  aiChatFooter: { display: 'flex', gap: 8, padding: '12px 18px', borderTop: '1px solid #eee', background: '#fafafa' },
  aiChatInput: { flex: 1, padding: '10px 14px', border: '1px solid #ddd', borderRadius: 24, fontSize: 14, outline: 'none', background: '#fff' },
  aiSendBtn: { padding: '10px 20px', background: '#7c4dff', color: '#fff', border: 'none', borderRadius: 24, cursor: 'pointer', fontWeight: 600, fontSize: 14, whiteSpace: 'nowrap' },
  aiAvatar: { width: 32, height: 32, borderRadius: '50%', background: '#7c4dff', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0, marginRight: 8 },
  userAvatar: { width: 32, height: 32, borderRadius: '50%', background: '#5B9E6F', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0, marginLeft: 8 },
};
