// PPT 信息填写 + 大纲编辑 + 主题选择 多步骤表单
import { useState, useCallback, useEffect, useRef } from 'react';
import { teacherApi } from '../../api/teacher';
import { teachingAssistantApi } from '../../api/teachingAssistant';
import GenerationProgress from './GenerationProgress';
import type { GenStatus } from './GenerationProgress';
import StyleSelector from '../StyleSelector';
import { DEFAULT_VISUAL_STYLE } from '../../constants/visualStyles';

interface PptInfoFormProps {
  onSuccess: (pptId: number) => void;
  onCancel: () => void;
}

type LessonTypeKey = 'new_lesson' | 'review' | 'exercise' | 'conversation';
type ThemeName = 'classic' | 'cartoon' | 'academic' | 'senior';

const LESSON_TYPES: { key: LessonTypeKey; label: string }[] = [
  { key: 'new_lesson', label: '新授课' },
  { key: 'review', label: '复习课' },
  { key: 'exercise', label: '练习课' },
  { key: 'conversation', label: '口语课' },
];

const THEMES: { name: ThemeName; label: string; color: string; desc: string }[] = [
  { name: 'classic', label: '经典简约', color: '#2d7d46', desc: '蓝白清新，适合日常教学' },
  { name: 'cartoon', label: '小学卡通', color: '#f59e0b', desc: '明亮活泼，适合低年级' },
  { name: 'academic', label: '清新学术', color: '#3b82f6', desc: '简约清晰，适合初中' },
  { name: 'senior', label: '深色严谨', color: '#1e293b', desc: '沉稳专业，适合高中' },
];

interface Section {
  id: string;
  title: string;
  subtopics: string[];
}

let sectionIdCounter = 0;
const newId = () => `sec_${++sectionIdCounter}_${Date.now()}`;

