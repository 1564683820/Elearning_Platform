// PPT 创建页 — 四步流程：课程信息 → 知识图谱 → 选择主题 → AI 生成 PPT
import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { teacherApi } from '../../api/teacher';
import type { ThemeItem } from '../../api/teacher';
import KnowledgeGraphEditor from '../../components/KnowledgeGraphEditor';
import type { KnowledgeGraphData } from '../../components/KnowledgeGraphEditor';
import type { KGSectionData } from '../../components/KnowledgeGraphEditor/GraphSectionList';
import StyleSelector from '../../components/StyleSelector';
import StyleRecommendation from '../../components/StyleRecommendation';
import { DEFAULT_VISUAL_STYLE } from '../../constants/visualStyles';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSecondary, btnSmall, btnSmallSecondary,
  IconArrowRight, IconBack, IconPpt, IconCheck, IconRefresh,
} from '../../design-system';

const LESSON_TYPES: Record<string, string> = {
  new_lesson: '新授课',
  review: '复习课',
  exercise: '练习课',
  conversation: '口语课',
};

const LESSON_ICONS: Record<string, string> = {
  new_lesson: 'NL', review: 'RV', exercise: 'EX', conversation: 'CN',
};

type Step = 'form' | 'editing' | 'theme' | 'generating';

const STEPS = [
  { key: 'form' as Step, label: '填写课程信息', num: 1 },
  { key: 'editing' as Step, label: '编辑知识图谱', num: 2 },
  { key: 'theme' as Step, label: '选择主题', num: 3 },
  { key: 'generating' as Step, label: '生成课件', num: 4 },
];

const STEP_DESC: Record<Step, string> = {
  form: '填写课程信息，AI 先生成知识图谱',
  editing: '审查并调整知识图谱结构，确认后选择课件外观',
  theme: '选择课件的主题风格，然后生成 PPT',
  generating: 'AI 正在根据已确认的知识图谱生成课件...',
};

// 进度条动画样式
const progressBarStyle: React.CSSProperties = {
  height: 6, background: colors['surface-soft'], borderRadius: radius.pill,
  overflow: 'hidden',
};

const progressFillStyle = (percent: number): React.CSSProperties => ({
  height: '100%', width: `${Math.min(100, Math.max(0, percent))}%`,
  background: `linear-gradient(90deg, ${colors.success}, ${green.soft})`,
  borderRadius: radius.pill, transition: 'width 0.4s ease',
});

