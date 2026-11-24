// 试卷列表页 — 展示所有草稿和已发布试卷，支持筛选、查看、删除，以及答题卡和模板管理
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { paperStateLabels } from '../../shared/exams/PaperGradingStatus';
import { teacherApi, ExamListItem, AnswerSheetTemplateItem, ChoiceQuestionItem, ClassData } from '../../api/teacher';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary, chipStyle, inputStyle, labelStyle,
  IconPlus, IconTrash, IconCheck, IconEdit,
} from '../../design-system';

const DIFFICULTY_MAP: Record<number, string> = { 1: '简单', 2: '中等', 3: '困难' };
const STATUS_NAMES: Record<string, string> = { draft: '草稿', published: '已发布' };
const STATUS_TABS = [
  { value: undefined as string | undefined, label: '全部' },
  { value: 'draft', label: '草稿' },
  { value: 'published', label: '已发布' },
];

const OPTION_LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
type QuestionType = 'single_choice' | 'multi_choice';

const makeOptions = (count: number): string[] => Array.from({ length: count }, (_, i) => OPTION_LETTERS[i]);

const makeDefaultQuestions = (n: number, score: number, opts: number, qtype: QuestionType): ChoiceQuestionItem[] =>
  Array.from({ length: n }, (_, i) => ({
    question_number: i + 1, score, type: qtype, option_count: opts,
    options: makeOptions(opts),
  }));

const segCtrl: React.CSSProperties = { display: 'inline-flex', borderRadius: 50, overflow: 'hidden', border: '1px solid #e5e5e5', height: 32 };
const segBtn = (active: boolean): React.CSSProperties => ({
  padding: '4px 12px', fontSize: 12, fontWeight: active ? 600 : 400,
  color: active ? '#fff' : '#6b7280', background: active ? green.primary : '#fff',
  border: 'none', cursor: 'pointer', height: '100%', display: 'inline-flex', alignItems: 'center',
});
const miniInp: React.CSSProperties = { ...inputStyle, width: 56, padding: '5px 6px', fontSize: 12, textAlign: 'center' };
const optBubble: React.CSSProperties = {
  width: 30, height: 30, borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  fontSize: 12, fontWeight: 500,
  border: '1.5px solid #e5e5e5', background: '#fff', color: '#6b7280',
};

const TAB_KEYS = ['answer-sheet', 'templates'] as const;
type TabKey = (typeof TAB_KEYS)[number];

