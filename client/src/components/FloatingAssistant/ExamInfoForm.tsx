// 试卷信息填写表单 — 当用户说出卷但未提供具体信息时弹出
// 直接调用 API 生成试卷，成功后返回跳转链接
import { useState, useEffect, useRef } from 'react';
import { teacherApi, ClassData } from '../../api/teacher';
import { teachingAssistantApi } from '../../api/teachingAssistant';
import GenerationProgress, { GenerationProgressStream } from './GenerationProgress';
import type { GenStatus } from './GenerationProgress';

interface ExamInfoFormProps {
  onCancel: () => void;
  onSuccess: (examId: number) => void;
}

// 可用题型定义
const EXAM_Q_TYPES: { key: string; label: string }[] = [
  { key: 'choice', label: '选择题' },
  { key: 'fill', label: '填空题' },
  { key: 'judge', label: '判断题' },
  { key: 'translation', label: '翻译题' },
  { key: 'reading', label: '阅读理解' },
  { key: 'writing', label: '写作题' },
  { key: 'listening', label: '听力题' },
  { key: 'cloze', label: '完形填空' },
  { key: 'seven_choice', label: '七选五' },
  { key: 'grammar_fill', label: '语法填空' },
  { key: 'error_correction', label: '短文改错' },
  { key: 'answer', label: '简答题' },
  { key: 'applied_writing', label: '应用写作' },
  { key: 'continuation_writing', label: '读后续写' },
];

// 年级 → 题型配置（与出卷页保持一致，初中统一中考题型，高中统一高考题型）
const GRADE_QUESTION_CONFIG: Record<string, { types: string[]; defaults: Record<string, number> }> = {
  // ── 小学：校内阶段测试 ──
  '三年级': { types: ['choice', 'fill', 'reading', 'writing'], defaults: { choice: 8, fill: 5, reading: 1, writing: 1 } },
  '四年级': { types: ['choice', 'fill', 'reading', 'writing'], defaults: { choice: 10, fill: 5, reading: 1, writing: 1 } },
  '五年级': { types: ['choice', 'fill', 'reading', 'writing'], defaults: { choice: 10, fill: 8, reading: 2, writing: 1 } },
  '六年级': { types: ['choice', 'fill', 'reading', 'writing'], defaults: { choice: 10, fill: 8, reading: 2, writing: 1 } },
  // ── 初中（中考，三个年级题型一致）──
  '七年级': { types: ['choice', 'cloze', 'reading', 'fill', 'writing'], defaults: { choice: 15, cloze: 1, reading: 3, fill: 1, writing: 1 } },
  '八年级': { types: ['choice', 'cloze', 'reading', 'fill', 'writing'], defaults: { choice: 15, cloze: 1, reading: 3, fill: 1, writing: 1 } },
  '九年级': { types: ['choice', 'cloze', 'reading', 'fill', 'writing'], defaults: { choice: 15, cloze: 1, reading: 3, fill: 1, writing: 1 } },
  // ── 高中（高考新课标Ⅰ卷，三个年级题型一致）──
  '高一': { types: ['reading', 'seven_choice', 'cloze', 'grammar_fill', 'applied_writing', 'continuation_writing'], defaults: { reading: 4, seven_choice: 1, cloze: 1, grammar_fill: 1, applied_writing: 1, continuation_writing: 1 } },
  '高二': { types: ['reading', 'seven_choice', 'cloze', 'grammar_fill', 'applied_writing', 'continuation_writing'], defaults: { reading: 4, seven_choice: 1, cloze: 1, grammar_fill: 1, applied_writing: 1, continuation_writing: 1 } },
  '高三': { types: ['reading', 'seven_choice', 'cloze', 'grammar_fill', 'applied_writing', 'continuation_writing'], defaults: { reading: 4, seven_choice: 1, cloze: 1, grammar_fill: 1, applied_writing: 1, continuation_writing: 1 } },
  // ── 大学四六级 ──
  '四级': { types: ['writing', 'reading', 'translation', 'cloze', 'choice', 'seven_choice', 'fill'], defaults: { writing: 1, reading: 3, translation: 1, cloze: 1, choice: 10, seven_choice: 1, fill: 1 } },
  '六级': { types: ['writing', 'reading', 'translation', 'cloze', 'choice', 'seven_choice', 'fill'], defaults: { writing: 1, reading: 3, translation: 1, cloze: 1, choice: 10, seven_choice: 1, fill: 1 } },
};

type Difficulty = '简单' | '中等' | '困难';