export default function PptInfoForm({ onSuccess, onCancel }: PptInfoFormProps) {
  // Step 1: 基本信息
  const [title, setTitle] = useState('');
  const [tagInput, setTagInput] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [grade, setGrade] = useState('');
  const [lessonType, setLessonType] = useState<LessonTypeKey>('new_lesson');

  // Step 2: 大纲 & 主题
  const [sections, setSections] = useState<Section[]>([]);
  const [selectedTheme, setSelectedTheme] = useState<ThemeName>('classic');
  const [selectedVisualStyle, setSelectedVisualStyle] = useState(DEFAULT_VISUAL_STYLE);

  // 步骤控制
  const [step, setStep] = useState<'form' | 'outline' | 'generating'>('form');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 生成进度
  const [genStatus, setGenStatus] = useState<GenStatus>('idle');
  const [activeSkillName, setActiveSkillName] = useState('');
  const [genStreamText, setGenStreamText] = useState('');
  const genTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Step 1: 添加知识点标签
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

  // Step 1: 生成大纲
  const handleGenerateOutline = useCallback(async () => {
    if (!title.trim()) { setError('请输入PPT主题/名称'); return; }
    setLoading(true);
    setError('');
    try {
      const data = await teacherApi.ppt.generateOutline({
        title: title.trim(),
        lesson_type: lessonType,
        grade: grade || undefined,
        knowledge_points: tags.length > 0 ? tags : undefined,
      });
      const rawSections = (data as any)?.sections || [];
      setSections(rawSections.map((s: any) => ({
        id: newId(),
        title: s.title || '',
        subtopics: (s.subtopics || []).map((st: string) => st),
      })));
      setStep('outline');
    } catch (err: any) {
      setError(err?.message || '生成大纲失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [title, lessonType, grade, tags]);

  // Step 2: 大纲编辑
  const updateSectionTitle = (id: string, val: string) => {
    setSections(prev => prev.map(s => s.id === id ? { ...s, title: val } : s));
  };
  const updateSubtopic = (secId: string, idx: number, val: string) => {
    setSections(prev => prev.map(s =>
      s.id === secId ? { ...s, subtopics: s.subtopics.map((st, i) => i === idx ? val : st) } : s
    ));
  };
  const addSubtopic = (secId: string) => {
    setSections(prev => prev.map(s =>
      s.id === secId ? { ...s, subtopics: [...s.subtopics, ''] } : s
    ));
  };
  const removeSubtopic = (secId: string, idx: number) => {
    setSections(prev => prev.map(s =>
      s.id === secId ? { ...s, subtopics: s.subtopics.filter((_, i) => i !== idx) } : s
    ));
  };
  const addSection = () => {
    setSections(prev => [...prev, { id: newId(), title: '', subtopics: [''] }]);
  };
  const removeSection = (id: string) => {
    setSections(prev => prev.filter(s => s.id !== id));
  };

  // Step 2: 生成完整 PPT
  const handleGeneratePpt = useCallback(async () => {
    const validSections = sections.filter(s => s.title.trim());
    if (validSections.length === 0) { setError('请至少保留一个章节标题'); return; }
    setError('');
    setStep('generating');
    setGenStatus('idle');
    setGenStreamText('');

    // 1. 获取激活的 PPT 技能名称
    let skillName = '';
    try {
      const skillData = await teachingAssistantApi.getActiveSkill('ppt');
      if (skillData && skillData.items && skillData.items.length > 0) {
        skillName = skillData.items[0].name;
      }
    } catch { /* 忽略，没有激活技能也能正常生成 */ }
    setActiveSkillName(skillName);
    setGenStatus('skill_invoked');

    // 2. 模拟 1.5 秒后进入生成状态（让技能调用提示可见）
    await new Promise(r => setTimeout(r, 1500));
    setGenStatus('generating');

    // 模拟实时输出
    const progressMsgs = [
      '正在解析大纲结构...',
      '正在为每个章节生成内容...',
      '正在应用幻灯片主题...',
      '正在生成排版与配色...',
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

    // 3. 调用 API
    try {
      const result = await teacherApi.ppt.generateFromOutline({
        title: title.trim(),
        lesson_type: lessonType,
        grade: grade || undefined,
        knowledge_points: tags.length > 0 ? tags : undefined,
        sections: validSections.map(s => ({
          title: s.title.trim(),
          subtopics: s.subtopics.filter(st => st.trim()),
        })),
        theme_name: selectedTheme,
        visual_style: selectedVisualStyle,
      });
      const pptId = result?.id;
      if (genTimerRef.current) clearInterval(genTimerRef.current);
      setGenStreamText(prev => prev + '\n✅ 生成完成！');
      if (pptId) {
        // 短暂展示成功状态后跳转
        setGenStatus('success');
        setTimeout(() => onSuccess(pptId), 1500);
      } else {
        setGenStreamText(prev => prev + '\n⚠️ 返回数据异常');
        setTimeout(() => {
          setError('生成PPT失败，请重试');
          setStep('outline');
        }, 1000);
      }
    } catch (err: any) {
      if (genTimerRef.current) clearInterval(genTimerRef.current);
      setGenStreamText(prev => prev + `\n❌ 失败：${err?.message || '生成PPT失败'}`);
      setTimeout(() => {
        setError(err?.message || '生成PPT失败');
        setStep('outline');
      }, 1000);
    }
  }, [title, lessonType, grade, tags, sections, selectedTheme, onSuccess]);

  // 回到表单步骤
  const backToForm = () => {
    setStep('form');
    setError('');
  };

  // ========== Step 1: 基本信息表单 ==========
  if (step === 'form') {
    return (
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <span style={{ fontSize: 18 }}>📊</span>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#1a2e1a' }}>制作 PPT 课件</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* PPT 主题 */}
          <div>
            <label style={labelStyle}>PPT 主题 <span style={{ color: '#dc2626' }}>*</span></label>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="例如：现在进行时、定语从句..."
              style={inputStyle}
            />
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
                style={{ flex: 1, minWidth: 80, border: 'none', outline: 'none', fontSize: 12, color: '#6b7280', background: 'transparent' }}
              />
            </div>
          </div>
          {/* 年级 */}
          <div>
            <label style={labelStyle}>适合年级</label>
            <select value={grade} onChange={e => setGrade(e.target.value)} style={inputStyle}>
              <option value="">请选择</option>
              <option value="小学">小学</option>
              <option value="初中">初中</option>
              <option value="高中">高中</option>
            </select>
          </div>
          {/* 课型 */}
          <div>
            <label style={labelStyle}>课型</label>
            <select value={lessonType} onChange={e => setLessonType(e.target.value as LessonTypeKey)} style={inputStyle}>
              {LESSON_TYPES.map(lt => (
                <option key={lt.key} value={lt.key}>{lt.label}</option>
              ))}
            </select>
          </div>
        </div>
        {error && <div style={{ fontSize: 12, color: '#dc2626', marginTop: 8 }}>{error}</div>}
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <button onClick={onCancel} style={btnSecondary}>取消</button>
          <button onClick={handleGenerateOutline} disabled={loading}
            style={{
              ...btnPrimary,
              background: loading ? '#d4edda' : '#2d7d46',
              color: loading ? '#88c8a0' : '#fff',
              cursor: loading ? 'default' : 'pointer',
            }}>
            {loading ? 'AI 正在生成大纲...' : 'AI 生成大纲'}
          </button>
        </div>
      </div>
    );
  }

  // ========== Step 2: 大纲编辑 + 主题选择 ==========
  if (step === 'outline') {
    return (
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#1a2e1a' }}>📋 编辑 PPT 大纲</span>
          <span style={{ fontSize: 11, color: '#6b7280' }}>可增删改标题和子主题</span>
        </div>

        {/* 大纲列表 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
          {sections.map((sec, si) => (
            <div key={sec.id} style={{
              border: '1px solid #e2e8f0', borderRadius: 8, padding: 8,
              background: '#fafcfa',
            }}>
              {/* 章节头部 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                <span style={{ fontSize: 11, color: '#9ca3af', minWidth: 18 }}>{si + 1}.</span>
                <input
                  value={sec.title}
                  onChange={e => updateSectionTitle(sec.id, e.target.value)}
                  placeholder="章节标题"
                  style={{
                    flex: 1, border: '1px solid #e2e8f0', borderRadius: 4,
                    padding: '3px 6px', fontSize: 12, outline: 'none',
                  }}
                />
                <span onClick={() => removeSection(sec.id)}
                  style={{ cursor: 'pointer', color: '#ef4444', fontSize: 14, padding: '0 4px' }}>×</span>
              </div>
              {/* 子主题列表 */}
              <div style={{ paddingLeft: 22, display: 'flex', flexDirection: 'column', gap: 3 }}>
                {sec.subtopics.map((st, sti) => (
                  <div key={sti} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <span style={{ fontSize: 10, color: '#9ca3af' }}>▸</span>
                    <input
                      value={st}
                      onChange={e => updateSubtopic(sec.id, sti, e.target.value)}
                      placeholder={`子主题 ${sti + 1}`}
                      style={{
                        flex: 1, border: 'none', borderBottom: '1px dashed #e2e8f0',
                        padding: '2px 4px', fontSize: 11, outline: 'none', background: 'transparent',
                      }}
                    />
                    <span onClick={() => removeSubtopic(sec.id, sti)}
                      style={{ cursor: 'pointer', color: '#ef4444', fontSize: 12, lineHeight: 1 }}>×</span>
                  </div>
                ))}
                <span onClick={() => addSubtopic(sec.id)}
                  style={{ cursor: 'pointer', color: '#2d7d46', fontSize: 11, padding: '2px 0' }}>
                  + 添加子主题
                </span>
              </div>
            </div>
          ))}
          <span onClick={addSection}
            style={{ cursor: 'pointer', color: '#2d7d46', fontSize: 12, fontWeight: 500 }}>
            + 添加章节
          </span>
        </div>

        {/* 主题选择 */}
        <div style={{ marginBottom: 12 }}>
          <label style={{ ...labelStyle, marginBottom: 6 }}>选择主题配色</label>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {THEMES.map(theme => (
              <div
                key={theme.name}
                onClick={() => setSelectedTheme(theme.name)}
                style={{
                  flex: 1, minWidth: 70, padding: '6px 4px', borderRadius: 8,
                  border: selectedTheme === theme.name ? `2px solid ${theme.color}` : '2px solid #e2e8f0',
                  background: selectedTheme === theme.name ? `${theme.color}10` : '#fff',
                  cursor: 'pointer', textAlign: 'center' as const,
                  transition: 'all 150ms',
                }}
              >
                <div style={{
                  width: 24, height: 24, borderRadius: '50%',
                  background: theme.color, margin: '0 auto 3px',
                  border: selectedTheme === theme.name ? '2px solid #fff' : 'none',
                  boxShadow: selectedTheme === theme.name ? `0 0 0 2px ${theme.color}` : 'none',
                }} />
                <div style={{ fontSize: 10, fontWeight: 500, color: '#374151' }}>{theme.label}</div>
                <div style={{ fontSize: 9, color: '#9ca3af' }}>{theme.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 视觉风格选择 */}
        <div style={{ marginBottom: 12 }}>
          <label style={{ ...labelStyle, marginBottom: 6 }}>选择视觉布局</label>
          <StyleSelector
            value={selectedVisualStyle}
            onChange={setSelectedVisualStyle}
            columns={3}
            description=""
          />
        </div>

        {error && <div style={{ fontSize: 12, color: '#dc2626', marginBottom: 8 }}>{error}</div>}

        <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
          <button onClick={backToForm} style={btnSecondary}>上一步</button>
          <button onClick={handleGeneratePpt} disabled={loading}
            style={{
              ...btnPrimary,
              background: loading ? '#d4edda' : '#2d7d46',
              color: loading ? '#88c8a0' : '#fff',
              cursor: loading ? 'default' : 'pointer',
            }}>
            {loading ? '正在生成...' : '开始制作'}
          </button>
        </div>
      </div>
    );
  }

  // ========== Step 3: 生成中（进度展示） ==========
  return (
    <div style={{ marginLeft: 0, marginBottom: 8 }}>
      <GenerationProgress
        status={genStatus}
        skillName={activeSkillName || 'PPT设计'}
        skillTypeLabel="PPT"
        successUrl={genStatus === 'success' ? undefined : undefined}
        successLabel="点击查看PPT"
        streamText={genStreamText}
      />
      {error && <div style={{ fontSize: 12, color: '#dc2626', marginTop: 4 }}>{error}</div>}
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
