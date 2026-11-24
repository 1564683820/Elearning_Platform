// 手动批卷页面 — 拍照上传 + 教师对照图片手动标注答案 + 自动批改
// 替代不可靠的 OMR 自动识别方案
import { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { teacherApi, ManualGradeResult } from '../../api/teacher';
import {
  colors, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary,
} from '../../design-system';

const XS = 8;

// 题目信息
interface GradingQuestion {
  question_number: number;
  options: string[];
  option_count: number;
}

// 试卷批卷信息
interface GradingInfo {
  exam_id: number;
  title: string;
  class_id: number;
  total_questions: number;
  total_score: number;
  questions: GradingQuestion[];
}

export default function ManualGrade() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const examId = searchParams.get('examId') || '';
  const classId = searchParams.get('classId') || '';

  // 试卷信息
  const [gradingInfo, setGradingInfo] = useState<GradingInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // 照片
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState('');

  // 考号 / 学生名
  const [examNumber, setExamNumber] = useState('');
  const [studentName, setStudentName] = useState('');

  // 手动标注答案 { question_number: "A" }
  const [answers, setAnswers] = useState<Record<string, string>>({});

  // 提交状态
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // 批改结果
  const [gradeResult, setGradeResult] = useState<ManualGradeResult | null>(null);

  // 选择答案模式: "click" | "keyboard"（键盘模式：显示总览表格，连续按键标注）
  const [mode, setMode] = useState<'click' | 'keyboard'>('click');

  // 键盘模式：当前聚焦题号
  const [focusQnum, setFocusQnum] = useState(0);

  // 加载试卷信息
  useEffect(() => {
    if (!examId) {
      setError('缺少 examId 参数');
      setLoading(false);
      return;
    }
    loadGradingInfo();
  }, [examId]);

  const loadGradingInfo = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await teacherApi.getExamGradingInfo(examId);
      setGradingInfo(res);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || '加载试卷信息失败');
    } finally {
      setLoading(false);
    }
  };

  // 点击选择答案 / 键盘输入
  const selectAnswer = useCallback((qnum: number, option: string) => {
    setAnswers(prev => {
      const key = String(qnum);
      if (prev[key] === option) {
        // 再次点击取消选择
        const next = { ...prev };
        delete next[key];
        return next;
      }
      return { ...prev, [key]: option };
    });
  }, []);

  // 上传照片
  useEffect(() => {
    return () => { if (imagePreview) URL.revokeObjectURL(imagePreview); };
  }, [imagePreview]);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImageFile(file);
      const url = URL.createObjectURL(file);
      setImagePreview(url);
    }
  };

  // 获取已选答案数
  const selectedCount = Object.keys(answers).length;
  const totalQuestions = gradingInfo?.total_questions || 0;
  const isAllAnswered = selectedCount === totalQuestions && totalQuestions > 0;

  // 提交批改
  const handleSubmit = async () => {
    if (!imageFile) {
      setSubmitError('请先上传答题卡照片');
      return;
    }
    if (selectedCount === 0) {
      setSubmitError('请至少标注一题的答案');
      return;
    }

    setSubmitting(true);
    setSubmitError('');

    try {
      const formData = new FormData();
      formData.append('image', imageFile);
      if (examNumber) formData.append('exam_number', examNumber);
      if (studentName) formData.append('student_name', studentName);
      formData.append('manual_answers_json', JSON.stringify(answers));

      const result = await teacherApi.manualGrade(examId, formData);
      setGradeResult(result);
    } catch (err: any) {
      setSubmitError(err?.message || '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  // 键盘事件（键盘模式用）
  useEffect(() => {
    if (mode !== 'keyboard') return;
    const handleKey = (e: KeyboardEvent) => {
      const target = e.target;
      if (target instanceof HTMLElement && (
        target.closest('input, textarea, select, button, [contenteditable]')
      )) return;
      if (e.ctrlKey || e.metaKey || e.altKey || e.isComposing || e.repeat || submitting || gradeResult) return;
      const key = e.key.toUpperCase();
      const focusedQuestion = gradingInfo?.questions.find(q => q.question_number === focusQnum);
      if (focusedQuestion?.options.includes(key)) {
        if (focusQnum > 0) {
          selectAnswer(focusQnum, key);
          // 自动跳到下一题
          const questions = gradingInfo?.questions || [];
          const idx = questions.findIndex(q => q.question_number === focusQnum);
          if (idx >= 0 && idx < questions.length - 1) {
            setFocusQnum(questions[idx + 1].question_number);
          }
        }
        e.preventDefault();
      } else if (key === 'BACKSPACE' || key === 'DELETE') {
        if (focusQnum > 0) {
          setAnswers(prev => {
            const next = { ...prev };
            delete next[String(focusQnum)];
            return next;
          });
        }
        e.preventDefault();
      } else if (key === 'ARROWUP' || key === 'ARROWLEFT') {
        const questions = gradingInfo?.questions || [];
        const idx = questions.findIndex(q => q.question_number === focusQnum);
        if (idx > 0) setFocusQnum(questions[idx - 1].question_number);
        e.preventDefault();
      } else if (key === 'ARROWDOWN' || key === 'ARROWRIGHT') {
        const questions = gradingInfo?.questions || [];
        const idx = questions.findIndex(q => q.question_number === focusQnum);
        if (idx >= 0 && idx < questions.length - 1) setFocusQnum(questions[idx + 1].question_number);
        e.preventDefault();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [mode, focusQnum, selectAnswer, gradingInfo, submitting, gradeResult]);

  // 开始键盘模式时聚焦第一题
  const startKeyboardMode = () => {
    setMode('keyboard');
    const qs = gradingInfo?.questions || [];
    if (qs.length > 0) setFocusQnum(qs[0].question_number);
  };

  // ── 渲染 ──
  if (loading) {
    return (
      <div style={{ padding: space.lg, textAlign: 'center', color: colors['text-secondary'] }}>
        加载试卷信息...
      </div>
    );
  }

  if (error && !gradingInfo) {
    return (
      <div style={{ padding: space.lg }}>
        <div style={{ ...cardStyle, padding: space.lg, textAlign: 'center' }}>
          <p style={{ color: colors.danger, marginBottom: space.md }}>{error}</p>
          <button style={btnPrimary} onClick={() => navigate('/exams/grade')}>返回批卷页</button>
        </div>
      </div>
    );
  }

  // 显示结果
  if (gradeResult) {
    return <GradeResultView
      result={gradeResult}
      questions={gradingInfo?.questions || []}
      onBack={() => {
        setGradeResult(null);
        setImageFile(null);
        setImagePreview('');
        setExamNumber('');
        setStudentName('');
        setAnswers({});
        setSubmitError('');
        setFocusQnum(gradingInfo?.questions[0]?.question_number || 0);
      }}
      onReturn={() => navigate(`/exams/grade?examId=${examId}&classId=${classId || gradingInfo?.class_id || ''}`)}
    />;
  }

  const questions = gradingInfo?.questions || [];

  return (
    <div style={{ padding: space.lg, maxWidth: 900, margin: '0 auto' }}>
      {/* 头部 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: XS * 2, marginBottom: space.lg }}>
        <button style={btnSmallSecondary} onClick={() => navigate(`/exams/grade?examId=${examId}&classId=${classId}`)}>
          ← 返回
        </button>
        <h1 style={{ ...typography.headline, color: colors['text-primary'], flex: 1, margin: 0 }}>
          手动批卷
        </h1>
        <span style={{ ...typography['body-sm'], color: colors['text-secondary'] }}>
          {gradingInfo?.title}
        </span>
      </div>

      <div style={{ display: 'flex', gap: space.lg, flexWrap: 'wrap' }}>
        {/* 左侧：图片上传区 */}
        <div style={{ flex: '1 1 320px', maxWidth: 420 }}>
          <div style={{ ...cardStyle, padding: space.md }}>
            <h3 style={{ ...typography['card-title'], marginBottom: space.sm, color: colors['text-primary'] }}>
              1. 上传答题卡照片
            </h3>
            <div
              style={{
                border: `2px dashed ${colors.hairline}`,
                borderRadius: radius.md,
                padding: imagePreview ? 0 : space.xl,
                textAlign: 'center',
                cursor: 'pointer',
                backgroundColor: colors['surface-soft'],
                minHeight: imagePreview ? 'auto' : 120,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
                marginBottom: space.md,
              }}
              onClick={() => document.getElementById('manual-grade-image-input')?.click()}
            >
              {imagePreview ? (
                <img
                  src={imagePreview}
                  alt="答题卡照片"
                  style={{ maxWidth: '100%', maxHeight: 500, display: 'block' }}
                />
              ) : (
                <span style={{ color: colors['text-secondary'], ...typography['body-sm'] }}>
                  点击或拖拽上传答题卡照片
                </span>
              )}
              <input
                id="manual-grade-image-input"
                type="file"
                accept="image/*"
                capture="environment"
                style={{ display: 'none' }}
                onChange={handleImageChange}
              />
            </div>

            {/* 考号输入 */}
            <div style={{ marginBottom: XS }}>
              <label style={{ ...typography['body-sm'], color: colors['text-secondary'], display: 'block', marginBottom: 4 }}>
                学生考号（可选，用于自动匹配学生）
              </label>
              <input
                type="text"
                value={examNumber}
                onChange={e => setExamNumber(e.target.value)}
                placeholder="如: 20240101"
                style={{
                  width: '100%',
                  padding: '6px 10px',
                  border: `1px solid ${colors.hairline}`,
                  borderRadius: radius.sm,
                  fontSize: 14,
                  boxSizing: 'border-box',
                }}
              />
            </div>
            <div style={{ marginBottom: space.sm }}>
              <label style={{ ...typography['body-sm'], color: colors['text-secondary'], display: 'block', marginBottom: 4 }}>
                学生姓名（若无法通过考号匹配）
              </label>
              <input
                type="text"
                value={studentName}
                onChange={e => setStudentName(e.target.value)}
                placeholder="如: 张三"
                style={{
                  width: '100%',
                  padding: '6px 10px',
                  border: `1px solid ${colors.hairline}`,
                  borderRadius: radius.sm,
                  fontSize: 14,
                  boxSizing: 'border-box',
                }}
              />
            </div>
          </div>

          <div style={{ ...cardStyle, padding: space.md, marginTop: space.md }}>
            <h3 style={{ ...typography['card-title'], marginBottom: space.sm, color: colors['text-primary'] }}>
              2. 标注答案
            </h3>
            <div style={{ display: 'flex', gap: XS, marginBottom: space.sm }}>
              <button
                style={{ ...btnSmall, ...(mode === 'click' ? {} : { ...btnSmallSecondary }) }}
                onClick={() => setMode('click')}
              >
                点击模式
              </button>
              <button
                style={{ ...btnSmall, ...(mode === 'keyboard' ? {} : { ...btnSmallSecondary }) }}
                onClick={startKeyboardMode}
              >
                键盘模式 (A/B/C/D)
              </button>
            </div>

            {/* 统计 */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: XS * 2, marginBottom: space.md,
              padding: `${XS}px ${XS * 2}px`,
              backgroundColor: colors['surface-soft'],
              borderRadius: radius.sm,
            }}>
              <span style={{ ...typography['body-sm'], color: colors['text-secondary'] }}>
                已标注: <strong style={{ color: isAllAnswered ? colors.success : colors.primary }}>
                  {selectedCount}/{totalQuestions}
                </strong> 题
              </span>
            </div>

            {/* 提交按钮 */}
            <button
              style={{
                ...btnPrimary,
                width: '100%',
                opacity: isAllAnswered ? 1 : 0.6,
              }}
              disabled={submitting || selectedCount === 0}
              onClick={handleSubmit}
            >
              {submitting ? '批改中...' : `提交批改 (${selectedCount}/${totalQuestions}题)`}
            </button>
            {submitError && (
              <p style={{ color: colors.danger, fontSize: 13, marginTop: XS }}>{submitError}</p>
            )}
          </div>
        </div>

        {/* 右侧：题目列表 */}
        <div style={{ flex: '2 1 400px' }}>
          {mode === 'click' ? (
            <ClickModeGrid
              questions={questions}
              answers={answers}
              onSelect={selectAnswer}
            />
          ) : (
            <KeyboardModeTable
              questions={questions}
              answers={answers}
              focusQnum={focusQnum}
              onSelect={selectAnswer}
              onFocus={setFocusQnum}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ── 点击模式：网格按钮 ──
function ClickModeGrid({
  questions, answers, onSelect,
}: {
  questions: GradingQuestion[];
  answers: Record<string, string>;
  onSelect: (qnum: number, option: string) => void;
}) {
  return (
    <div style={{ ...cardStyle, padding: space.md }}>
      <h3 style={{ ...typography['card-title'], marginBottom: space.sm, color: colors['text-primary'] }}>
        对照照片点击选项标注
      </h3>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
        gap: XS,
      }}>
        {questions.map(q => {
          const qnum = q.question_number;
          const selected = answers[String(qnum)] || '';
          return (
            <div
              key={qnum}
              style={{
                border: `1px solid ${selected ? colors.primary : colors['hairline-soft']}`,
                borderRadius: radius.sm,
                padding: XS,
                backgroundColor: selected ? green.bg : colors.canvas,
              }}
            >
              <div style={{ ...typography['body-sm'], fontWeight: 600, marginBottom: 4, color: colors['text-primary'] }}>
                第{qnum}题
              </div>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {q.options.map(opt => (
                  <button
                    key={opt}
                    onClick={() => onSelect(qnum, opt)}
                    style={{
                      minWidth: 32,
                      height: 32,
                      border: `1.5px solid ${selected === opt ? colors.primary : colors.hairline}`,
                      borderRadius: radius.sm,
                      backgroundColor: selected === opt ? colors.primary : colors.canvas,
                      color: selected === opt ? colors['on-primary'] : colors['text-primary'],
                      fontSize: 13,
                      fontWeight: selected === opt ? 600 : 400,
                      cursor: 'pointer',
                      transition: 'all 0.15s',
                    }}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── 键盘模式：表格 + 键盘 A/B/C/D 输入 ──
function KeyboardModeTable({
  questions, answers, focusQnum, onSelect, onFocus,
}: {
  questions: GradingQuestion[];
  answers: Record<string, string>;
  focusQnum: number;
  onSelect: (qnum: number, option: string) => void;
  onFocus: (qnum: number) => void;
}) {
  return (
    <div style={{ ...cardStyle, padding: space.md }}>
      <h3 style={{ ...typography['card-title'], marginBottom: space.sm, color: colors['text-primary'] }}>
        键盘标注 (A/B/C/D 键选答案，方向键切换题目)
      </h3>
      <p style={{ ...typography['body-sm'], color: colors['text-secondary'], marginBottom: space.md }}>
        单击题目行聚焦 → 按 A/B/C/D 选择答案 → 自动跳到下一题
      </p>
      <div style={{ maxHeight: '60vh', overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ backgroundColor: colors['surface-soft'] }}>
              <th style={{ padding: '6px 10px', textAlign: 'left', borderBottom: `1px solid ${colors.hairline}`, width: 60 }}>题号</th>
              <th style={{ padding: '6px 10px', textAlign: 'left', borderBottom: `1px solid ${colors.hairline}`, width: 80 }}>答案</th>
              <th style={{ padding: '6px 10px', textAlign: 'left', borderBottom: `1px solid ${colors.hairline}` }}>选项</th>
            </tr>
          </thead>
          <tbody>
            {questions.map(q => {
              const qnum = q.question_number;
              const selected = answers[String(qnum)] || '';
              const isFocus = focusQnum === qnum;
              return (
                <tr
                  key={qnum}
                  onClick={() => onFocus(qnum)}
                  style={{
                    cursor: 'pointer',
                    backgroundColor: isFocus ? green.bg2 : 'transparent',
                    borderBottom: `1px solid ${colors['hairline-soft']}`,
                    transition: 'background-color 0.1s',
                  }}
                >
                  <td style={{ padding: '6px 10px', fontWeight: 600 }}>
                    {qnum}
                  </td>
                  <td style={{ padding: '6px 10px' }}>
                    {selected ? (
                      <span style={{
                        display: 'inline-block',
                        backgroundColor: colors.primary,
                        color: colors['on-primary'],
                        padding: '2px 8px',
                        borderRadius: radius.sm,
                        fontWeight: 600,
                        fontSize: 12,
                      }}>
                        {selected}
                      </span>
                    ) : (
                      <span style={{ color: colors['text-tertiary'] }}>—</span>
                    )}
                  </td>
                  <td style={{ padding: '6px 10px' }}>
                    <div style={{ display: 'flex', gap: 4 }}>
                      {q.options.map(opt => {
                        const isKeymap = isFocus;
                        return (
                          <span
                            key={opt}
                            style={{
                              padding: '2px 6px',
                              borderRadius: radius.sm,
                              fontSize: 12,
                              border: `1px solid ${selected === opt ? colors.primary : colors.hairline}`,
                              backgroundColor: selected === opt ? colors.primary : 'transparent',
                              color: selected === opt ? colors['on-primary'] : colors['text-secondary'],
                              fontWeight: selected === opt ? 600 : 400,
                            }}
                          >
                            {isKeymap ? <u>{opt}</u> : opt}
                          </span>
                        );
                      })}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── 批改结果视图 ──
function GradeResultView({
  result, questions, onBack, onReturn,
}: {
  result: ManualGradeResult;
  questions: GradingQuestion[];
  onBack: () => void;
  onReturn: () => void;
}) {
  const answers = result.answers || [];
  return (
    <div style={{ padding: space.lg, maxWidth: 800, margin: '0 auto' }}>
      <div style={{ ...cardStyle, padding: space.lg }}>
        {/* 总览 */}
        <div style={{
          textAlign: 'center',
          padding: space.lg,
          backgroundColor: green.bg,
          borderRadius: radius.md,
          marginBottom: space.lg,
        }}>
          <div style={{ ...typography['display-lg'], color: colors.primary, fontWeight: 700 }}>
            {result.total_score}/{result.max_score}
          </div>
          <div style={{ ...typography['body-sm'], color: colors['text-secondary'], marginTop: XS }}>
            {result.student_name || '未知学生'}
            {result.exam_number ? ` (考号: ${result.exam_number})` : ''}
          </div>
          <div style={{ ...typography['body-sm'], color: colors.danger, marginTop: XS }}>
            错题: {result.wrong_count} 道
          </div>
          <div style={{ marginTop: space.md, display: 'flex', gap: XS, justifyContent: 'center' }}>
            <button style={btnPrimary} onClick={onBack}>继续批改下一份</button>
            <button style={btnSmallSecondary} onClick={onReturn}>返回成绩列表</button>
          </div>
        </div>

        {/* 逐题详情 */}
        <h3 style={{ ...typography['card-title'], color: colors['text-primary'], marginBottom: space.sm }}>
          答题详情
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: XS }}>
          {answers.map((a) => {
            const isCorrect = a.is_correct;
            return (
              <div
                key={a.question_number}
                style={{
                  padding: `${XS}px ${XS * 2}px`,
                  borderLeft: `3px solid ${isCorrect ? colors.success : colors.danger}`,
                  backgroundColor: isCorrect ? green.bg : '#fef2f2',
                  borderRadius: radius.sm,
                  fontSize: 13,
                }}
              >
                <div style={{ fontWeight: 600 }}>
                  第{a.question_number}题
                  <span style={{ marginLeft: XS, color: isCorrect ? colors.success : colors.danger }}>
                    {isCorrect ? '✓' : '✗'}
                  </span>
                </div>
                <div style={{ color: colors['text-secondary'], fontSize: 12 }}>
                  作答: <strong>{a.student_answer || '未答'}</strong>
                  {' '}|{' '}
                  正确: <strong style={{ color: colors.primary }}>{a.correct_answer || '-'}</strong>
                </div>
                <div style={{ color: colors['text-tertiary'], fontSize: 11 }}>
                  得分: {a.score}/{a.max_score}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// 绿色主题色引用
const green = {
  primary: '#5B9E6F',
  bg: '#e6f7e6',
  bg2: '#d4edda',
};
