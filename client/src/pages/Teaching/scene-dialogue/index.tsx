// 课堂情景对话 — 支持语音实时对话、AI 发音/语法纠错
import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { colors, radius, typography, space, cardStyle, shadows, btnPrimary, btnSmall, btnSmallSecondary, inputStyle, IconSpeaker, IconBack, IconMic, IconPlay, IconStop, IconBulb, IconGraduation } from '../../../design-system';

// ─── 麦克风测试常量 ────────────────────────────────
const MIC_TEST_TEXT = '生活就像海洋，只有意志坚强的人才能到达彼岸。An apple a day, doctors keep me away.';

// ─── 类型定义 ──────────────────────────────────────
interface Message {
  role: 'user' | 'ai';
  content: string;
  transcription?: string;    // 用户语音转写文本
  analysis?: string;         // 纠错分析
  audioUrl?: string;         // AI 回答的音频 URL
  timestamp: number;
}

interface ScenarioPreset {
  id: string;
  name: string;
  icon: string;
}

/** 评分各维度 */
interface EvaluationDimensions {
  pronunciation: number;   // 发音准确度 (0-20)
  pause_fluency: number;   // 停顿与流利度 (0-20)
  grammar: number;         // 语法准确度 (0-20)
  vocabulary: number;      // 词汇表达 (0-20)
  interaction: number;     // 互动参与 (0-20)
}

/** 评分结果 */
interface EvaluationResult {
  score: number;
  dimensions: EvaluationDimensions;
  feedback: string;
  strengths: string[];
  improvements: string[];
}

/** 对话轮次（用于评分） */
interface ConversationTurn {
  role: 'user' | 'ai';
  content: string;
}

type Mode = 'rest' | 'realtime';

// ─── 本地场景兜底数据 ────────────────────────────
const LOCAL_SCENARIOS: ScenarioPreset[] = [
  { id: 'coffee', name: '咖啡店点餐', icon: '☕' },
  { id: 'restaurant', name: '餐厅用餐', icon: '🍽️' },
  { id: 'shopping', name: '购物逛街', icon: '🛍️' },
  { id: 'travel', name: '旅行问路', icon: '🗺️' },
  { id: 'hotel', name: '酒店入住', icon: '🏨' },
  { id: 'airport', name: '机场出行', icon: '✈️' },
  { id: 'interview', name: '面试求职', icon: '💼' },
  { id: 'hospital', name: '看医生', icon: '🏥' },
  { id: 'library', name: '图书馆', icon: '📚' },
  { id: 'friends', name: '结识朋友', icon: '🤝' },
];

const LEVELS = [
  { value: 'beginner', label: '初级' },
  { value: 'intermediate', label: '中级' },
  { value: 'advanced', label: '高级' },
];

// PCM 16KHz 录音参数
const PCM_SAMPLE_RATE = 16000;

// Float32 → Int16 (小端序)
function float32ToInt16(float32: Float32Array): Int16Array {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return int16;
}

// 降采样
function downsample(buffer: Float32Array, sourceRate: number, targetRate: number): Float32Array {
  if (sourceRate === targetRate) return buffer;
  const ratio = sourceRate / targetRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    const srcIdx = i * ratio;
    const idx1 = Math.floor(srcIdx);
    const idx2 = Math.min(idx1 + 1, buffer.length - 1);
    const frac = srcIdx - idx1;
    result[i] = buffer[idx1] * (1 - frac) + buffer[idx2] * frac;
  }
  return result;
}

// ─── 组件 ──────────────────────────────────────────

/** 获取浏览器支持的 MediaRecorder MIME 类型 */
function getSupportedMimeType(): string {
  const types = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
    'audio/mpeg',
  ];
  for (const t of types) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return ''; // fallback – 让浏览器自己选
}