export default function ExamList() {
  const navigate = useNavigate();

  // ── 试卷列表状态 ──
  const [exams, setExams] = useState<ExamListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string | undefined>(undefined);

  // ── 弹窗状态 ──
  const [showDialog, setShowDialog] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>('answer-sheet');

  // ── 发布班级选择 ──
  const [classes, setClasses] = useState<ClassData[]>([]);
  const [publishClassId, setPublishClassId] = useState('');
  const [showPublishPicker, setShowPublishPicker] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishTargetId, setPublishTargetId] = useState<number | null>(null);

  // ── 批卷二级菜单 ──
  const [showGradeDialog, setShowGradeDialog] = useState(false);
  const [gradeExamId, setGradeExamId] = useState<number | null>(null);
  const [gradeExamTitle, setGradeExamTitle] = useState('');
  const [selectedGradeClassId, setSelectedGradeClassId] = useState('');

  // ── 模板状态 ──
  const [templates, setTemplates] = useState<AnswerSheetTemplateItem[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [templateName, setTemplateName] = useState('');
  const [templateGrade, setTemplateGrade] = useState('');
  const [templateDesc, setTemplateDesc] = useState('');
  const [templateIsDefault, setTemplateIsDefault] = useState(false);

  // ── 选择题配置状态 ──
  const [qCount, setQCount] = useState(10);
  const [defScore, setDefScore] = useState(5);
  const [defOptCnt, setDefOptCnt] = useState(4);
  const [defType, setDefType] = useState<QuestionType>('single_choice');
  const [questions, setQuestions] = useState<ChoiceQuestionItem[]>(
    () => makeDefaultQuestions(10, 5, 4, 'single_choice'),
  );
  const [templateError, setTemplateError] = useState('');

  // 重置创建表单
  const resetCreateForm = useCallback(() => {
    setTemplateName(''); setTemplateGrade(''); setTemplateDesc(''); setTemplateIsDefault(false);
    setQCount(10); setDefScore(5); setDefOptCnt(4); setDefType('single_choice');
    setQuestions(makeDefaultQuestions(10, 5, 4, 'single_choice'));
    setTemplateError('');
  }, []);

  // 同步题量
  const syncQCount = (n: number) => {
    const cnt = Math.max(1, Math.min(100, n));
    setQCount(cnt);
    setQuestions(prev => {
      if (cnt === prev.length) return prev;
      if (cnt > prev.length) {
        const add = Array.from({ length: cnt - prev.length }, (_, i) => ({
          question_number: prev.length + i + 1, score: defScore, type: defType,
          option_count: defOptCnt, options: makeOptions(defOptCnt),
        } as ChoiceQuestionItem));
        return [...prev, ...add];
      }
      return prev.slice(0, cnt).map((q, i) => ({ ...q, question_number: i + 1 }));
    });
  };

  // 同步默认分值
  const syncDefScore = (s: number) => { setDefScore(s); setQuestions(prev => prev.map(q => ({ ...q, score: s }))); };

  // 同步默认选项数量
  const syncDefOptCnt = (n: number) => {
    const c = Math.max(2, Math.min(8, n));
    setDefOptCnt(c);
    setQuestions(prev => prev.map(q => ({ ...q, option_count: c, options: makeOptions(c) })));
  };

  // 同步默认题型
  const syncDefType = (t: QuestionType) => { setDefType(t); setQuestions(prev => prev.map(q => ({ ...q, type: t }))); };

  // 更新单个题目
  const updQ = (idx: number, patch: Partial<ChoiceQuestionItem>) =>
    setQuestions(prev => prev.map((q, i) => (i === idx ? { ...q, ...patch } : q)));

  const setQType = (idx: number, t: QuestionType) => updQ(idx, { type: t });
  const setQOptCnt = (idx: number, n: number) => {
    const c = Math.max(2, Math.min(8, n));
    updQ(idx, { option_count: c, options: makeOptions(c) });
  };

  // ── 加载试卷列表 ──
  const loadExams = async () => {
    setLoading(true);
    try {
      const res = await teacherApi.listExams({ status: filter, page_size: 50 });
      setExams(res.items);
    } catch (e: any) {
      alert('加载失败: ' + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadExams(); }, [filter]);
  useEffect(() => { teacherApi.listClasses().then(setClasses).catch(() => {}); }, []);

  // ── 试卷操作 ──
  const handleDelete = async (id: number, title: string) => {
    if (!window.confirm('确定删除试卷「' + title + '」？')) return;
    try {
      await teacherApi.deleteExam(id);
    } catch (e: any) {
      alert('删除失败: ' + (e?.response?.data?.detail || e.message));
    }
    loadExams();
  };

  // 发布：打开班级选择弹窗
  const handlePublishClick = (id: number) => {
    setPublishTargetId(id);
    setPublishClassId('');
    setShowPublishPicker(true);
  };

  const handlePublishConfirm = async () => {
    if (!publishTargetId) return;
    if (!publishClassId) { alert('请选择目标班级'); return; }
    setPublishing(true);
    try {
      await teacherApi.publishExam(publishTargetId, { class_id: publishClassId });
      setShowPublishPicker(false);
      loadExams();
    } catch (e: any) {
      alert('发布失败: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setPublishing(false);
    }
  };

  // ── 批卷：打开二级菜单 ──
  const handleGradeClick = (id: number, title: string) => {
    setGradeExamId(id);
    setGradeExamTitle(title);
    setSelectedGradeClassId('');
    setShowGradeDialog(true);
  };

  // 进入批卷页
  const handleEnterGrade = () => {
    if (!gradeExamId || !selectedGradeClassId) {
      alert('请先选择班级');
      return;
    }
    setShowGradeDialog(false);
    navigate('/exams/grade?examId=' + gradeExamId + '&classId=' + selectedGradeClassId);
  };

  // ── 加载模板列表 ──
  const loadTemplates = async () => {
    setTemplatesLoading(true);
    try {
      const items = await teacherApi.listAnswerSheetTemplates();
      setTemplates(items);
    } catch (e: any) {
      alert('加载模板失败: ' + e.message);
    } finally {
      setTemplatesLoading(false);
    }
  };

  // 打开弹窗时，如果切到模板 tab 则加载模板
  const openDialog = (tab: TabKey) => {
    setShowDialog(true);
    setActiveTab(tab);
    setShowCreateForm(false);
    resetCreateForm();
    if (tab === 'templates') { loadTemplates(); }
  };

  // ── 停用模板 ──
  const handleArchiveTemplate = async (id: string, name: string) => {
    if (!window.confirm('停用模板「' + name + '」？已有试卷继续使用原版本。')) return;
    try {
      await teacherApi.archiveAnswerSheetTemplate(id);
      loadTemplates();
    } catch (e: any) {
      alert('停用失败: ' + e.message);
    }
  };

  // ── 创建模板 ──
  const handleCreateTemplate = async () => {
    setTemplateError('');
    if (!templateName.trim()) { setTemplateError('请输入模板名称'); return; }
    if (questions.length === 0) { setTemplateError('题目配置不能为空'); return; }
    try {
      await teacherApi.createAnswerSheetTemplate({
        name: templateName.trim(),
        create_only: true,
        choice_questions: questions,
        grade: templateGrade.trim() || undefined,
        description: templateDesc.trim() || undefined,
        is_default: templateIsDefault ? 1 : 0,
      });
      setShowCreateForm(false);
      resetCreateForm();
      loadTemplates();
    } catch (e: any) {
      alert('创建失败: ' + (e?.response?.data?.detail || e.message));
    }
  };

  // ── 预览答题卡 ──
  const handlePreviewTemplate = async (t: AnswerSheetTemplateItem) => {
    try {
      const res = await teacherApi.answerSheetFromJson({
        title: t.name,
        choice_questions: t.choice_questions,
        page_size: 'A4',
      });
      const win = window.open('', '_blank');
      if (win) {
        win.document.write(res.html);
        win.document.close();
      } else {
        alert('浏览器阻止了新窗口，请允许弹窗后重试');
      }
    } catch (e: any) {
      alert('预览失败: ' + (e?.response?.data?.detail || e.message));
    }
  };

  // ── 下载答题卡PDF（模板页，通过新接口直接生成PDF） ──
  const handleDownloadTemplate = async (t: AnswerSheetTemplateItem) => {
    try {
      const blob = await teacherApi.downloadAnswerSheetFromJsonPdf({
        title: t.name,
        choice_questions: t.choice_questions,
        page_size: 'A4',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `答题卡_${t.name}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert('下载失败: ' + (e?.response?.data?.detail || e.message));
    }
  };

  // ── 下载答题卡PDF（带认证，通过 Axios 发送 Bearer Token） ──
  const handleDownloadPdf = async (examId: number) => {
    try {
      const blob = await teacherApi.downloadAnswerSheetPdf(examId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `答题卡_${examId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert('下载PDF失败: ' + (e?.response?.data?.detail || e.message));
    }
  };

  // ── 将试卷答题卡添加为我的模板 ──
  const handleAddAsTemplate = async (exam: ExamListItem) => {
    try {
      const config = await teacherApi.getAnswerSheetConfig(exam.id);
      if (!config.regions || config.regions.length === 0) {
        alert('该试卷无答题卡选择题配置，无法添加为模板');
        return;
      }
      const choiceQuestions: ChoiceQuestionItem[] = config.regions.map(r => ({
        question_number: r.question_number,
        score: r.score,
        type: (r.type === 'multi' || r.type === 'multiple_choice') ? 'multi_choice' : 'single_choice',
        option_count: r.option_count,
        options: r.options,
        correct_answer: r.correct_answer || undefined,
      }));
      await teacherApi.createAnswerSheetTemplate({
        name: `${exam.title}答题卡模板`,
        choice_questions: choiceQuestions,
        grade: exam.grade,
        description: `从试卷「${exam.title}」自动生成`,
        is_default: 0,
      });
      alert('已成功添加为答题卡模板');
      // 切到我的模板 Tab 并刷新列表
      setActiveTab('templates');
      loadTemplates();
    } catch (e: any) {
      alert('添加模板失败: ' + (e?.response?.data?.detail || e.message));
    }
  };

  // ── 公共弹窗样式 ──
  const overlayStyle: React.CSSProperties = {
    position: 'fixed', inset: 0, zIndex: 1000,
    background: 'rgba(0,0,0,0.4)', display: 'flex',
    alignItems: 'center', justifyContent: 'center',
  };
  const dialogStyle: React.CSSProperties = {
    ...cardStyle, width: 720, maxHeight: '85vh',
    display: 'flex', flexDirection: 'column',
  };
  const tabBarStyle: React.CSSProperties = {
    display: 'flex', gap: 0, borderBottom: `2px solid ${colors['hairline-soft']}`,
    marginBottom: space.sm, flexShrink: 0,
  };
  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: '10px 20px', fontSize: 14, fontWeight: active ? 600 : 400,
    color: active ? colors['text-primary'] : colors['text-tertiary'],
    borderBottom: active ? `2px solid ${green.primary}` : '2px solid transparent',
    background: 'none', borderTop: 'none', borderLeft: 'none', borderRight: 'none',
    cursor: 'pointer', transition: 'color 0.15s, border-color 0.15s',
    marginBottom: -2,
  });

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      {/* ─── 顶栏 ─── */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: space.xl,
      }}>
        <div>
          <h1 style={{
            margin: 0, fontSize: typography['display-lg'].fontSize,
            fontWeight: typography['display-lg'].fontWeight,
            letterSpacing: typography['display-lg'].letterSpacing,
            color: colors['text-primary'],
          }}>试卷管理</h1>
          <p style={{ margin: '4px 0 0', color: colors['text-secondary'], fontSize: typography['body-sm'].fontSize }}>
            AI 出卷、查看、编辑、发布
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={() => navigate('/exams/paper-drafts/new')} style={btnSmallSecondary}>纸质批改草稿</button>
          <button onClick={() => navigate('/exams/create')} style={btnPrimary}>
            <IconPlus size={14} color="#fff" /> 创建新试卷
          </button>
          <button onClick={() => openDialog('answer-sheet')} style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            padding: '10px 24px', background: colors['block-cream'], color: green.strong,
            border: `1.5px solid ${green.soft}`, borderRadius: 50, fontSize: 15,
            fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap',
            transition: 'background 0.15s, box-shadow 0.15s',
          }}
            onMouseEnter={(e) => { e.currentTarget.style.background = green.bg; e.currentTarget.style.boxShadow = '0 2px 8px rgba(91,158,111,0.2)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = colors['block-cream']; e.currentTarget.style.boxShadow = 'none'; }}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke={green.strong} strokeWidth="2" strokeLinecap="round">
              <rect x="2" y="3" width="12" height="10" rx="1" />
              <line x1="5" y1="7" x2="11" y2="7" />
              <line x1="5" y1="10" x2="9" y2="10" />
            </svg>
            答题卡
          </button>
        </div>
      </div>

      {/* ─── 状态筛选 ─── */}
      <div style={{ marginBottom: space.lg, display: 'flex', gap: 8 }}>
        {STATUS_TABS.map((tab) => {
          const key = tab.value ?? 'all';
          const active = filter === tab.value;
          return (
            <button key={key} onClick={() => setFilter(tab.value)} style={chipStyle(active)}>
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ─── 试卷列表 ─── */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: colors['text-tertiary'] }}>加载中...</div>
      ) : exams.length === 0 ? (
        <div style={{
          ...cardStyle, textAlign: 'center', padding: 60,
          border: `2px dashed ${colors.hairline}`,
        }}>
          <p style={{ color: colors['text-tertiary'], margin: 0, fontSize: 15 }}>
            暂无试卷，点击右上角创建第一份
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: space.sm, gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
          {exams.map((exam) => (
            <div key={exam.id} style={{
              ...cardStyle,
              display: 'flex', flexDirection: 'column',
              cursor: 'pointer',
              transition: 'box-shadow 0.2s, transform 0.2s',
            }}
              onClick={() => navigate(exam.paper_draft ? '/exams/paper-drafts/' + exam.id : '/exams/create?id=' + exam.id)}
              onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.1)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'none'; }}
            >
              <div style={{ display: 'flex', gap: 8, marginBottom: space.sm, flexWrap: 'wrap' }}>
                <span style={{
                  background: exam.status === 'published' ? colors['block-lime'] : colors['surface-soft'],
                  color: exam.status === 'published' ? colors.success : colors['text-secondary'],
                  padding: '2px 12px', borderRadius: radius.pill, fontSize: 12, fontWeight: 500,
                }}>{exam.paper_state ? paperStateLabels[exam.paper_state] : exam.paper_draft ? '纸质批改草稿' : STATUS_NAMES[exam.status] || exam.status}</span>
                <span style={{
                  background: colors['block-lilac'], color: green.strong,
                  padding: '2px 12px', borderRadius: radius.pill, fontSize: 12,
                }}>{DIFFICULTY_MAP[exam.difficulty] || '中等'}</span>
                {exam.grade && (
                  <span style={{
                    background: colors['block-cream'], color: green.primary,
                    padding: '2px 12px', borderRadius: radius.pill, fontSize: 12,
                  }}>{exam.grade}</span>
                )}
              </div>
              <h3 style={{
                margin: '0 0 xs', fontSize: typography['card-title'].fontSize,
                fontWeight: 600, color: colors['text-primary'], lineHeight: 1.3,
              }}>{exam.title}</h3>
              <p style={{ margin: 0, color: colors['text-secondary'], fontSize: typography['body-sm'].fontSize }}>
                {exam.question_count} 题 · {exam.total_score} 分 · {exam.duration_minutes} 分钟
              </p>
              <div style={{
                marginTop: 'auto', paddingTop: space.sm,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                borderTop: `1px solid ${colors['hairline-soft']}`,
                fontSize: typography['body-sm'].fontSize,
                color: colors['text-tertiary'],
              }}>
                <span>
                  {exam.submission_count > 0 ? exam.submission_count + ' 人提交' : '暂无提交'}
                </span>
                <span>{new Date(exam.created_at).toLocaleDateString()}</span>
              </div>
              <div style={{ marginTop: space.sm, display: 'flex', gap: 8 }} onClick={(e) => e.stopPropagation()}>
                {/* 所有试卷都有批卷按钮 */}
                <button onClick={() => exam.paper_draft ? navigate('/exams/paper-drafts/' + exam.id) : handleGradeClick(exam.id, exam.title)} style={{
                  ...btnSmall, flex: 1,
                  background: colors['block-lilac'], color: green.strong, border: 'none',
                }}>
                  <IconEdit size={12} color={green.strong} /> {exam.paper_draft ? '继续编辑' : '批卷'}
                </button>
                {exam.paper_draft && (
                  <button type="button" onClick={() => navigate(`/exams/${exam.id}/records`)} style={btnSmallSecondary}>批改记录</button>
                )}
                {/* 草稿试卷额外显示发布按钮 */}
                {exam.status === 'draft' && !exam.paper_draft && (
                  <button onClick={() => handlePublishClick(exam.id)} style={{
                    ...btnSmall,
                    background: colors['block-lime'], color: colors.success, border: 'none',
                  }}>
                    <IconCheck size={12} color={colors.success} /> 发布
                  </button>
                )}
                <button onClick={() => handleDelete(exam.id, exam.title)} style={btnSmallSecondary}>
                  <IconTrash size={12} color={colors.danger} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ══════════════════════════════════════════════════
          Tab 弹窗：答题卡管理
          ══════════════════════════════════════════════════ */}
      {showDialog && (
        <div onClick={() => setShowDialog(false)} style={overlayStyle}>
          <div onClick={(e) => e.stopPropagation()} style={dialogStyle}>
            {/* 弹窗头部 */}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              paddingBottom: space.sm, flexShrink: 0,
            }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>答题卡管理</h2>
              <button
                onClick={() => setShowDialog(false)}
                style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: colors['text-tertiary'], padding: '0 4px' }}
              >✕</button>
            </div>

            {/* Tab 切换栏 */}
            <div style={tabBarStyle}>
              <button onClick={() => { setActiveTab('answer-sheet'); setShowCreateForm(false); }} style={tabStyle(activeTab === 'answer-sheet')}>
                试卷答题卡
              </button>
              <button onClick={() => { setActiveTab('templates'); loadTemplates(); setShowCreateForm(false); resetCreateForm(); }} style={tabStyle(activeTab === 'templates')}>
                我的模板
              </button>
            </div>

            {/* ── Tab 1：试卷答题卡下载 ── */}
            {activeTab === 'answer-sheet' && (
              <div style={{ overflowY: 'auto', flex: 1 }}>
                {exams.filter(e => e.has_answer_sheet && e.answer_sheet_summary).length === 0 ? (
                  <p style={{ textAlign: 'center', color: colors['text-tertiary'], padding: '40px 0', margin: 0 }}>
                    暂无可下载答题卡的试卷
                  </p>
                ) : (
                  exams.filter(e => e.has_answer_sheet && e.answer_sheet_summary).map(exam => {
                    const summary = exam.answer_sheet_summary!;
                    return (
                      <div key={exam.id} style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '12px 0', borderBottom: `1px solid ${colors['hairline-soft']}`,
                      }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 600, fontSize: 14, color: colors['text-primary'], marginBottom: 2 }}>{exam.title}</div>
                          <div style={{ fontSize: 12, color: colors['text-tertiary'] }}>
                            {summary.total_questions} 题 · 每项 {summary.option_count} 选项 · {exam.question_count} 道大题
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: 8, flexShrink: 0, marginLeft: 12 }}>
                          <span onClick={() => handleDownloadPdf(exam.id)} style={{ ...btnSmall, cursor: 'pointer', display: 'inline-flex', textDecoration: 'none', background: colors['block-lime'], color: colors.success, border: 'none' }}>
                            下载 PDF
                          </span>
                          <a href={summary.html_url} target="_blank" rel="noopener noreferrer" style={{ ...btnSmallSecondary, textDecoration: 'none' }}>
                            预览
                          </a>
                          <span onClick={() => handleAddAsTemplate(exam)} style={{ ...btnSmall, cursor: 'pointer', display: 'inline-flex', textDecoration: 'none', background: colors['block-lilac'], color: green.strong, border: 'none' }}>
                            添加为模板
                          </span>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}

            {/* ── Tab 2：我的模板 ── */}
            {activeTab === 'templates' && (
              <div style={{ overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column' }}>
                {showCreateForm ? (
                  /* ═══════ 创建模板表单 ═══════ */
                  <div>
                    {/* 标题栏 */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.sm }}>
                      <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>新建答题卡模板</h3>
                      <button onClick={() => { setShowCreateForm(false); resetCreateForm(); }} style={btnSmallSecondary}>返回列表</button>
                    </div>

                    {/* 基本信息 */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: space.sm, marginBottom: 6 }}>
                      <div>
                        <label style={labelStyle}>模板名称 *</label>
                        <input style={inputStyle} value={templateName} onChange={e => setTemplateName(e.target.value)} placeholder="例如：数学中考标准答题卡" />
                      </div>
                      <div>
                        <label style={labelStyle}>年级</label>
                        <input style={inputStyle} value={templateGrade} onChange={e => setTemplateGrade(e.target.value)} placeholder="例如：九年级" />
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: space.sm }}>
                      <div style={{ flex: 1 }}>
                        <input style={inputStyle} value={templateDesc} onChange={e => setTemplateDesc(e.target.value)} placeholder="可选，模板用途说明" />
                      </div>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13, color: colors['text-secondary'], whiteSpace: 'nowrap' }}>
                        <input type="checkbox" checked={templateIsDefault} onChange={e => setTemplateIsDefault(e.target.checked)} />
                        设为默认
                      </label>
                    </div>

                    {/* ── 全局默认设置工具栏 ── */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '8px 12px', background: colors['surface-soft'], borderRadius: radius.md, marginBottom: space.sm }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: colors['text-secondary'] }}>默认设置：</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ fontSize: 11, color: colors['text-tertiary'] }}>题量</span>
                        <input type="number" style={miniInp} value={qCount} min={1} max={100}
                          onChange={e => syncQCount(parseInt(e.target.value) || 1)} />
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ fontSize: 11, color: colors['text-tertiary'] }}>分值</span>
                        <input type="number" style={miniInp} value={defScore} min={1} max={100}
                          onChange={e => syncDefScore(parseInt(e.target.value) || 1)} />
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ fontSize: 11, color: colors['text-tertiary'] }}>选项数</span>
                        <input type="number" style={miniInp} value={defOptCnt} min={2} max={8}
                          onChange={e => syncDefOptCnt(parseInt(e.target.value) || 2)} />
                      </div>
                      <div style={segCtrl}>
                        <button onClick={() => syncDefType('single_choice')} style={segBtn(defType === 'single_choice')}>单选</button>
                        <button onClick={() => syncDefType('multi_choice')} style={segBtn(defType === 'multi_choice')}>多选</button>
                      </div>
                    </div>

                    {/* ── 题目列表 ── */}
                    <div style={{ maxHeight: 360, overflowY: 'auto', paddingRight: 4 }}>
                      {questions.map((q, idx) => (
                        <div key={idx} style={{
                          display: 'flex', gap: 10, alignItems: 'flex-start',
                          padding: '10px 0', borderBottom: `1px solid ${colors['hairline-soft']}`,
                        }}>
                          {/* 左：题号 */}
                          <div style={{
                            width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                            background: colors['block-lime'], color: green.strong,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 13, fontWeight: 600, marginTop: 2,
                          }}>{q.question_number}</div>

                          {/* 右：选项 + 设置 */}
                          <div style={{ flex: 1, minWidth: 0 }}>
                            {/* 右上角设置栏 */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                              <div style={segCtrl}>
                                <button onClick={() => setQType(idx, 'single_choice')} style={segBtn(q.type === 'single_choice')}>单选</button>
                                <button onClick={() => setQType(idx, 'multi_choice')} style={segBtn(q.type === 'multi_choice')}>多选</button>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                                <span style={{ fontSize: 10, color: colors['text-tertiary'] }}>分值</span>
                                <input type="number" style={{ ...miniInp, width: 44 }} value={q.score} min={1} max={100}
                                  onChange={e => updQ(idx, { score: parseInt(e.target.value) || 1 })} />
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                                <span style={{ fontSize: 10, color: colors['text-tertiary'] }}>选项</span>
                                <input type="number" style={{ ...miniInp, width: 40 }} value={q.option_count} min={2} max={8}
                                  onChange={e => setQOptCnt(idx, parseInt(e.target.value) || 2)} />
                              </div>
                            </div>

                            {/* 选项预览 */}
                            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                              {q.options.map((letter) => (
                                <span key={letter} style={optBubble}>{letter}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>

                    {templateError && (
                      <p style={{ margin: space.sm + 'px 0 0', color: colors.danger, fontSize: 13 }}>{templateError}</p>
                    )}

                    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: space.sm }}>
                      <button onClick={() => { setShowCreateForm(false); resetCreateForm(); }} style={btnSmallSecondary}>取消</button>
                      <button onClick={handleCreateTemplate} style={{ ...btnSmall, background: green.primary, color: '#fff', border: 'none' }}>保存模板</button>
                    </div>
                  </div>
                ) : (
                  /* 模板列表 */
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.sm }}>
                      <span style={{ fontSize: 13, color: colors['text-tertiary'] }}>
                        {templatesLoading ? '加载中...' : templates.length + ' 个模板'}
                      </span>
                      <button onClick={() => { setShowCreateForm(true); resetCreateForm(); }} style={{
                        ...btnSmall, background: green.bg, color: green.strong, border: `1px solid ${green.soft}`,
                      }}>
                        <IconPlus size={12} color={green.strong} /> 新建模板
                      </button>
                    </div>

                    {templatesLoading ? (
                      <p style={{ textAlign: 'center', color: colors['text-tertiary'], padding: 30 }}>加载中...</p>
                    ) : templates.length === 0 ? (
                      <p style={{ textAlign: 'center', color: colors['text-tertiary'], padding: 40, margin: 0 }}>
                        暂无模板，点击上方新建
                      </p>
                    ) : (
                      templates.map(t => (
                        <div key={t.id} style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                          padding: '12px 0', borderBottom: `1px solid ${colors['hairline-soft']}`,
                        }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                              <span style={{ fontWeight: 600, fontSize: 14, color: colors['text-primary'] }}>{t.name}</span>
                              {t.is_default === 1 && (
                                <span style={{ background: colors['block-lime'], color: colors.success, padding: '1px 8px', borderRadius: radius.pill, fontSize: 11 }}>
                                  默认
                                </span>
                              )}
                            </div>
                            <div style={{ fontSize: 12, color: colors['text-tertiary'] }}>
                              {t.grade && <span>{t.grade} · </span>}
                              {t.question_count} 题 · {t.total_score} 分
                              {t.description && <span> · {t.description}</span>}
                            </div>
                          </div>
                          <div style={{ display: 'flex', gap: 8, flexShrink: 0, marginLeft: 12 }}>
                            <button onClick={() => handlePreviewTemplate(t)} style={{
                              ...btnSmall, background: colors['block-lime'], color: colors.success, border: 'none',
                            }}>预览答题卡</button>
                            <button onClick={() => handleDownloadTemplate(t)} style={{
                              ...btnSmall, background: 'transparent', color: colors['text-secondary'], border: `1px solid ${colors['hairline-soft']}`,
                            }}>下载</button>
                            <button onClick={() => handleArchiveTemplate(t.id, t.name)} style={btnSmallSecondary}>停用</button>
                          </div>
                        </div>
                      ))
                    )}
                  </>
                )}
              </div>
            )}

            {/* 弹窗底部按钮 */}
            <div style={{ paddingTop: space.sm, textAlign: 'center', borderTop: `1px solid ${colors['hairline-soft']}`, flexShrink: 0 }}>
              <button onClick={() => setShowDialog(false)} style={btnSmallSecondary}>关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════
          批卷二级菜单对话框
          ══════════════════════════════════════════════════ */}
      {showGradeDialog && (
        <div onClick={() => setShowGradeDialog(false)} style={overlayStyle}>
          <div onClick={(e) => e.stopPropagation()} style={{
            ...cardStyle, width: 440, padding: 0, overflow: 'hidden',
          }}>
            {/* 头部：左侧返回按钮 + 标题 */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '16px 20px', borderBottom: `1px solid ${colors['hairline-soft']}`,
            }}>
              <button onClick={() => setShowGradeDialog(false)}
                style={{
                  background: 'none', border: 'none', fontSize: 22, cursor: 'pointer',
                  color: colors['text-secondary'], padding: '0 2px', lineHeight: 1,
                  display: 'flex', alignItems: 'center',
                }}
                title="返回"
              >‹</button>
              <div>
                <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: colors['text-primary'] }}>
                  批卷 - {gradeExamTitle}
                </h3>
                <p style={{ margin: '4px 0 0', fontSize: 12, color: colors['text-tertiary'] }}>
                  选择要批改的班级，进入批卷页面
                </p>
              </div>
            </div>

            {/* 班级选择 */}
            <div style={{ padding: '24px 20px' }}>
              <label style={{ ...labelStyle, marginBottom: 8 }}>选择班级</label>
              <select value={selectedGradeClassId}
                onChange={(e) => setSelectedGradeClassId(e.target.value)}
                style={{ ...inputStyle, width: '100%' }}>
                <option value="">-- 请选择班级 --</option>
                {classes.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}（{c.student_count} 人）</option>
                ))}
              </select>
            </div>

            {/* 底部按钮 */}
            <div style={{
              display: 'flex', gap: 8, justifyContent: 'flex-end',
              padding: '12px 20px', borderTop: `1px solid ${colors['hairline-soft']}`,
              background: colors['surface-soft'],
            }}>
              <button onClick={() => setShowGradeDialog(false)} style={btnSmallSecondary}>取消</button>
              <button onClick={handleEnterGrade} disabled={!selectedGradeClassId} style={{
                ...btnSmall,
                background: selectedGradeClassId ? colors.primary : colors['text-tertiary'],
                color: '#fff', border: 'none', opacity: selectedGradeClassId ? 1 : 0.5,
                cursor: selectedGradeClassId ? 'pointer' : 'default',
              }}>
                <IconEdit size={12} color="#fff" /> 进入批卷
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════
          发布班级选择对话框
          ══════════════════════════════════════════════════ */}
      {showPublishPicker && (
        <div onClick={() => setShowPublishPicker(false)} style={overlayStyle}>
          <div onClick={(e) => e.stopPropagation()} style={{
            ...cardStyle, width: 400, padding: space.lg, textAlign: 'center',
          }}>
            <h3 style={{
              margin: '0 0 4px', fontSize: typography.headline.fontSize,
              fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
            }}>选择目标班级</h3>
            <p style={{ fontSize: 13, color: colors['text-secondary'], marginBottom: space.md }}>
              请选择要将试卷发布到的班级
            </p>
            <select value={publishClassId} onChange={(e) => setPublishClassId(e.target.value)}
              style={{ ...inputStyle, marginBottom: space.md }}>
              <option value="">-- 请选择班级 --</option>
              {classes.map((c) => (
                <option key={c.id} value={c.id}>ID:{c.id} - {c.name}</option>
              ))}
            </select>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => setShowPublishPicker(false)} style={{
                flex: 1, padding: '10px 0', borderRadius: radius.pill,
                border: `1px solid ${colors.hairline}`, background: '#fff',
                color: colors['text-secondary'], fontSize: 13, cursor: 'pointer',
              }}>取消</button>
              <button onClick={handlePublishConfirm} disabled={publishing} style={{
                flex: 2, padding: '10px 0', borderRadius: radius.pill, border: 'none',
                background: publishing ? colors['text-tertiary'] : colors.primary,
                color: '#fff', fontSize: 13, fontWeight: 500, cursor: publishing ? 'default' : 'pointer',
                opacity: publishing ? 0.6 : 1,
              }}>{publishing ? '发布中...' : '确认发布'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