export default function PPTCreate() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>('form');

  // Step 1 表单
  const [lessonType, setLessonType] = useState('new_lesson');
  const [title, setTitle] = useState('');
  const [subject, setSubject] = useState('');
  const [grade, setGrade] = useState('');
  const [supplement, setSupplement] = useState('');
  const [generatingKG, setGeneratingKG] = useState(false);
  const [formErrors, setFormErrors] = useState<string[]>([]);

  // Step 2 知识图谱
  const [kgData, setKgData] = useState<KnowledgeGraphData>({
    title: '', lesson_type: '', subject: '', grade: '', sections: [], status: 'draft',
  });
  const [kgId, setKgId] = useState<string | null>(null);
  const [kgError, setKgError] = useState('');
  const [kgProgress, setKgProgress] = useState(0);
  const [kgProgressMsg, setKgProgressMsg] = useState('');

  // Step 3 主题选择
  const [themes, setThemes] = useState<ThemeItem[]>([]);
  const [selectedTheme, setSelectedTheme] = useState('classic');
  const [selectedVisualStyle, setSelectedVisualStyle] = useState(DEFAULT_VISUAL_STYLE);
  const [loadingThemes, setLoadingThemes] = useState(false);

  // 从知识图谱 section 构建页面估算数组（供 StyleRecommendation 分析用）
  const estimatedPages = useMemo(() => {
    if (!kgData.sections || kgData.sections.length === 0) return [] as Record<string, unknown>[];
    const pages: Record<string, unknown>[] = [];
    // 封面
    pages.push({
      type: 'title_slide',
      content: { title: kgData.title, subtitle: `${kgData.subject || ''} · ${kgData.grade || ''}` },
    });
    // 目录页
    pages.push({
      type: 'catalog',
      content: {
        sections: kgData.sections.map((s: any) => ({
          title: s.title,
          subtopics: (s.children || []).map((c: any) => c.title),
        })),
      },
    });
    // 学习目标页
    pages.push({
      type: 'objective',
      content: {
        objectives: kgData.sections.map((s: any) => s.title),
      },
    });
    // 各章节的知识点 → 估计为 vocabulary/dialogue/grammar/practice 类型
    for (const section of kgData.sections) {
      const children = section.children || [];
      for (const child of children) {
        const childTitle = child.title || '';
        // 根据标题关键词推断类型
        let type = 'content';
        if (/word|vocabulary|单词|词汇/i.test(childTitle)) type = 'vocabulary';
        else if (/dialogue|conversation|对话/i.test(childTitle)) type = 'dialogue';
        else if (/grammar|语法/i.test(childTitle)) type = 'grammar';
        else if (/practice|exercise|练习|习题/i.test(childTitle)) type = 'practice';
        else if (/listen|听力/i.test(childTitle)) type = 'listening';
        else if (/speak|口语/i.test(childTitle)) type = 'speaking';

        pages.push({
          type,
          content: {
            title: childTitle,
            words: type === 'vocabulary' ? [{ word: childTitle }] : [],
            dialogues: type === 'dialogue' ? [{ speaker: 'A', text: childTitle }] : [],
          },
        });
      }
    }
    // 总结页
    pages.push({
      type: 'summary',
      content: {
        summary: kgData.sections.map((s: any) => s.title),
      },
    });
    return pages;
  }, [kgData]);

  // Step 4 生成 PPT
  const [generatingPpt, setGeneratingPpt] = useState(false);
  const [pptError, setPptError] = useState('');
  const [pptProgress, setPptProgress] = useState(0);
  const [pptProgressMsg, setPptProgressMsg] = useState('');

  useEffect(() => {
    if (step === 'theme') {
      const loadThemes = async () => {
        setLoadingThemes(true);
        try {
          const result = await teacherApi.ppt.listThemes();
          if (result.items?.length > 0) setThemes(result.items);
        } catch { /* use default */ } finally { setLoadingThemes(false); }
      };
      loadThemes();
    }
  }, [step]);

  const generateGraphSSE = async (options: {
    title: string; lesson_type: string; subject?: string; grade?: string; supplement?: string;
  }) => {
    setKgProgress(0); setKgProgressMsg(''); setKgError(''); setGeneratingKG(true);
    try {
      const response = await teacherApi.knowledgeGraph.generateSSE({
        ...options, expected_sections: 4, expected_nodes_per_section: 3,
      });
      if (!response.ok) {
        let errBody: any = {};
        try { errBody = await response.json(); } catch {}
        throw new Error(errBody.detail || errBody.message || `HTTP ${response.status}`);
      }
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let completed = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';
        for (const part of parts) {
          const lines = part.split('\n');
          let eventType = '', dataStr = '';
          for (const line of lines) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim();
            if (line.startsWith('data: ')) dataStr = line.slice(6);
          }
          if (!dataStr) continue;
          const data = JSON.parse(dataStr);
          if (data.type === 'progress') {
            setKgProgress(data.progress);
            setKgProgressMsg(data.message);
          } else if (data.type === 'complete') {
            completed = true;
            setKgProgress(100);
            setKgProgressMsg('知识图谱生成完成');
            const result = data.data;
            setKgId(result.id);
            setKgData({
              id: result.id, title: result.title,
              lesson_type: options.lesson_type, subject: options.subject || '',
              grade: options.grade || '',
              sections: result.content?.sections || [], status: result.status || 'draft',
            });
            setStep('editing');
          } else if (data.type === 'error') {
            throw new Error(data.message || '生成失败');
          }
        }
      }
      if (!completed) throw new Error('连接意外中断');
    } catch (e: any) {
      const errMsg = e.message || String(e) || '生成知识图谱失败';
      setKgError(errMsg);
      setKgId(null);
      setKgData({ title: '', lesson_type: '', subject: '', grade: '', sections: [], status: 'draft' });
    } finally { setGeneratingKG(false); }
  };

  // Step 1 → Step 2
  const handleGenerateGraph = async () => {
    const errors: string[] = [];
    if (!title.trim()) errors.push('请输入课程标题');
    setFormErrors(errors);
    if (errors.length > 0) return;
    await generateGraphSSE({
      title: title.trim(), lesson_type: lessonType,
      subject: subject.trim(), grade: grade.trim(), supplement: supplement.trim(),
    });
  };

  // Step 2: AI 重新生成
  const handleRegenerateGraph = async () => {
    if (!kgId) return;
    await generateGraphSSE({
      title: title.trim(), lesson_type: lessonType,
      subject: subject.trim(), grade: grade.trim(), supplement: supplement.trim(),
    });
  };

  // Step 2: 保存
  const handleSaveGraph = async () => {
    if (!kgId) return;
    try { await teacherApi.knowledgeGraph.update(kgId, { content: kgData.sections, title: kgData.title }); }
    catch (e: any) { setKgError('保存失败: ' + e.message); }
  };

  // Step 2 → Step 3
  const handleConfirmAndSelectTheme = async () => {
    if (!kgId) return;
    setPptError('');
    try {
      try { await teacherApi.knowledgeGraph.get(kgId); }
      catch { throw new Error('知识图谱数据不存在，请重新生成图谱'); }
      await teacherApi.knowledgeGraph.update(kgId, { content: kgData.sections, title: kgData.title });
      await teacherApi.knowledgeGraph.confirm(kgId);
      setStep('theme');
    } catch (e: any) { setPptError(e.message || '确认图谱失败'); }
  };

  // Step 3 → Step 4
  const handleGenerateWithTheme = async () => {
    if (!kgId) return;
    setGeneratingPpt(true); setPptError(''); setPptProgress(0);
    setPptProgressMsg('正在生成 PPT 内容...');
    try {
      await teacherApi.knowledgeGraph.get(kgId);
    } catch {
      setGeneratingPpt(false);
      setPptError('知识图谱数据不存在，请返回重新生成');
      return;
    }
    const progressTimer = setInterval(() => {
      setPptProgress(prev => prev < 55 ? prev + 5 : prev);
    }, 800);
    try {
      // Phase 3.3: 构建 spec_lock 设计规格锁定
      const specLock = {
        visual_style: selectedVisualStyle,
        theme_name: selectedTheme,
      };
      const ppt = await teacherApi.knowledgeGraph.generatePpt(
        kgId, selectedTheme, selectedVisualStyle, specLock,
      );
      clearInterval(progressTimer);
      setPptProgress(70); setPptProgressMsg('正在合成音频...');
      await new Promise(r => setTimeout(r, 500));
      setPptProgress(90); setPptProgressMsg('渲染 HTML 中...');
      await new Promise(r => setTimeout(r, 300));
      setPptProgress(100); setPptProgressMsg('PPT 生成完成');
      setStep('generating');
      setTimeout(() => { navigate(`/ppt/edit/${ppt.id}`); }, 1200);
    } catch (e: any) {
      clearInterval(progressTimer);
      setPptError(e.message || '生成 PPT 失败');
      setGeneratingPpt(false); setPptProgress(0);
    }
  };

  const handleBackToForm = () => { setStep('form'); setKgId(null); setKgError(''); };

  const stepIndex = STEPS.findIndex(s => s.key === step);
  const currentStepStep = STEPS[stepIndex];

  return (
    <div style={{ maxWidth: 840, margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: space.md }}>
        <h1 style={{ margin: 0, ...typography['display-lg'], color: colors['text-primary'] }}>
          创建备课 PPT
        </h1>
        <p style={{ margin: `${space.xs}px 0 0`, ...typography['body-sm'], color: colors['text-secondary'] }}>
          {STEP_DESC[step]}
        </p>
      </div>

      {/* 步骤指示器 — 绿色主题水波纹 */}
      <div style={{
        display: 'flex', gap: 0, marginBottom: space.lg, alignItems: 'center',
        background: colors.canvas, borderRadius: radius.lg, padding: space.sm,
        boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
      }}>
        {STEPS.map((s, i) => {
          const isActive = i === stepIndex;
          const isDone = i < stepIndex;
          return (
            <div key={s.key} style={{
              flex: 1, display: 'flex', alignItems: 'center', gap: space.xs,
              position: 'relative',
            }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: space.xs,
                opacity: isDone || isActive ? 1 : 0.45,
              }}>
                {/* 步骤圆圈 */}
                <div style={{
                  width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: isActive ? colors.success : isDone ? green.bg2 : colors['surface-soft'],
                  color: isActive ? '#fff' : isDone ? colors.success : colors['text-tertiary'],
                  fontWeight: 600, fontSize: 13,
                  transition: 'all 0.3s ease',
                  boxShadow: isActive ? `0 0 0 3px ${green.bg3}` : 'none',
                }}>
                  {isDone ? <IconCheck size={14} color={colors.success} /> : s.num}
                </div>
                {/* 步骤标签 */}
                <span style={{
                  ...typography['body-sm'], fontWeight: isActive || isDone ? 600 : 400,
                  color: isActive ? colors.success : isDone ? colors['text-primary'] : colors['text-tertiary'],
                  whiteSpace: 'nowrap',
                }}>
                  {s.label}
                </span>
              </div>
              {/* 连接线 */}
              {i < STEPS.length - 1 && (
                <div style={{
                  flex: 1, height: 2, margin: '0 8px',
                  background: isDone ? colors.success : colors.hairline,
                  borderRadius: 1, transition: 'background 0.3s',
                }} />
              )}
            </div>
          );
        })}
      </div>

      {/* 错误提示 */}
      {(kgError || pptError || formErrors.length > 0) && (
        <div style={{
          ...cardStyle, marginBottom: space.md, padding: space.sm,
          background: '#fef2f2', borderColor: colors.danger + '30',
        }}>
          {formErrors.length > 0 ? (
            formErrors.map((err, i) => (
              <div key={i} style={{ color: colors.danger, ...typography['body-sm'] }}>· {err}</div>
            ))
          ) : (
            <div style={{ color: colors.danger, ...typography['body-sm'] }}>{kgError || pptError}</div>
          )}
        </div>
      )}

      {/* Step 3: AI 生成动画 */}
      {step === 'generating' && (
        <div style={{ ...cardStyle, textAlign: 'center', padding: space.xxl }}>
          <div style={{
            width: 64, height: 64, borderRadius: '50%',
            margin: '0 auto 16px',
            background: `linear-gradient(135deg, ${colors.success}, ${green.soft})`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 28,
          }}>
            <IconPpt size={32} color="#fff" />
          </div>
          <div style={{ ...typography.subhead, fontWeight: 600, color: colors['text-primary'], marginBottom: 4 }}>
            正在根据知识图谱生成课件...
          </div>
          <div style={{ ...typography['body-sm'], color: colors['text-secondary'], marginBottom: space.lg }}>
            AI 为每个知识点生成对应的幻灯片内容
          </div>
          {/* 进度动画 */}
          <div style={{ width: '60%', margin: '0 auto' }}>
            <div style={progressBarStyle}>
              <div style={{
                height: '100%', width: '40%',
                background: `linear-gradient(90deg, ${colors.success}, ${green.soft})`,
                borderRadius: radius.pill,
                animation: 'createProgress 1.5s ease-in-out infinite',
              }} />
            </div>
            <style>{`@keyframes createProgress { 0% { transform: translateX(-100%); } 100% { transform: translateX(350%); } }`}</style>
          </div>
        </div>
      )}

      {/* Step 1: 表单 */}
      {step === 'form' && (
        <div style={{ ...cardStyle, padding: space.lg }}>
          {/* 课型选择 — 网格卡片 */}
          <label style={{
            display: 'block', ...typography.eyebrow, color: colors['text-secondary'],
            marginBottom: space.sm, textTransform: 'uppercase',
          }}>课型</label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: space.sm, marginBottom: space.lg }}>
            {Object.entries(LESSON_TYPES).map(([k, v]) => (
              <div key={k} onClick={() => setLessonType(k)} style={{
                padding: `${space.md}px ${space.xs}px`, borderRadius: radius.md, cursor: 'pointer',
                textAlign: 'center',
                border: lessonType === k ? `2px solid ${colors.success}` : `2px solid ${colors.hairline}`,
                background: lessonType === k ? green.bg3 : colors.canvas,
                fontWeight: lessonType === k ? 600 : 400,
                fontSize: 14, color: lessonType === k ? colors.success : colors['text-secondary'],
                transition: 'all 0.2s',
              }}
                onMouseEnter={(e) => { if (lessonType !== k) e.currentTarget.style.borderColor = colors.primary + '60'; }}
                onMouseLeave={(e) => { if (lessonType !== k) e.currentTarget.style.borderColor = colors.hairline; }}
              >
                <div style={{
                  width: 36, height: 36, borderRadius: '50%', margin: '0 auto 6px',
                  background: lessonType === k ? colors.success : colors['surface-soft'],
                  color: lessonType === k ? '#fff' : colors['text-secondary'],
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 700,
                }}>
                  {LESSON_ICONS[k]}
                </div>
                {v}
              </div>
            ))}
          </div>

          {/* 标题 */}
          <div style={{ marginBottom: space.md }}>
            <label style={{
              display: 'block', ...typography.eyebrow, color: colors['text-secondary'],
              marginBottom: space.xs,
            }}>课件标题 *</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：Unit 3 My Friends"
              style={{
                width: '100%', padding: '10px 14px', border: `1px solid ${colors.hairline}`,
                borderRadius: radius.md, fontSize: 14, boxSizing: 'border-box',
                color: colors['text-primary'], background: colors.canvas,
                outline: 'none', transition: 'border-color 0.15s',
              }}
              onFocus={(e) => e.currentTarget.style.borderColor = colors.primary}
              onBlur={(e) => e.currentTarget.style.borderColor = colors.hairline}
            />
          </div>

          {/* 主题 + 年级 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: space.md, marginBottom: space.md }}>
            <div>
              <label style={{
                display: 'block', ...typography.eyebrow, color: colors['text-secondary'],
                marginBottom: space.xs,
              }}>主题/单元</label>
              <input value={subject} onChange={(e) => setSubject(e.target.value)}
                placeholder="如：My Friends"
                style={{
                  width: '100%', padding: '10px 14px', border: `1px solid ${colors.hairline}`,
                  borderRadius: radius.md, fontSize: 14, boxSizing: 'border-box',
                  color: colors['text-primary'], background: colors.canvas,
                  outline: 'none', transition: 'border-color 0.15s',
                }}
                onFocus={(e) => e.currentTarget.style.borderColor = colors.primary}
                onBlur={(e) => e.currentTarget.style.borderColor = colors.hairline}
              />
            </div>
            <div>
              <label style={{
                display: 'block', ...typography.eyebrow, color: colors['text-secondary'],
                marginBottom: space.xs,
              }}>年级</label>
              <input value={grade} onChange={(e) => setGrade(e.target.value)}
                placeholder="如：三年级"
                style={{
                  width: '100%', padding: '10px 14px', border: `1px solid ${colors.hairline}`,
                  borderRadius: radius.md, fontSize: 14, boxSizing: 'border-box',
                  color: colors['text-primary'], background: colors.canvas,
                  outline: 'none', transition: 'border-color 0.15s',
                }}
                onFocus={(e) => e.currentTarget.style.borderColor = colors.primary}
                onBlur={(e) => e.currentTarget.style.borderColor = colors.hairline}
              />
            </div>
          </div>

          {/* 补充说明 */}
          <div style={{ marginBottom: space.lg }}>
            <label style={{
              display: 'block', ...typography.eyebrow, color: colors['text-secondary'],
              marginBottom: space.xs,
            }}>
              补充说明 <span style={{ fontWeight: 400, color: colors['text-tertiary'] }}>（对 AI 的额外要求）</span>
            </label>
            <textarea value={supplement} onChange={(e) => setSupplement(e.target.value)}
              placeholder="例如：重点是现在完成时的两种用法区别，学生容易混淆与一般过去时的区别"
              style={{
                width: '100%', minHeight: 80, padding: '10px 14px',
                border: `1px solid ${colors.hairline}`, borderRadius: radius.md,
                fontSize: 14, boxSizing: 'border-box', resize: 'vertical',
                fontFamily: 'inherit', color: colors['text-primary'],
                background: colors.canvas, outline: 'none',
                transition: 'border-color 0.15s',
              }}
              onFocus={(e) => e.currentTarget.style.borderColor = colors.primary}
              onBlur={(e) => e.currentTarget.style.borderColor = colors.hairline}
            />
          </div>

          {/* 按钮 / 进度条 */}
          {generatingKG ? (
            <div style={{ ...cardStyle, background: green.bg3, borderColor: colors.success + '30', padding: space.md }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: space.sm, marginBottom: space.sm }}>
                <div style={{ flex: 1, ...progressBarStyle }}>
                  <div style={progressFillStyle(kgProgress)} />
                </div>
                <span style={{ ...typography.button, color: colors.success, minWidth: 36, textAlign: 'right' }}>
                  {kgProgress}%
                </span>
              </div>
              <div style={{
                ...typography['body-sm'], color: colors.success, fontWeight: 500,
                display: 'flex', alignItems: 'center', gap: space.xs,
              }}>
                <div style={{
                  width: 12, height: 12, border: `2px solid ${colors.success}`,
                  borderTopColor: 'transparent', borderRadius: '50%',
                  animation: 'spin 0.6s linear infinite',
                }} />
                <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
                {kgProgressMsg || 'AI 正在分析课程内容...'}
              </div>
            </div>
          ) : (
            <button onClick={handleGenerateGraph} style={{
              width: '100%', ...btnPrimary, padding: '12px 24px',
              fontSize: 16, fontWeight: 600, gap: 8,
            }}>
              <IconRefresh size={16} color="#fff" />
              AI 生成知识图谱
            </button>
          )}
        </div>
      )}

      {/* Step 2: 知识图谱编辑 */}
      {step === 'editing' && (
        <div>
          {generatingKG && (
            <div style={{
              ...cardStyle, background: green.bg3, borderColor: colors.success + '30',
              marginBottom: space.md, padding: space.md,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: space.sm, marginBottom: space.xs }}>
                <div style={{ flex: 1, ...progressBarStyle }}>
                  <div style={progressFillStyle(kgProgress)} />
                </div>
                <span style={{ ...typography.button, color: colors.success, minWidth: 36, textAlign: 'right' }}>
                  {kgProgress}%
                </span>
              </div>
              <div style={{ ...typography['body-sm'], color: colors.success, fontWeight: 500 }}>
                {kgProgressMsg || 'AI 正在重新生成...'}
              </div>
            </div>
          )}
          <KnowledgeGraphEditor
            data={kgData} onChange={setKgData}
            onRegenerate={handleRegenerateGraph}
            onConfirm={handleConfirmAndSelectTheme}
            generating={generatingKG || generatingPpt}
          />
          <div style={{ display: 'flex', gap: space.sm, marginTop: space.md }}>
            <button onClick={handleBackToForm} style={{ ...btnSecondary, flex: 1, padding: '12px' }}>
              ← 返回修改课程信息
            </button>
            <button onClick={handleSaveGraph} style={{
              ...btnSecondary, flex: 1, padding: '12px',
              background: green.bg, color: colors.success, border: `1px solid ${colors.success}30`,
            }}>
              保存修改
            </button>
            <button onClick={handleConfirmAndSelectTheme}
              disabled={generatingPpt || kgData.sections.length === 0}
              style={{
                ...btnPrimary, flex: 2, padding: '12px', gap: 6,
                opacity: (generatingPpt || kgData.sections.length === 0) ? 0.5 : 1,
              }}>
              确认图谱，选择主题 <IconArrowRight size={14} color="#fff" />
            </button>
          </div>
        </div>
      )}

      {/* Step 3: 选择主题 */}
      {step === 'theme' && (
        <div>
          {/* AI 风格推荐面板 */}
          <StyleRecommendation
            pages={estimatedPages}
            onSelectStyle={(styleName) => setSelectedVisualStyle(styleName)}
          />

          <div style={{ ...cardStyle, padding: space.lg }}>
            <h3 style={{ margin: 0, ...typography.subhead, fontWeight: 600, color: colors['text-primary'], marginBottom: space.xs }}>
              选择课件主题风格
            </h3>
            <p style={{ ...typography['body-sm'], color: colors['text-tertiary'], marginBottom: space.lg }}>
              选择课件的外观风格，后续也可以在编辑器中随时切换主题
            </p>

            {loadingThemes ? (
              <div style={{ textAlign: 'center', padding: space.xxl, color: colors['text-tertiary'] }}>
                正在加载主题...
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: space.sm }}>
                {themes.map((theme) => (
                  <div key={theme.name} onClick={() => setSelectedTheme(theme.name)}
                    style={{
                      borderRadius: radius.md, cursor: 'pointer', overflow: 'hidden',
                      border: selectedTheme === theme.name ? `2px solid ${colors.success}` : `2px solid ${colors.hairline}`,
                      transition: 'all 0.2s',
                      boxShadow: selectedTheme === theme.name ? `0 2px 12px ${colors.success}30` : 'none',
                    }}
                  >
                    <div style={{
                      height: 80,
                      background: theme.preview_color || colors['surface-soft'],
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 24, fontWeight: 700, color: '#fff',
                      textShadow: '0 1px 3px rgba(0,0,0,0.3)',
                    }}>
                      {theme.name.charAt(0).toUpperCase() + theme.name.slice(1, 2)}
                    </div>
                    <div style={{
                      padding: `10px ${space.sm}px`, textAlign: 'center',
                      background: selectedTheme === theme.name ? green.bg3 : colors['surface-soft'],
                      fontWeight: selectedTheme === theme.name ? 600 : 400,
                      fontSize: 13, color: selectedTheme === theme.name ? colors.success : colors['text-primary'],
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
                    }}>
                      {theme.display_name}
                      {selectedTheme === theme.name && <IconCheck size={12} color={colors.success} />}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 视觉布局选择 */}
          <div style={{ marginTop: space.md }}>
            <StyleSelector
              value={selectedVisualStyle}
              onChange={setSelectedVisualStyle}
              title="选择视觉布局"
              description="决定卡片形状、装饰元素、排版风格和留白间距"
            />
          </div>

          {/* 图谱 → PPT 映射预览 */}
          {kgData.sections.length > 0 && (
            <div style={{
              ...cardStyle, marginTop: space.md,
              background: 'linear-gradient(135deg, #f0fdf4, #ecfdf5)',
              borderColor: colors.success + '20',
            }}>
              <div style={{
                ...typography['body-sm'], fontWeight: 600, color: colors.success,
                marginBottom: space.sm, display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <IconPpt size={14} color={colors.success} />
                知识图谱 → PPT 映射预览
                <span style={{ ...typography.caption, color: colors['text-tertiary'], fontWeight: 400 }}>
                  （每个知识点将生成 1-2 张幻灯片）
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {kgData.sections.map((sec: any, si: number) => {
                  const childCount = sec.children?.length || 0;
                  const estSlides = Math.round(childCount * 1.5);
                  return (
                    <div key={si} style={{
                      display: 'flex', alignItems: 'center', gap: 8, ...typography['body-sm'],
                      padding: `6px ${space.sm}px`, borderRadius: radius.sm,
                      background: colors.canvas, border: `1px solid ${colors.success}20`,
                    }}>
                      <div style={{
                        width: 24, height: 24, borderRadius: '50%', flexShrink: 0,
                        background: green.bg3, display: 'flex', alignItems: 'center',
                        justifyContent: 'center', color: colors.success, fontWeight: 700, fontSize: 11,
                      }}>
                        {si + 1}
                      </div>
                      <span style={{ flex: 1, color: colors['text-primary'], fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {sec.title}
                      </span>
                      <span style={{ color: colors['text-tertiary'], fontSize: 12, whiteSpace: 'nowrap' }}>
                        {childCount} 知识点
                      </span>
                      <span style={{
                        padding: '2px 8px', borderRadius: radius.pill, fontSize: 11, fontWeight: 600,
                        background: green.bg3, color: colors.success, whiteSpace: 'nowrap',
                      }}>
                        约 {estSlides} 张幻灯片
                      </span>
                    </div>
                  );
                })}
              </div>
              <div style={{
                marginTop: space.xs, ...typography['body-sm'], color: colors['text-tertiary'],
                padding: `${space.xs}px ${space.sm}px`, background: colors.canvas,
                borderRadius: radius.sm, border: `1px dashed ${colors.hairline}`,
              }}>
                <strong style={{ color: colors['text-secondary'] }}>生成说明：</strong>
                AI 将严格按照知识图谱的章节和知识点顺序生成幻灯片。第一页为封面，最后为总结页，中间为各知识点教学页。
              </div>
            </div>
          )}

          {/* 错误和进度 */}
          {pptError && (
            <div style={{
              ...cardStyle, marginTop: space.sm,
              background: '#fef2f2', borderColor: colors.danger + '30',
            }}>
              <div style={{ color: colors.danger, ...typography['body-sm'] }}>{pptError}</div>
            </div>
          )}

          {generatingPpt && (
            <div style={{ ...cardStyle, marginTop: space.md, background: green.bg3, borderColor: colors.success + '30' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: space.sm, marginBottom: space.xs }}>
                <div style={{ flex: 1, ...progressBarStyle }}>
                  <div style={progressFillStyle(pptProgress)} />
                </div>
                <span style={{ ...typography.button, color: colors.success, minWidth: 36, textAlign: 'right' }}>
                  {pptProgress}%
                </span>
              </div>
              {pptProgressMsg && (
                <div style={{ ...typography['body-sm'], color: colors.success, fontWeight: 500 }}>
                  {pptProgressMsg}
                </div>
              )}
            </div>
          )}

          <div style={{ display: 'flex', gap: space.sm, marginTop: space.md }}>
            <button onClick={() => setStep('editing')} disabled={generatingPpt}
              style={{
                ...btnSecondary, flex: 1, padding: '12px',
                opacity: generatingPpt ? 0.5 : 1,
              }}>
              ← 返回修改知识图谱
            </button>
            <button onClick={handleGenerateWithTheme} disabled={generatingPpt || !selectedTheme}
              style={{
                ...btnPrimary, flex: 2, padding: '12px', gap: 6,
                opacity: (generatingPpt || !selectedTheme) ? 0.5 : 1,
              }}>
              {generatingPpt ? (
                <>生成中...</>
              ) : (
                <>使用 "{themes.find(t => t.name === selectedTheme)?.display_name || selectedTheme}" 生成 PPT <IconArrowRight size={14} color="#fff" /></>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