export default function ExamInfoForm({ onCancel, onSuccess }: ExamInfoFormProps) {
  const [title, setTitle] = useState('');
  const [tagInput, setTagInput] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [grade, setGrade] = useState('');
  const [difficulty, setDifficulty] = useState<Difficulty>('中等');
  const [duration, setDuration] = useState('60');
  const [qMode, setQMode] = useState<'standard' | 'custom'>('standard');
  const [qTypeCounts, setQTypeCounts] = useState<Record<string, number>>({});
  const [references, setReferences] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showingProgress, setShowingProgress] = useState(false);
  const [genStatus, setGenStatus] = useState<GenStatus>('idle');
  const [activeSkillName, setActiveSkillName] = useState('');
  const [genStreamText, setGenStreamText] = useState('');
  const [uploadedExamId, setUploadedExamId] = useState<number | null>(null);
  const genTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 按题型并行生成进度
  const [parallelTypes, setParallelTypes] = useState<{ qtype: string; label: string; count: number }[]>([]);
  const [parallelResults, setParallelResults] = useState<Record<string, { label: string; count: number; status: 'pending' | 'generating' | 'success' | 'error'; error?: string }>>({});
  const [parallelSuccess, setParallelSuccess] = useState(false);
  const [parallelError, setParallelError] = useState('');

  // 常规考试模式：年级变化时自动填充题型
  useEffect(() => {
    if (qMode === 'standard' && grade && GRADE_QUESTION_CONFIG[grade]) {
      setQTypeCounts({ ...GRADE_QUESTION_CONFIG[grade].defaults });
    }
  }, [qMode, grade]);

  // 添加知识点标签
  const handleTagKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const val = tagInput.trim();
      if (val && !tags.includes(val)) {
        setTags(prev => [...prev, val]);
      }
      setTagInput('');
    }
  };
  const removeTag = (tag: string) => setTags(prev => prev.filter(t => t !== tag));

  // 题型数量变更
  const handleQTypeCount = (key: string, val: string) => {
    const num = parseInt(val, 10);
    if (isNaN(num) || num < 0) return;
    setQTypeCounts(prev => ({ ...prev, [key]: num }));
  };

  // 难度映射到后端数值
  const difficultyToNumber: Record<string, number> = { '简单': 1, '中等': 2, '困难': 3 };

  // 直接调用 API 生成试卷（班级在发布时选择，生成不需要）
  const handleSubmit = async () => {
    if (!title.trim()) { setError('请输入试卷名称'); return; }

    const hasAnyQuestion = Object.values(qTypeCounts).some(c => c > 0);
    if (!hasAnyQuestion) { setError('请至少设置一种题型的题量'); return; }

    setLoading(true);
    setError('');
    setShowingProgress(true);
    setGenStatus('idle');
    setGenStreamText('');

    // 1. 获取激活的 exam 技能名称
    let skillName = '';
    try {
      const skillData = await teachingAssistantApi.getActiveSkill('exam');
      if (skillData && skillData.items && skillData.items.length > 0) {
        skillName = skillData.items[0].name;
      }
    } catch { /* 忽略 */ }
    setActiveSkillName(skillName || '试卷设计');
    setGenStatus('skill_invoked');

    // 2. 短暂展示技能调用成功
    await new Promise(r => setTimeout(r, 1200));
    setGenStatus('generating');

    // 判断是否需要使用流式并行生成
    const activeTypes = Object.entries(qTypeCounts).filter(([, c]) => c > 0);
    const useStreaming = activeTypes.length > 1;

    if (useStreaming) {
      // 流式并行生成 (方案 A)
      const typeEntries = activeTypes.map(([qtype, count]) => ({
        qtype,
        label: EXAM_Q_TYPES.find(t => t.key === qtype)?.label || qtype,
        count,
      }));
      setParallelTypes(typeEntries);
      const initResults: Record<string, any> = {};
      typeEntries.forEach(t => {
        initResults[t.qtype] = { label: t.label, count: t.count, status: 'pending' };
      });
      setParallelResults(initResults);

      try {
        const response = await teacherApi.generateExamStream({
          title: title.trim(),
          difficulty: difficultyToNumber[difficulty] || 2,
          duration_minutes: Number(duration) || 60,
          grade: grade || undefined,
          knowledge_points: tags.length > 0 ? tags : undefined,
          question_type_counts: qTypeCounts,
          question_types: activeTypes.map(([k]) => k),
          question_count: activeTypes.reduce((s, [, c]) => s + c, 0),
          additional_references: references || undefined,
        });

        if (!response.ok) {
          const errText = await response.text();
          throw new Error(errText || `HTTP ${response.status}`);
        }

        const eventStream = response.body?.getReader();
        if (!eventStream) throw new Error('无法读取响应流');

        const decoder = new TextDecoder();
        let buffer = '';
        let finalExamId: number | null = null;

        while (true) {
          const { done, value } = await eventStream.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const event = JSON.parse(line.slice(6));

              if (event.type === 'type_start') {
                setParallelResults(prev => ({
                  ...prev,
                  [event.qtype]: { ...prev[event.qtype], status: 'generating' },
                }));
                setGenStreamText(prev => prev + `▶ 开始生成${event.label}...\n`);
              } else if (event.type === 'type_done') {
                setParallelResults(prev => ({
                  ...prev,
                  [event.qtype]: { ...prev[event.qtype], status: 'success' },
                }));
                setGenStreamText(prev => prev + `✓ ${event.label}完成\n`);
              } else if (event.type === 'type_error') {
                setParallelResults(prev => ({
                  ...prev,
                  [event.qtype]: { ...prev[event.qtype], status: 'error', error: event.error },
                }));
                setGenStreamText(prev => prev + `✕ ${event.label}失败\n`);
              } else if (event.type === 'exam_done') {
                finalExamId = event.data?.id || event.data?.exam_id || null;
                setGenStreamText(prev => prev + '\n✅ 试卷生成完成！');
                if (finalExamId) {
                  setUploadedExamId(finalExamId);
                  setGenStatus('success');
                  setParallelSuccess(true);
                  setTimeout(() => {
                    setLoading(false);
                    setShowingProgress(false);
                    onSuccess(finalExamId!);
                  }, 1500);
                } else {
                  setGenStreamText(prev => prev + '\n⚠️ 返回数据异常');
                  setTimeout(() => {
                    setError('生成试卷失败，返回数据异常');
                    setShowingProgress(false);
                    setLoading(false);
                  }, 1000);
                }
              } else if (event.type === 'error') {
                throw new Error(event.message || '生成失败');
              }
            } catch { /* 忽略解析错误 */ }
          }
        }
      } catch (err: any) {
        setGenStreamText(prev => prev + `\n❌ 失败：${err?.message || '生成失败'}`);
        setParallelError(err?.message || '生成失败');
        setTimeout(() => {
          setError(err?.message || '生成试卷失败，请重试');
          setShowingProgress(false);
          setLoading(false);
        }, 2000);
      }
      return;
    }

    // 单题型/旧版：使用非流式路径
    const progressMsgs = [
      '正在解析试卷参数...',
      '正在生成题目内容...',
      '正在排版试卷格式...',
      '即将完成...',
    ];
    let msgIdx = 0;
    genTimerRef.current = setInterval(() => {
      if (msgIdx < progressMsgs.length) {
        setGenStreamText(prev => prev + progressMsgs[msgIdx] + '\n');
        msgIdx++;
      } else {
        if (genTimerRef.current) clearInterval(genTimerRef.current);
      }
    }, 800);

    try {
      const data = await teacherApi.generateExam({
        title: title.trim(),
        difficulty: difficultyToNumber[difficulty] || 2,
        duration_minutes: Number(duration) || 60,
        grade: grade || undefined,
        knowledge_points: tags.length > 0 ? tags : undefined,
        question_type_counts: qTypeCounts,
        question_types: activeTypes.map(([k]) => k),
        question_count: activeTypes.reduce((s, [, c]) => s + c, 0),
        additional_references: references || undefined,
      });
      const examId = (data as any)?.id || (data as any)?.exam_id;
      if (genTimerRef.current) clearInterval(genTimerRef.current);
      setGenStreamText(prev => prev + '\n✅ 生成完成！');
      if (examId) {
        setUploadedExamId(examId);
        setGenStatus('success');
        setTimeout(() => {
          setLoading(false);
          setShowingProgress(false);
          onSuccess(examId);
        }, 1500);
      } else {
        setGenStreamText(prev => prev + '\n⚠️ 返回数据异常');
        setTimeout(() => {
          setError('生成试卷失败，返回数据异常');
          setShowingProgress(false);
          setLoading(false);
        }, 1000);
      }
    } catch (err: any) {
      if (genTimerRef.current) clearInterval(genTimerRef.current);
      setGenStreamText(prev => prev + `\n❌ 失败：${err?.message || '生成试卷失败'}`);
      setTimeout(() => {
        setError(err?.message || '生成试卷失败，请重试');
        setShowingProgress(false);
        setLoading(false);
      }, 1000);
    }
  };

  // 展示进度时渲染 GenerationProgress
  if (showingProgress) {
    const examLink = genStatus === 'success' ? `/exams/create?id=${uploadedExamId}` : undefined;
    // 多题型使用流式并行进度视图
    if (parallelTypes.length > 1 && (genStatus === 'generating' || genStatus === 'success' || genStatus === 'error')) {
      return (
        <GenerationProgressStream
          types={parallelTypes}
          typeResults={parallelResults}
          streamText={genStreamText}
          error={parallelError}
          success={parallelSuccess}
          successUrl={examLink}
          successLabel="点击查看试卷"
        />
      );
    }
    return (
      <GenerationProgress
        status={genStatus}
        skillName={activeSkillName}
        skillTypeLabel="试卷"
        successUrl={examLink}
        successLabel="点击查看试卷"
        streamText={genStreamText}
      />
    );
  }

  return (
    <div style={cardStyle}>
      {/* 头部 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <span style={{ fontSize: 18 }}>📝</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#1a2e1a' }}>出卷信息</span>
        <span style={{ fontSize: 11, color: '#6b7280' }}>AI 直接生成试卷</span>
      </div>

      {/* 表单字段 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 380, overflowY: 'auto', paddingRight: 4 }}>

        {/* 试卷名称 */}
        <div>
          <label style={labelStyle}>试卷名称 <span style={{ color: '#dc2626' }}>*</span></label>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="例如：现在进行时专项练习、期中考试..."
            style={inputStyle}
          />
        </div>

        {/* 年级 & 难度 & 时长 一行 */}
        <div style={{ display: 'flex', gap: 8 }}>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>年级 <span style={{ color: '#dc2626' }}>*</span></label>
            <select value={grade} onChange={e => setGrade(e.target.value)} style={inputStyle}>
              <option value="">请选择</option>
              {Object.keys(GRADE_QUESTION_CONFIG).map(g => (
                <option key={g} value={g}>{g}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>难度</label>
            <select value={difficulty} onChange={e => setDifficulty(e.target.value as Difficulty)} style={inputStyle}>
              <option value="简单">简单</option>
              <option value="中等">中等</option>
              <option value="困难">困难</option>
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>时长(分钟)</label>
            <input
              type="number"
              min="10"
              max="180"
              value={duration}
              onChange={e => setDuration(e.target.value)}
              style={inputStyle}
            />
          </div>
        </div>

        {/* 题型模式切换 */}
        <div>
          <label style={labelStyle}>题型设置 <span style={{ color: '#dc2626' }}>*</span></label>
          <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
            <button onClick={() => {
              setQMode('standard');
              if (grade && GRADE_QUESTION_CONFIG[grade]) {
                setQTypeCounts({ ...GRADE_QUESTION_CONFIG[grade].defaults });
              }
            }} style={{
              flex: 1, padding: '6px 0', borderRadius: 50, fontSize: 11, fontWeight: 500,
              border: `1.5px solid ${qMode === 'standard' ? '#2d7d46' : '#e2e8f0'}`,
              background: qMode === 'standard' ? '#2d7d46' : '#fff',
              color: qMode === 'standard' ? '#fff' : '#6b7280', cursor: 'pointer',
            }}>
              常规考试
            </button>
            <button onClick={() => setQMode('custom')} style={{
              flex: 1, padding: '6px 0', borderRadius: 50, fontSize: 11, fontWeight: 500,
              border: `1.5px solid ${qMode === 'custom' ? '#2d7d46' : '#e2e8f0'}`,
              background: qMode === 'custom' ? '#2d7d46' : '#fff',
              color: qMode === 'custom' ? '#fff' : '#6b7280', cursor: 'pointer',
            }}>
              自定义题型
            </button>
          </div>
        </div>

        {/* 题型选择 */}
        <div>
          {!grade ? (
            <p style={{ fontSize: 11, color: '#9ca3af', margin: 0 }}>请先选择年级</p>
          ) : qMode === 'standard' && grade && GRADE_QUESTION_CONFIG[grade] ? (
            /* 常规考试模式：只读展示题型与数量 */
            <div>
              <label style={{ ...labelStyle, marginBottom: 3 }}>试卷题型（自动匹配）</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {Object.entries(GRADE_QUESTION_CONFIG[grade].defaults).filter(([, c]) => c > 0).map(([type, count]) => {
                  const qt = EXAM_Q_TYPES.find(t => t.key === type);
                  return (
                    <span key={type} style={{
                      display: 'inline-flex', alignItems: 'center', gap: 3,
                      padding: '3px 10px', borderRadius: 50,
                      border: '1px solid #88c8a0', background: '#e6f7e6',
                      fontSize: 11, color: '#2d7d46', fontWeight: 500,
                    }}>
                      {qt?.label || type}
                      <span style={{ fontSize: 10, color: '#3d7a4e' }}>×{count}</span>
                    </span>
                  );
                })}
              </div>
            </div>
          ) : (
            /* 自定义题型模式：显示年级对应题型，可调数量 */
            <div>
              <label style={{ ...labelStyle, marginBottom: 3 }}>题型及题量</label>
              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr',
                gap: '4px 8px',
              }}>
                {(GRADE_QUESTION_CONFIG[grade]?.types || Object.keys(GRADE_QUESTION_CONFIG).length > 0 ? Object.values(GRADE_QUESTION_CONFIG)[0].types : []).map((type) => {
                  const qt = EXAM_Q_TYPES.find(t => t.key === type);
                  return (
                    <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <label style={{
                        fontSize: 11, color: '#4b5563', whiteSpace: 'nowrap',
                        minWidth: 36, flexShrink: 0,
                      }}>
                        {qt?.label || type}
                      </label>
                      <input
                        type="number"
                        min="0"
                        max="50"
                        value={qTypeCounts[type] ?? ''}
                        onChange={e => handleQTypeCount(type, e.target.value)}
                        placeholder="0"
                        style={{
                          flex: 1, width: 0, minWidth: 20, padding: '3px 4px',
                          border: '1px solid #e2e8f0', borderRadius: 4,
                          fontSize: 11, textAlign: 'center', outline: 'none',
                        }}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* 知识点标签 */}
        <div>
          <label style={labelStyle}>知识点（回车添加）</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, margin: '4px 0' }}>
            {tags.map(tag => (
              <span key={tag} style={{
                display: 'inline-flex', alignItems: 'center', gap: 3,
                padding: '2px 8px', borderRadius: 50,
                background: '#e6f7e6', color: '#2d7d46', fontSize: 11,
              }}>
                {tag}
                <span onClick={() => removeTag(tag)}
                  style={{ cursor: 'pointer', opacity: 0.6, fontSize: 13, lineHeight: 1 }}>×</span>
              </span>
            ))}
            <input
              value={tagInput}
              onChange={e => setTagInput(e.target.value)}
              onKeyDown={handleTagKeyDown}
              placeholder="输入知识点，回车添加"
              style={{
                flex: 1, minWidth: 80, border: 'none', outline: 'none',
                fontSize: 12, color: '#6b7280', background: 'transparent',
              }}
            />
          </div>
        </div>

        {/* 补充说明 */}
        <div>
          <label style={labelStyle}>补充要求（可选，如教材版本、考察侧重点）</label>
          <textarea
            value={references}
            onChange={e => setReferences(e.target.value)}
            placeholder="例如：重点考察现在进行时的动词ing变化规则..."
            rows={2}
            style={{
              ...inputStyle,
              resize: 'vertical',
              minHeight: 36,
              fontFamily: 'inherit',
              lineHeight: 1.5,
            }}
          />
        </div>
      </div>

      {error && <div style={{ fontSize: 12, color: '#dc2626', marginTop: 8 }}>{error}</div>}

      {/* 操作按钮 */}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button onClick={onCancel} disabled={loading} style={btnSecondary}>取消</button>
        <button
          onClick={handleSubmit}
          disabled={loading}
          style={{
            ...btnPrimary,
            background: loading ? '#d4edda' : '#2d7d46',
            color: loading ? '#88c8a0' : '#fff',
            cursor: loading ? 'default' : 'pointer',
          }}
        >
          {loading ? 'AI 正在生成...' : 'AI 生成试卷'}
        </button>
      </div>
    </div>
  );
}

// ========== 共享样式 ==========

const cardStyle: React.CSSProperties = {
  background: '#f8faf8',
  border: '1px solid #d4edda',
  borderRadius: 12,
  padding: 16,
  marginBottom: 12,
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  fontWeight: 500,
  color: '#6b7280',
  marginBottom: 2,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '7px 10px',
  border: '1px solid #e2e8f0',
  borderRadius: 6,
  fontSize: 12,
  color: '#1a2e1a',
  background: '#fff',
  outline: 'none',
  boxSizing: 'border-box',
};

const btnSecondary: React.CSSProperties = {
  flex: 1, padding: '8px 0', borderRadius: 50,
  border: '1px solid #e2e8f0',
  background: '#fff', color: '#6b7280',
  fontSize: 12, cursor: 'pointer',
};

const btnPrimary: React.CSSProperties = {
  flex: 2, padding: '8px 0', borderRadius: 50,
  border: 'none',
  fontSize: 12, fontWeight: 500,
};