export default function SceneDialogue() {
  const navigate = useNavigate();

  // 场景
  const [scenarios, setScenarios] = useState<ScenarioPreset[]>(LOCAL_SCENARIOS);
  const [selectedScenario, setSelectedScenario] = useState<ScenarioPreset | null>(null);
  const [level, setLevel] = useState('intermediate');
  const [mode, setMode] = useState<Mode>('rest'); // 默认 REST 模式

  // 对话
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 麦克风测试
  const [micTestActive, setMicTestActive] = useState(false);
  const [micTestRecording, setMicTestRecording] = useState(false);
  const [micTestAudioUrl, setMicTestAudioUrl] = useState<string | null>(null);
  const [micTestPlaying, setMicTestPlaying] = useState(false);

  // 实时对话通话状态
  const [callActive, setCallActive] = useState(false);
  const [callDuration, setCallDuration] = useState(0);
  const callTimerRef = useRef<number>(0);
  const streamRef = useRef<MediaStream | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const [playingUrl, setPlayingUrl] = useState('');
  const [inputText, setInputText] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // ── 评分相关 ──
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evaluationError, setEvaluationError] = useState('');
  const [showEvaluation, setShowEvaluation] = useState(false);
  // 累积 WS 模式下的对话历史（用于评分）
  const [conversationTurns, setConversationTurns] = useState<ConversationTurn[]>([]);
  const conversationTurnsRef = useRef<ConversationTurn[]>([]); // ref 避免闭包过期

  // 麦克风开关状态（通话中可切换，避免录到杂音）
  const [micEnabled, setMicEnabled] = useState(false);
  const micEnabledRef = useRef(false);

  // 波形条动画参数（稳定值，避免 Math.random 反复重算）
  const waveBars = useMemo(() =>
    [...Array(32)].map((_, i) => ({
      duration: 0.3 + Math.random() * 0.5,
      delay: i * 0.04,
    })),
  []);

  // WebSocket 实时语音状态
  const [wsConnected, setWsConnected] = useState(false);
  const [wsResult, setWsResult] = useState<{ asrText: string; chatText: string } | null>(null);
  const [activeSpeaker, setActiveSpeaker] = useState<'ai' | 'user' | null>(null);
  // 已完成轮次的对话条目（每句独立显示）
  const [dialogueItems, setDialogueItems] = useState<{role: 'user'|'ai'; text: string}[]>([]);
  // 当前轮次实时增量文本
  const [liveAsrText, setLiveAsrText] = useState('');
  const [liveChatText, setLiveChatText] = useState('');
  const liveAsrTextRef = useRef('');
  const liveChatTextRef = useRef('');
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const scriptNodeRef = useRef<ScriptProcessorNode | null>(null);
  const ttsAudioCtxRef = useRef<AudioContext | null>(null);
  const ttsNextPlayTimeRef = useRef<number>(0); // 下一个音频块的播放起始时间戳
  const wsEndCallTimerRef = useRef<number>(0);  // endCall 超时定时器（组件卸载时清理用）

  // 加载场景列表
  useEffect(() => {
    fetch('/Elearning/api/v1/ai/scenarios')
      .then(r => r.json())
      .then(res => {
        if (res.code === 0 && res.data?.presets) {
          setScenarios(res.data.presets);
        }
      })
      .catch(() => {/* 使用本地兜底数据 */});
  }, []);

  // 自动滚动
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  // ── WebSocket 连接 ──
  const connectWebSocket = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      alert('请先登录');
      return;
    }
    const scenarioId = selectedScenario?.id || '';
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${proto}//${window.location.host}/Elearning/api/v1/ai/voice-chat/ws?scenario_id=${scenarioId}&level=${level}&token=${token}`;
    console.log('[WS] 正在连接:', wsUrl.replace(token, '***'));
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onopen = () => {
      console.log('[WS] 连接已建立');
      setWsConnected(true);
      setWsResult(null);
    };
    // 本轮用户 ASR 累积
    let currentTurnAsr = '';
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'asr') {
          setActiveSpeaker('user');
          currentTurnAsr += data.text;
          liveAsrTextRef.current += data.text;
          setLiveAsrText(liveAsrTextRef.current);
          setLiveChatText('');
          liveChatTextRef.current = '';
          setWsResult(prev => ({ asrText: (prev?.asrText||'') + data.text, chatText: prev?.chatText||'' }));
        } else if (data.type === 'chat') {
          setActiveSpeaker('ai');
          liveChatTextRef.current += data.text;
          setLiveChatText(liveChatTextRef.current);
          setWsResult(prev => ({ asrText: prev?.asrText||'', chatText: (prev?.chatText||'') + data.text }));
        } else if (data.type === 'asr_ended') {
          // ASR 结束：将本轮用户发言作为独立条目存入
          const finalAsr = currentTurnAsr;
          if (finalAsr.trim()) {
            setDialogueItems(prev => [...prev, { role: 'user', text: finalAsr }]);
          }
        } else if (data.type === 'chat_ended') {
          // Chat 结束：将本轮 AI 回复作为独立条目存入（从 ref 读取，避免闭包过期）
          const finalChat = liveChatTextRef.current || '';
          if (finalChat.trim()) {
            setDialogueItems(prev => [...prev, { role: 'ai', text: finalChat }]);
          }
          // 同时存入 conversationTurns（用于评分）
          const finalAsr = currentTurnAsr || '';
          if (finalAsr.trim()) {
            const turn: ConversationTurn = { role: 'user', content: finalAsr };
            conversationTurnsRef.current = [...conversationTurnsRef.current, turn];
            setConversationTurns(prev => [...prev, turn]);
          }
          if (finalChat.trim()) {
            const turn: ConversationTurn = { role: 'ai', content: finalChat };
            conversationTurnsRef.current = [...conversationTurnsRef.current, turn];
            setConversationTurns(prev => [...prev, turn]);
          }
          // 重置当前轮次
          currentTurnAsr = '';
          liveAsrTextRef.current = '';
          liveChatTextRef.current = '';
          setLiveAsrText('');
          setLiveChatText('');
        } else if (data.type === 'audio') {
          setActiveSpeaker('ai');
          // 后端发送 PCM s16le 24000Hz 单声道，用 Web Audio API 实时播放
          const binary = atob(data.data);
          const pcm16 = new Int16Array(binary.length / 2);
          for (let i = 0, j = 0; i < binary.length; i += 2, j++) {
            pcm16[j] = (binary.charCodeAt(i + 1) << 8) | binary.charCodeAt(i);
          }
          playPCM(pcm16, 24000);
        } else if (data.type === 'tts_ended') {
          setActiveSpeaker(null);
          // TTS 结束，重置下一轮播放时间
          ttsNextPlayTimeRef.current = 0;
        } else if (data.type === 'error') {
          console.error('[WS] 错误:', data.message);
          alert(`语音服务错误: ${data.message}`);
        } else if (data.type === 'full_result') {
          console.log('[WS] 对话完成:', data);
          console.log('[WS] full_result asr_text长度:', data.asr_text?.length, 'chat_text长度:', data.chat_text?.length);
          // 收集最终 ASR/Chat 文本
          const finalAsr = data.asr_text || '';
          const finalChat = data.chat_text || '';
          // 避免重复记录
          const existing = conversationTurnsRef.current;
          const lastUser = existing.length > 0 && existing[existing.length-1].role === 'user'
            ? existing[existing.length-1].content : '';
          if (finalAsr && finalAsr !== lastUser) {
            // 作为独立条目展示（如果尚未通过 asr_ended 添加）
            setDialogueItems(prev => {
              const last = prev[prev.length-1];
              if (last?.role === 'user' && last.text === finalAsr) return prev;
              return [...prev, { role: 'user' as const, text: finalAsr }];
            });
            const turn: ConversationTurn = { role: 'user', content: finalAsr };
            conversationTurnsRef.current = [...conversationTurnsRef.current, turn];
            setConversationTurns(prev => [...prev, turn]);
          }
          if (finalChat) {
            setDialogueItems(prev => {
              const last = prev[prev.length-1];
              if (last?.role === 'ai' && last.text === finalChat) return prev;
              return [...prev, { role: 'ai' as const, text: finalChat }];
            });
            const turn: ConversationTurn = { role: 'ai', content: finalChat };
            conversationTurnsRef.current = [...conversationTurnsRef.current, turn];
            setConversationTurns(prev => [...prev, turn]);
          }
          setLiveAsrText('');
          setLiveChatText('');
          liveAsrTextRef.current = '';
          liveChatTextRef.current = '';
        }
      } catch {}
    };
    ws.onerror = (e) => {
      console.error('[WS] 连接错误:', e);
      setWsConnected(false);
      alert('无法连接到语音服务，请确保后端服务已启动');
    };
    ws.onclose = (e) => {
      console.log('[WS] 连接关闭:', e.code, e.reason);
      setWsConnected(false);
    };
  }, [selectedScenario?.id, level]);

  const disconnectWebSocket = useCallback(() => {
    if (wsRef.current) {
      try { wsRef.current.send(JSON.stringify({ type: 'close' })); } catch {}
      wsRef.current.close();
      wsRef.current = null;
    }
    setWsConnected(false);
  }, []);

  // 用 Web Audio API 按顺序播放 PCM s16le 数据，避免多块同时播放
  const playPCM = useCallback((pcm16: Int16Array, sampleRate: number) => {
    if (pcm16.length === 0) return;
    // 复用 TTS 专用 AudioContext
    if (!ttsAudioCtxRef.current || ttsAudioCtxRef.current.state === 'closed') {
      ttsAudioCtxRef.current = new AudioContext({ sampleRate });
      ttsNextPlayTimeRef.current = 0; // 新建 context 时重置播放时间
    }
    const ctx = ttsAudioCtxRef.current;
    // Int16 → Float32 (-1.0 ~ 1.0)
    const float32 = new Float32Array(pcm16.length);
    for (let i = 0; i < pcm16.length; i++) {
      float32[i] = pcm16[i] / 32768;
    }
    const audioBuffer = ctx.createBuffer(1, float32.length, sampleRate);
    audioBuffer.copyToChannel(float32, 0);
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    // 计算播放起始时间：如果上一个块还没播完，排队到其末尾；否则立即播放
    const now = ctx.currentTime;
    const startTime = Math.max(ttsNextPlayTimeRef.current, now);
    source.start(startTime);
    // 更新下一个块的起始时间 = 当前块起始 + 持续时间
    ttsNextPlayTimeRef.current = startTime + float32.length / sampleRate;
  }, []);

  // ── PCM 实时录音捕获 ──
  /** 启动麦克风捕获并发送 PCM 数据到 WebSocket */
  const startPCMCapture = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const audioCtx = new AudioContext({ sampleRate: PCM_SAMPLE_RATE });
      audioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const scriptNode = audioCtx.createScriptProcessor(4096, 1, 1);
      scriptNodeRef.current = scriptNode;
      source.connect(scriptNode);
      scriptNode.connect(audioCtx.destination);
      const sourceRate = audioCtx.sampleRate;
      scriptNode.onaudioprocess = (event) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        setActiveSpeaker('user');
        const input = event.inputBuffer.getChannelData(0);
        const down = sourceRate === PCM_SAMPLE_RATE ? input : downsample(input, sourceRate, PCM_SAMPLE_RATE);
        wsRef.current.send(float32ToInt16(down as Float32Array).buffer);
      };
    } catch (err) {
      console.error('PCM 录音失败:', err);
      alert('无法访问麦克风');
      setMicEnabled(false);
      micEnabledRef.current = false;
    }
  }, []);

  /** 仅停止麦克风捕获（保留 WebSocket 连接和会话） */
  const stopMicOnly = useCallback(() => {
    if (scriptNodeRef.current) {
      scriptNodeRef.current.disconnect();
      scriptNodeRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
  }, []);

  /** 结束通话：停止麦克风 + 结束会话 + 清理通话计时器 */
  const stopPCMCapture = useCallback(() => {
    stopMicOnly();
    if (callTimerRef.current) { clearInterval(callTimerRef.current); callTimerRef.current = 0; }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'finish_session' }));
    }
    setCallActive(false);
    setActiveSpeaker(null);
    setMicEnabled(false);
    micEnabledRef.current = false;
  }, [stopMicOnly]);

  const cleanupPCMCapture = useCallback(() => {
    stopPCMCapture();
  }, [stopPCMCapture]);

  // 组件卸载时清理资源
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
      }
      if (callTimerRef.current) {
        clearInterval(callTimerRef.current);
      }
      if (wsEndCallTimerRef.current) {
        clearTimeout(wsEndCallTimerRef.current);
        wsEndCallTimerRef.current = 0;
      }
      disconnectWebSocket();
      cleanupPCMCapture();
    };
  }, [disconnectWebSocket, cleanupPCMCapture]);

  // ── 麦克风测试 ──
  const micTestRecordRef = useRef<MediaRecorder | null>(null);
  const micTestChunksRef = useRef<Blob[]>([]);
  const micTestStreamRef = useRef<MediaStream | null>(null);
  const micTestAnalyserRef = useRef<AnalyserNode | null>(null);
  const micTestMonitorTrackRef = useRef<MediaStreamTrack | null>(null);
  const micTestLevelTimerRef = useRef<number>(0);

  const [micTestLevel, setMicTestLevel] = useState(0);

  const startMicTest = useCallback(() => {
    setMicTestActive(true);
    setMicTestAudioUrl(null);
    setMicTestPlaying(false);
    setMicTestLevel(0);
  }, []);

  const cancelMicTest = useCallback(() => {
    if (micTestRecording) stopMicTestRecording();
    if (micTestMonitorTrackRef.current) {
      micTestMonitorTrackRef.current.stop();
      micTestMonitorTrackRef.current = null;
    }
    if (micTestAudioUrl) { URL.revokeObjectURL(micTestAudioUrl); setMicTestAudioUrl(null); }
    if (micTestLevelTimerRef.current) { cancelAnimationFrame(micTestLevelTimerRef.current); micTestLevelTimerRef.current = 0; }
    setMicTestActive(false);
    setMicTestPlaying(false);
    setMicTestLevel(0);
  }, [micTestRecording, micTestAudioUrl]);

  const startMicTestRecording = useCallback(async () => {
    try {
      const mimeType = getSupportedMimeType();
      console.log('[MicTest] 浏览器支持 MIME:', mimeType || '默认');

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micTestStreamRef.current = stream;

      // 打印音频设备信息
      const track = stream.getAudioTracks()[0];
      console.log('[MicTest] 音频设备:', track.label, JSON.stringify(track.getSettings()));

      // ⚠️ Chrome 下 AnalyserNode 与 MediaRecorder 共用同一 MediaStream 会导致录制静音，
      //    因此克隆一份音轨给音量监测，MediaRecorder 使用原始未受干扰的流。
      const monitorTrack = track.clone();
      micTestMonitorTrackRef.current = monitorTrack;
      const monitorStream = new MediaStream([monitorTrack]);
      const audioCtx = new AudioContext();
      const source = audioCtx.createMediaStreamSource(monitorStream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      micTestAnalyserRef.current = analyser;

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const pollLevel = () => {
        analyser.getByteTimeDomainData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += Math.abs(dataArray[i] - 128);
        }
        const avg = sum / dataArray.length;
        const pct = Math.min(100, Math.round(avg * 100 / 128));
        setMicTestLevel(pct);
        micTestLevelTimerRef.current = requestAnimationFrame(pollLevel);
      };
      pollLevel();

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      const usedMime = recorder.mimeType;
      console.log('[MicTest] 实际使用的 MIME:', usedMime);

      micTestRecordRef.current = recorder;
      micTestChunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) micTestChunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        if (micTestLevelTimerRef.current) { cancelAnimationFrame(micTestLevelTimerRef.current); micTestLevelTimerRef.current = 0; }
        audioCtx.close();
        const totalBytes = micTestChunksRef.current.reduce((s, b) => s + b.size, 0);
        console.log(`[MicTest] 录音完成，${micTestChunksRef.current.length} 个数据块，共 ${totalBytes} 字节`);
        const blob = new Blob(micTestChunksRef.current, { type: 'audio/webm' });
        const url = URL.createObjectURL(blob);
        setMicTestAudioUrl(url);
        setMicTestRecording(false);
      };
      recorder.start(100);
      setMicTestRecording(true);
    } catch (err: any) {
      const msg = err?.message || err?.name || String(err);
      console.error('[MicTest] 录音失败:', err);
      alert(`麦克风测试失败: ${msg}\n\n请检查:\n1. 是否已允许麦克风权限\n2. 当前页面是否为 HTTPS 或 localhost\n3. 是否有其他应用占用麦克风`);
    }
  }, []);

  const stopMicTestRecording = useCallback(() => {
    if (micTestRecordRef.current && micTestRecordRef.current.state !== 'inactive') {
      micTestRecordRef.current.stop();
    }
    if (micTestMonitorTrackRef.current) {
      micTestMonitorTrackRef.current.stop();
      micTestMonitorTrackRef.current = null;
    }
    if (micTestStreamRef.current) {
      micTestStreamRef.current.getTracks().forEach(t => t.stop());
      micTestStreamRef.current = null;
    }
    if (micTestLevelTimerRef.current) {
      cancelAnimationFrame(micTestLevelTimerRef.current);
      micTestLevelTimerRef.current = 0;
    }
  }, []);

  const playMicTest = useCallback(() => {
    if (!micTestAudioUrl) return;
    const audio = new Audio(micTestAudioUrl);
    audioPlayerRef.current = audio;
    audio.onended = () => { setMicTestPlaying(false); };
    audio.onerror = (e) => {
      console.error('[MicTest] 播放失败:', audio.error?.code, audio.error?.message, e);
      setMicTestPlaying(false);
    };
    audio.play()
      .then(() => setMicTestPlaying(true))
      .catch((err) => {
        console.error('[MicTest] play() 异常:', err);
      });
  }, [micTestAudioUrl]);

  // ── 调用评分 API ──
  const triggerEvaluation = useCallback(async (history: ConversationTurn[]) => {
    const userTurns = history.filter(m => m.role === 'user');
    if (userTurns.length === 0) return;
    setEvaluating(true);
    setEvaluationError('');
    try {
      const res = await fetch('/Elearning/api/v1/ai/voice-evaluate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: JSON.stringify({
          scenario_id: selectedScenario?.id || '',
          level,
          conversation_history: history,
        }),
      });
      const json = await res.json();
      if (json.code === 0 && json.data) {
        setEvaluation(json.data);
        setShowEvaluation(true);
      } else {
        setEvaluationError(json.message || '评分失败');
      }
    } catch (err: any) {
      setEvaluationError(err?.message || '评分请求失败');
    } finally {
      setEvaluating(false);
    }
  }, [selectedScenario?.id, level]);

  // ── 实时对话开始/结束 ──
  const startCall = useCallback(async () => {
    setCallDuration(0);
    setWsResult(null);
    setActiveSpeaker(null);
    setMessages([]);
    setEvaluation(null);
    setEvaluationError('');
    setShowEvaluation(false);
    setConversationTurns([]);
    conversationTurnsRef.current = [];
    setDialogueItems([]);
    setLiveAsrText('');
    setLiveChatText('');
    liveAsrTextRef.current = '';
    liveChatTextRef.current = '';
    setMicEnabled(false);
    micEnabledRef.current = false;
    setCallActive(true);
    callTimerRef.current = window.setInterval(() => setCallDuration(p => p + 1), 1000);
    connectWebSocket();
    // 不再自动启动麦克风，等待用户点击麦克风按钮
  }, [connectWebSocket]);

  /** 切换麦克风开关（通话中可用） */
  const toggleMic = useCallback(() => {
    if (micEnabledRef.current) {
      // 关闭麦克风
      stopMicOnly();
      setMicEnabled(false);
      micEnabledRef.current = false;
    } else {
      // 开启麦克风
      setMicEnabled(true);
      micEnabledRef.current = true;
      startPCMCapture();
    }
  }, [startPCMCapture, stopMicOnly]);

  const endCall = useCallback(() => {
    console.log('[评分] endCall: 发送 finish_session，等待 3s 收集剩余消息');
    stopPCMCapture(); // 停止麦克风，发送 finish_session
    // 等待 3 秒让后端回传剩余的 chat_ended 事件，然后关闭连接并评分
    const timer = window.setTimeout(() => {
      // 发送 close 指令，断开 WebSocket
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        try { wsRef.current.send(JSON.stringify({ type: 'close' })); } catch {}
        wsRef.current.close();
        wsRef.current = null;
      }
      setWsConnected(false);
      // 立即用已积累的对话历史触发评分
      const history = conversationTurnsRef.current;
      console.log('[评分] conversationTurns 长度:', history.length);
      if (history.length > 0) {
        triggerEvaluation(history);
      }
    }, 3000);
    // 将定时器句柄存入 ref 以便组件卸载时清理
    wsEndCallTimerRef.current = timer;
  }, [stopPCMCapture, triggerEvaluation]);

  // ── 文字对话发送 ──
  const sendTextMessage = async (text: string) => {
    if (!text.trim() || sending) return;

    setSending(true);
    const userMsg: Message = {
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    setMessages(prev => [...prev, userMsg]);

    try {
      const res = await fetch('/Elearning/api/v1/ai/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: JSON.stringify({
          messages: [...messages.map(m => ({
            role: m.role === 'user' ? 'user' : 'assistant',
            content: m.content,
          })), { role: 'user', content: text }],
          scenario: selectedScenario?.id || '',
          level,
        }),
      });
      const json = await res.json();
      if (json.code === 0 && json.data?.content) {
        const aiMsg: Message = {
          role: 'ai',
          content: json.data.content,
          timestamp: Date.now() + 1,
        };
        setMessages(prev => [...prev, aiMsg]);
      }
    } catch (err) {
      console.error('对话失败:', err);
    } finally {
      setSending(false);
    }
  };

  // ── 播放 AI 音频 ──
  const playAudio = (url: string) => {
    if (playingUrl === url) {
      // 切换播放/暂停
      if (audioPlayerRef.current) {
        if (!audioPlayerRef.current.paused) {
          audioPlayerRef.current.pause();
          setPlayingUrl('');
        } else {
          audioPlayerRef.current.play();
        }
      }
      return;
    }

    const audio = new Audio(url);
    audioPlayerRef.current = audio;
    audio.onended = () => setPlayingUrl('');
    audio.onerror = () => setPlayingUrl('');
    audio.play().then(() => setPlayingUrl(url)).catch(() => setPlayingUrl(''));
  };

  // ── 选择场景 ──
  const selectScenario = (s: ScenarioPreset) => {
    setSelectedScenario(s);
    setMessages([]);
  };

  // ── 格式化时间 ──
  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  // ── 渲染评分面板 ──
  const renderEvaluationPanel = (evalResult: EvaluationResult) => {
    const dims = evalResult.dimensions || {};
    const dimLabels: { key: keyof EvaluationDimensions; label: string; icon: string; desc: string }[] = [
      { key: 'pronunciation', label: '发音准确度', icon: '🎙️', desc: '元音/辅音清晰度、重音、语调' },
      { key: 'pause_fluency', label: '停顿与流利度', icon: '🌊', desc: '自然停顿、减少填充词(uh/um)、节奏流畅' },
      { key: 'grammar', label: '语法准确度', icon: '📝', desc: '句子结构、时态、冠词、介词' },
      { key: 'vocabulary', label: '词汇表达', icon: '📖', desc: '用词选择、多样性、场景贴切度' },
      { key: 'interaction', label: '互动参与度', icon: '💬', desc: '主动回应、提问、紧扣主题' },
    ];

    const getColorForScore = (score: number, max: number) => {
      const pct = score / max;
      if (pct >= 0.8) return '#22c55e';
      if (pct >= 0.6) return colors.primary;
      if (pct >= 0.4) return '#eab308';
      return '#ef4444';
    };

    const totalMax = 100;
    const totalPct = evalResult.score / totalMax;

    return (
      <div style={{
        width: '100%', maxWidth: 520,
        marginTop: space.lg,
        background: '#fafdfa',
        borderRadius: radius.lg,
        border: `1px solid ${colors['block-lime']}`,
        padding: space.lg,
        boxShadow: shadows.soft,
      }}>
        {/* 标题行 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: space.sm, marginBottom: space.md }}>
          <IconGraduation size={20} color={colors.primary} />
          <span style={{ fontWeight: 700, fontSize: 16, color: colors['text-primary'] }}>
            对话表现评估
          </span>
          <button
            style={{
              marginLeft: 'auto', ...btnSmall,
              background: 'transparent', color: colors['text-tertiary'],
              border: 'none', padding: '2px 8px', fontSize: 12, cursor: 'pointer',
            }}
            onClick={() => setShowEvaluation(false)}
          >
            关闭
          </button>
        </div>

        {/* 总分环形图 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: space.lg, marginBottom: space.md }}>
          <div style={{
            position: 'relative', width: 88, height: 88, flexShrink: 0,
          }}>
            <svg width="88" height="88" viewBox="0 0 88 88">
              {/* 背景圆环 */}
              <circle cx="44" cy="44" r="38" fill="none"
                stroke={colors['surface-soft']} strokeWidth="8" />
              {/* 进度圆环 */}
              <circle cx="44" cy="44" r="38" fill="none"
                stroke={getColorForScore(evalResult.score, totalMax)}
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={`${2 * Math.PI * 38 * totalPct} ${2 * Math.PI * 38 * (1 - totalPct)}`}
                transform="rotate(-90, 44, 44)"
                style={{ transition: 'stroke-dasharray 0.8s ease' }}
              />
            </svg>
            <div style={{
              position: 'absolute', top: 0, left: 0, width: 88, height: 88,
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'center',
            }}>
              <span style={{
                fontSize: 22, fontWeight: 700, color: colors['text-primary'],
                lineHeight: 1,
              }}>{evalResult.score}</span>
              <span style={{ fontSize: 10, color: colors['text-tertiary'], lineHeight: 1 }}>分</span>
            </div>
          </div>
          <div style={{ flex: 1, fontSize: 13, lineHeight: 1.6, color: colors['text-secondary'] }}>
            {evalResult.feedback}
          </div>
        </div>

        {/* 各维度评分条 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: space.sm, marginBottom: space.md }}>
          {dimLabels.map(dim => {
            const score = dims[dim.key] || 0;
            const pct = score / 20; // 各维度满分 20
            const barColor = getColorForScore(score, 20);
            return (
              <div key={dim.key}>
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  marginBottom: 3,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 14 }}>{dim.icon}</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: colors['text-primary'] }}>
                      {dim.label}
                    </span>
                  </div>
                  <span style={{
                    fontSize: 12, fontWeight: 700,
                    color: barColor,
                  }}>{score}/20</span>
                </div>
                {/* 进度条 */}
                <div style={{
                  height: 6, borderRadius: radius.pill,
                  background: colors['surface-soft'], overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%', width: `${pct * 100}%`,
                    background: barColor, borderRadius: radius.pill,
                    transition: 'width 0.6s ease',
                  }} />
                </div>
                <div style={{ fontSize: 10, color: colors['text-tertiary'], marginTop: 1 }}>
                  {dim.desc}
                </div>
              </div>
            );
          })}
        </div>

        {/* 优势与待改进 */}
        <div style={{
          display: 'flex', gap: space.md,
        }}>
          {evalResult.strengths.length > 0 && (
            <div style={{ flex: 1 }}>
              <div style={{
                fontSize: 11, fontWeight: 600, color: '#22c55e', marginBottom: 4,
                textTransform: 'uppercase', letterSpacing: '0.3px',
              }}>✅ 优势</div>
              <ul style={{
                margin: 0, paddingLeft: 16, fontSize: 12, color: colors['text-secondary'],
                lineHeight: 1.7,
              }}>
                {evalResult.strengths.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
          {evalResult.improvements.length > 0 && (
            <div style={{ flex: 1 }}>
              <div style={{
                fontSize: 11, fontWeight: 600, color: '#eab308', marginBottom: 4,
                textTransform: 'uppercase', letterSpacing: '0.3px',
              }}>💪 待改进</div>
              <ul style={{
                margin: 0, paddingLeft: 16, fontSize: 12, color: colors['text-secondary'],
                lineHeight: 1.7,
              }}>
                {evalResult.improvements.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
        </div>
      </div>
    );
  };

  // ── 渲染纠错分析 ──
  const renderAnalysis = (analysis: string) => {
    if (!analysis) return null;
    const lines = analysis.split('\n').filter(Boolean);
    return (
      <div style={{
        marginTop: 8,
        padding: '8px 12px',
        background: '#f0fdf4',
        borderRadius: radius.md,
        border: `1px solid ${colors['block-lime']}`,
        fontSize: 12,
        lineHeight: 1.6,
        color: colors['text-secondary'],
      }}>
        {lines.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
    );
  };

  // ── 渲染视图 ──
  if (!selectedScenario) {
    return (
      <div>
        <div style={{ marginBottom: space.lg }}>
          <h1 style={{ ...typography.headline, margin: 0, color: colors['text-primary'] }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
                  onClick={() => navigate('/teaching')}>
              <IconBack size={18} color={colors['text-primary']} /> 课堂情景对话
            </span>
          </h1>
          <p style={{ ...typography['body-sm'], color: colors['text-tertiary'], marginTop: 4, marginBottom: 0 }}>
            选择一个场景，开始语音英语对话练习。AI 会分析你的发音和语法。
          </p>
        </div>

        {/* 难度选择 */}
        <div style={{ marginBottom: space.lg, display: 'flex', gap: space.sm, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: colors['text-secondary'], fontWeight: 500 }}>难度：</span>
          {LEVELS.map(l => (
            <button key={l.value}
              style={{
                ...btnSmall,
                background: level === l.value ? colors.primary : colors.canvas,
                color: level === l.value ? colors['on-primary'] : colors['text-secondary'],
                border: level === l.value ? 'none' : `1px solid ${colors.hairline}`,
              }}
              onClick={() => setLevel(l.value)}
            >
              {l.label}
            </button>
          ))}
        </div>

        {/* 模式切换 */}
        <div style={{ marginBottom: space.lg, display: 'flex', gap: space.sm, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: 13, color: colors['text-secondary'], fontWeight: 500 }}>模式：</span>
          <button
            style={{
              ...btnSmall,
              background: mode === 'rest' ? colors.primary : colors.canvas,
              color: mode === 'rest' ? colors['on-primary'] : colors['text-secondary'],
              border: mode === 'rest' ? 'none' : `1px solid ${colors.hairline}`,
            }}
            onClick={() => setMode('rest')}
          >
            🎤 标准模式
          </button>
          <button
            style={{
              ...btnSmall,
              background: mode === 'realtime' ? colors.primary : colors.canvas,
              color: mode === 'realtime' ? colors['on-primary'] : colors['text-secondary'],
              border: mode === 'realtime' ? 'none' : `1px solid ${colors.hairline}`,
            }}
            onClick={() => setMode('realtime')}
          >
            ⚡ 实时对话
          </button>
          <span style={{ fontSize: 11, color: colors['text-tertiary'], marginLeft: 4 }}>
            {mode === 'realtime' ? '边录边说，实时交互（推荐）' : '录完再发送'}
          </span>
        </div>

        {/* 麦克风测试按钮 / 面板 */}
        {!micTestActive ? (
          <div style={{ marginBottom: space.lg }}>
            <button
              style={{
                ...btnSmall,
                background: colors.canvas,
                color: colors['text-secondary'],
                border: `1px solid ${colors.hairline}`,
                display: 'inline-flex', alignItems: 'center', gap: 6,
              }}
              onClick={startMicTest}
            >
              🎙️ 测试麦克风
            </button>
            <span style={{ fontSize: 11, color: colors['text-tertiary'], marginLeft: 8 }}>
              录制一段测试语音并回放，检查设备是否正常
            </span>
          </div>
        ) : (
          <div style={{
            marginBottom: space.lg, padding: space.md,
            background: colors.canvas, borderRadius: radius.md,
            border: `1px solid ${colors['block-lime']}`,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.sm }}>
              <span style={{ fontWeight: 600, fontSize: 14, color: colors['text-primary'] }}>
                🎙️ 麦克风测试
              </span>
              <button
                style={{
                  ...btnSmall, fontSize: 12,
                  background: 'transparent', color: colors['text-tertiary'],
                  border: 'none', padding: 0,
                }}
                onClick={cancelMicTest}
              >
                关闭
              </button>
            </div>
            {/* 测试文本 */}
            <div style={{
              padding: '10px 14px', background: '#fff',
              borderRadius: radius.md, marginBottom: space.sm,
              fontSize: 13, lineHeight: 1.7, color: colors['text-primary'],
              border: `1px solid ${colors.hairline}`,
            }}>
              <div style={{ fontWeight: 500, marginBottom: 4, fontSize: 12, color: colors['text-tertiary'] }}>
                请朗读以下内容：
              </div>
              {MIC_TEST_TEXT}
            </div>
            {/* 操作按钮 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: space.sm }}>
              <button
                style={{
                  ...btnSmall,
                  background: micTestRecording ? colors.danger : colors.primary,
                  color: colors['on-primary'],
                  border: 'none',
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                }}
                onClick={micTestRecording ? stopMicTestRecording : startMicTestRecording}
              >
                {micTestRecording ? '⏹ 停止录音' : '🎤 开始录音'}
              </button>
              {micTestRecording && (
                <span style={{ fontSize: 12, color: colors.danger, fontWeight: 500 }}>
                  录音中...
                </span>
              )}
            </div>
            {/* 实时音量指示条 */}
            {micTestRecording && (
              <div style={{ marginTop: space.sm }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 11, color: colors['text-tertiary'] }}>
                  <span>实时音量</span>
                  <span>{micTestLevel}%</span>
                </div>
                <div style={{
                  height: 8, borderRadius: 4, overflow: 'hidden',
                  background: colors.hairline,
                }}>
                  <div style={{
                    width: `${micTestLevel}%`,
                    height: '100%',
                    borderRadius: 4,
                    transition: 'width 0.05s linear',
                    background: micTestLevel > 60
                      ? '#22c55e'
                      : micTestLevel > 20
                        ? '#eab308'
                        : '#ef4444',
                  }} />
                </div>
                {micTestLevel < 5 && (
                  <div style={{ marginTop: 4, fontSize: 11, color: '#ef4444' }}>
                    ⚠️ 未检测到声音输入，请检查麦克风是否被静音或选择了正确的输入设备
                  </div>
                )}
              </div>
            )}
            {micTestAudioUrl && !micTestRecording && (
                <button
                  style={{
                    ...btnSmall,
                    background: colors.canvas,
                    color: colors.primary,
                    border: `1px solid ${colors['block-lime']}`,
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                  }}
                  onClick={playMicTest}
                >
                  {micTestPlaying ? '⏹ 停止' : '▶ 回放录音'}
                </button>
              )}
            {micTestAudioUrl && !micTestRecording && !micTestPlaying && (
              <div style={{ marginTop: space.sm, fontSize: 11, color: colors['text-tertiary'] }}>
                ✅ 麦克风正常工作，录音已生成。如未听到声音，请检查扬声器或系统音频设置。
              </div>
            )}
          </div>
        )}

        {/* 场景卡片网格 */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
          gap: space.md,
        }}>
          {scenarios.map(s => (
            <div key={s.id}
              style={{ ...cardStyle, cursor: 'pointer', textAlign: 'center', padding: space.lg }}
              onClick={() => selectScenario(s)}
              onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.08)'; }}
              onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = ''; }}
            >
              <div style={{ fontSize: 36, marginBottom: 8 }}>{s.icon || '🎙️'}</div>
              <div style={{ fontWeight: 600, fontSize: 14, color: colors['text-primary'] }}>{s.name}</div>
              <div style={{ marginTop: 8 }}>
                <span style={{
                  ...btnSmall, fontSize: 12, padding: '4px 14px',
                  background: colors['block-lime'], color: colors.primary,
                  border: 'none',
                }}>
                  开始对话
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 80px)' }}>
      {/* 场景标题栏 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: space.sm,
        paddingBottom: space.md, borderBottom: `1px solid ${colors.hairline}`,
        marginBottom: space.md, flexShrink: 0,
      }}>
        <button style={btnSmallSecondary} onClick={() => setSelectedScenario(null)}>
          <IconBack size={14} color={colors['text-secondary']} /> 返回
        </button>
        <span style={{ fontSize: 20, marginRight: 4 }}>{selectedScenario.icon || '🎙️'}</span>
        <span style={{ fontWeight: 600, fontSize: 16, color: colors['text-primary'] }}>{selectedScenario.name}</span>
        <span style={{
          marginLeft: 'auto', padding: '3px 10px', borderRadius: radius.pill,
          background: colors['block-lime'], fontSize: 12, color: colors.primary, fontWeight: 500,
        }}>
          {LEVELS.find(l => l.value === level)?.label}
        </span>
      </div>

      {mode === 'rest' ? (
        /* ── 标准模式：文字对话 ── */
        <>
          <div style={{ flex: 1, overflowY: 'auto', paddingRight: space.sm }}>
            {messages.length === 0 && (
              <div style={{ textAlign: 'center', padding: '48px 24px', color: colors['text-tertiary'] }}>
                <div style={{ fontSize: 48, marginBottom: 12 }}>💬</div>
                <div style={{ fontSize: 14, fontWeight: 500, color: colors['text-secondary'] }}>开始文字对话</div>
                <div style={{ fontSize: 12, marginTop: 4 }}>在下方输入框打字，AI 会回答并纠错</div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} style={{
                display: 'flex', flexDirection: 'column',
                alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: space.md,
              }}>
                {msg.role === 'user' && (
                  <div style={{
                    ...cardStyle, maxWidth: '70%', padding: '10px 16px',
                    background: colors.primary, color: colors['on-primary'],
                    border: 'none', borderRadius: `${radius.lg} ${radius.lg} 4px ${radius.lg}`,
                  }}>
                    <div style={{ fontSize: 13, lineHeight: 1.5 }}>{msg.content}</div>
                  </div>
                )}
                {msg.role === 'ai' && (
                  <div style={{
                    ...cardStyle, maxWidth: '75%', padding: '10px 16px',
                    borderRadius: `${radius.lg} ${radius.lg} ${radius.lg} 4px`,
                  }}>
                    <div style={{ fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                    {msg.analysis && renderAnalysis(msg.analysis)}
                    {msg.audioUrl && (
                      <button style={{
                        ...btnSmall, marginTop: 8, fontSize: 12,
                        background: playingUrl === msg.audioUrl ? colors['block-lime'] : colors.canvas,
                        color: colors.primary, border: `1px solid ${colors['block-lime']}`,
                        display: 'inline-flex', alignItems: 'center', gap: 6,
                      }} onClick={() => playAudio(msg.audioUrl!)}>
                        {playingUrl === msg.audioUrl ? <IconStop size={12} color={colors.primary} /> : <IconPlay size={12} color={colors.primary} />}
                        {playingUrl === msg.audioUrl ? '停止' : '播放回答'}
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
            {sending && (
              <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: space.md }}>
                <div style={{ ...cardStyle, padding: '12px 16px', borderRadius: `${radius.lg} ${radius.lg} ${radius.lg} 4px` }}>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    {[0, 0.2, 0.4].map((d, i) => (
                      <div key={i} style={{
                        width: 6, height: 6, borderRadius: '50%', background: colors.primary,
                        animation: `bounce 1.4s ease-in-out ${d}s infinite`,
                      }} />
                    ))}
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* 文字输入栏 */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: space.sm,
            paddingTop: space.md, borderTop: `1px solid ${colors.hairline}`, flexShrink: 0,
          }}>
            <input
              ref={inputRef}
              type="text"
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !sending) { sendTextMessage(inputText); setInputText(''); } }}
              placeholder="输入英语对话内容..."
              style={{
                ...inputStyle, flex: 1,
              }}
            />
            <button
              style={{
                ...btnPrimary, padding: '10px 20px', flexShrink: 0,
                opacity: sending || !inputText.trim() ? 0.5 : 1,
              }}
              disabled={sending || !inputText.trim()}
              onClick={() => { sendTextMessage(inputText); setInputText(''); }}
            >
              发送
            </button>
          </div>

          {/* 标准模式：评估对话按钮 */}
          {messages.length >= 2 && !sending && (
            <div style={{ paddingTop: space.sm, borderTop: `1px solid ${colors.hairline}`, marginTop: space.sm, display: 'flex', justifyContent: 'center' }}>
              {!showEvaluation && !evaluating ? (
                <button
                  style={{
                    ...btnSmall,
                    background: 'transparent',
                    color: colors.primary,
                    border: `1px solid ${colors.primary}60`,
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                  }}
                  onClick={() => {
                    const history: ConversationTurn[] = messages.map(m => ({
                      role: m.role === 'user' ? 'user' : 'ai',
                      content: m.content,
                    }));
                    triggerEvaluation(history);
                  }}
                >
                  <IconGraduation size={14} color={colors.primary} /> 评估整个对话
                </button>
              ) : null}
            </div>
          )}

          {/* 标准模式评分结果 */}
          {evaluating && (
            <div style={{ textAlign: 'center', padding: space.md }}>
              <div style={{ fontSize: 13, color: colors['text-tertiary'] }}>
                AI 正在评估对话表现...
              </div>
            </div>
          )}
          {evaluationError && (
            <div style={{
              margin: space.md, padding: '10px 16px',
              background: '#fef2f2', borderRadius: radius.md,
              border: `1px solid ${colors.danger}40`,
              fontSize: 13, color: colors.danger,
            }}>
              ⚠️ 评分失败：{evaluationError}
            </div>
          )}
          {showEvaluation && evaluation && renderEvaluationPanel(evaluation)}
        </>
      ) : (
        /* ── 实时模式：通话界面 ── */
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: space.lg, padding: space.lg }}>
          {/* 通话状态 */}
          <div style={{ fontSize: 12, color: colors['text-tertiary'], display: 'flex', alignItems: 'center', gap: 6 }}>
            {callActive && (
              <>
                <span style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: '#22c55e', display: 'inline-block',
                  animation: 'pulse-dot 1.5s ease-in-out infinite',
                }} />
                通话中 · {formatDuration(callDuration)}
                <span style={{
                  marginLeft: 8, padding: '2px 8px', borderRadius: 10,
                  fontSize: 11, fontWeight: 500,
                  background: micEnabled ? '#dcfce7' : '#f3f4f6',
                  color: micEnabled ? '#16a34a' : '#6b7280',
                }}>
                  {micEnabled ? '🎤 麦克风已开' : '🔇 麦克风已关'}
                </span>
              </>
            )}
            {!callActive && '点击下方按钮开始实时语音对话'}
          </div>

          {/* 头像区域 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: space.xxl, width: '100%', maxWidth: 500, justifyContent: 'center' }}>
            {/* AI 头像 */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: space.sm }}>
              <div style={{
                width: 96, height: 96, borderRadius: '50%',
                background: activeSpeaker === 'ai' ? colors['block-lime'] : colors['surface-soft'],
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 40, transition: 'all 0.3s',
                boxShadow: activeSpeaker === 'ai' ? `0 0 0 4px ${colors.primary}40` : 'none',
              }}>
                🧠
              </div>
              <span style={{ fontSize: 14, fontWeight: 600, color: colors['text-primary'] }}>小e</span>
              {activeSpeaker === 'ai' && (
                <span style={{ fontSize: 11, color: colors.primary, fontWeight: 500 }}>正在说话...</span>
              )}
            </div>

            {/* 中间箭头 */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <div style={{ width: 60, height: 2, background: colors.hairline }} />
              <svg width={20} height={20} viewBox="0 0 20 20" fill={colors['text-tertiary']}>
                <path d="M10 3v14M7 14l3 3 3-3" stroke={colors['text-tertiary']} strokeWidth="1.5" fill="none" />
              </svg>
            </div>

            {/* 用户头像 */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: space.sm }}>
              <div style={{
                width: 96, height: 96, borderRadius: '50%',
                background: activeSpeaker === 'user' ? colors['block-lime'] : colors['surface-soft'],
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 40, transition: 'all 0.3s',
                boxShadow: activeSpeaker === 'user' ? `0 0 0 4px ${colors.primary}40` : 'none',
              }}>
                👤
              </div>
              <span style={{ fontSize: 14, fontWeight: 600, color: colors['text-primary'] }}>我</span>
              {activeSpeaker === 'user' && (
                <span style={{ fontSize: 11, color: colors.primary, fontWeight: 500 }}>正在说话...</span>
              )}
            </div>
          </div>

          {/* 语音波形动画 */}
          <div style={{ width: '100%', maxWidth: 400, height: 60, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
            {waveBars.map((bar, i) => (
              <div key={i} style={{
                width: 4, borderRadius: 2,
                background: activeSpeaker === 'ai' ? colors.primary
                            : activeSpeaker === 'user' ? '#22c55e'
                            : colors.hairline,
                animation: activeSpeaker
                  ? `wave-bar ${bar.duration}s ease-in-out ${bar.delay}s infinite alternate`
                  : 'none',
                transformOrigin: 'center',
                transform: activeSpeaker ? 'scaleY(1)' : 'scaleY(0.2)',
                transition: 'background 0.3s',
              }} />
            ))}
          </div>

          {/* 麦克风开关按钮（通话中可用） */}
          {callActive && (
            <button
              onClick={toggleMic}
              style={{
                width: 72, height: 72, borderRadius: '50%',
                border: 'none', cursor: 'pointer',
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                gap: 2,
                background: micEnabled
                  ? 'linear-gradient(135deg, #22c55e, #16a34a)'
                  : 'linear-gradient(135deg, #6b7280, #4b5563)',
                color: '#fff',
                boxShadow: micEnabled
                  ? '0 4px 20px rgba(34,197,94,0.4)'
                  : '0 2px 10px rgba(0,0,0,0.15)',
                transition: 'all 0.2s',
                position: 'relative',
              }}
              title={micEnabled ? '关闭麦克风' : '开启麦克风'}
            >
              <IconMic size={24} color="#fff" />
              <span style={{ fontSize: 10, fontWeight: 600 }}>
                {micEnabled ? '已开启' : '已静音'}
              </span>
              {!micEnabled && (
                <div style={{
                  position: 'absolute', top: '50%', left: '50%',
                  width: 60, height: 2, background: '#ef4444',
                  transform: 'translate(-50%, -50%) rotate(-45deg)',
                  borderRadius: 1,
                }} />
              )}
            </button>
          )}
          {!callActive && (
            <div style={{ fontSize: 12, color: colors['text-tertiary'] }}>
              开始对话后点击麦克风按钮启用语音输入
            </div>
          )}

          {/* 实时字幕 — 每句独立显示 */}
          {(dialogueItems.length > 0 || liveAsrText || liveChatText) && (
            <div style={{
              width: '100%', maxWidth: 500, maxHeight: 200,
              overflowY: 'auto', padding: space.md, borderRadius: radius.md,
              background: colors['surface-soft'], border: `1px solid ${colors.hairline}`,
              fontSize: 13, lineHeight: 1.7,
            }}>
              {/* 已完成条目列表 */}
              {dialogueItems.map((item, i) => (
                <div key={i} style={{
                  marginBottom: item.role === 'user' ? 6 : 0,
                  display: 'flex', alignItems: 'flex-start', gap: 6,
                }}>
                  <span style={{
                    flexShrink: 0, fontWeight: 600, fontSize: 12,
                    color: item.role === 'user' ? colors['text-tertiary'] : colors.primary,
                    minWidth: 30,
                  }}>
                    {item.role === 'user' ? '你：' : '小e：'}
                  </span>
                  <span style={{ color: colors['text-primary'], wordBreak: 'break-word' }}>
                    {item.text}
                  </span>
                </div>
              ))}
              {/* 当前实时增量文本 */}
              {liveAsrText && (
                <div style={{
                  display: 'flex', alignItems: 'flex-start', gap: 6,
                  opacity: 0.75,
                }}>
                  <span style={{
                    flexShrink: 0, fontWeight: 600, fontSize: 12,
                    color: colors['text-tertiary'], minWidth: 30,
                  }}>你：</span>
                  <span style={{ color: colors['text-primary'], wordBreak: 'break-word' }}>
                    {liveAsrText}
                    <span style={{
                      display: 'inline-block', width: 2, height: 14,
                      background: '#22c55e', marginLeft: 2,
                      animation: 'cursor-blink 0.8s step-end infinite',
                      verticalAlign: 'text-bottom',
                    }} />
                  </span>
                </div>
              )}
              {liveChatText && (
                <div style={{
                  display: 'flex', alignItems: 'flex-start', gap: 6,
                  opacity: 0.75,
                }}>
                  <span style={{
                    flexShrink: 0, fontWeight: 600, fontSize: 12,
                    color: colors.primary, minWidth: 30,
                  }}>小e：</span>
                  <span style={{ color: colors['text-primary'], wordBreak: 'break-word' }}>
                    {liveChatText}
                    <span style={{
                      display: 'inline-block', width: 2, height: 14,
                      background: colors.primary, marginLeft: 2,
                      animation: 'cursor-blink 0.8s step-end infinite',
                      verticalAlign: 'text-bottom',
                    }} />
                  </span>
                </div>
              )}
            </div>
          )}

          {/* 结束/开始 按钮 */}
          <button
            style={{
              ...btnPrimary,
              minWidth: 180, padding: '14px 32px',
              background: callActive ? colors.danger : colors.primary,
              color: '#fff', border: 'none', fontSize: 16,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              boxShadow: callActive ? '0 4px 16px rgba(220,38,38,0.3)' : '0 4px 16px rgba(91,158,111,0.3)',
            }}
            onClick={callActive ? endCall : startCall}
          >
            {callActive ? (
              <><IconStop size={18} color="#fff" /> 结束对话</>
            ) : (
              <><IconPlay size={18} color="#fff" /> 开始对话</>
            )}
          </button>

          {/* ── 评分面板 ── */}
          {evaluating && (
            <div style={{ textAlign: 'center', marginTop: space.lg }}>
              <div style={{ fontSize: 13, color: colors['text-tertiary'] }}>
                AI 正在评估对话表现...
              </div>
            </div>
          )}
          {evaluationError && (
            <div style={{
              marginTop: space.lg, padding: '10px 16px',
              background: '#fef2f2', borderRadius: radius.md,
              border: `1px solid ${colors.danger}40`,
              fontSize: 13, color: colors.danger,
            }}>
              ⚠️ 评分失败：{evaluationError}
            </div>
          )}
          {showEvaluation && evaluation && renderEvaluationPanel(evaluation)}
        </div>
      )}

      {/* 动画样式 */}
      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.7); }
          40% { opacity: 1; transform: scale(1); }
        }
        @keyframes pulse-dot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.8); }
        }
        @keyframes wave-bar {
          0% { transform: scaleY(0.15); }
          100% { transform: scaleY(1); }
        }
        @keyframes cursor-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
