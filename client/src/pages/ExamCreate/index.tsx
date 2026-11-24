// 出卷页 — AI 生成、打勾选择题型+数量、年级选择、逐题编辑、保存/发布、导出
import { useState, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { teacherApi, ClassData } from '../../api/teacher';
import { teachingAssistantApi } from '../../api/teachingAssistant';
import GenerationProgress, { GenerationProgressStream } from '../../components/FloatingAssistant/GenerationProgress';
import type { GenStatus } from '../../components/FloatingAssistant/GenerationProgress';
import {
  colors, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary, chipStyle,
  inputStyle, labelStyle,
  IconPlus, IconTrash, IconEdit, IconRefresh, IconFile, IconBack, IconCheck,
} from '../../design-system';

const TYPE_LABELS: Record<string, string> = {
  choice: '选择题', fill: '填空题', translation: '翻译题',
  reading: '阅读理解', writing: '写作题', listening: '听力题',
  seven_choice: '七选五', grammar_fill: '语法填空', error_correction: '短文改错',
  cloze: '完形填空', judge: '判断题', answer: '简答题',
  applied_writing: '应用写作', continuation_writing: '读后续写',
};

// 年级 → 题型配置（常规考试模式自动填充）
// 基于各学段真实考试结构：小学（校内）、初中（中考）、高中（高考新课标Ⅰ卷）、大学（四六级）
// ⚠️ 初中三个年级统一使用中考笔试题型，高中三个年级统一使用高考新课标Ⅰ卷笔试题型
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

const GRADE_OPTIONS = [
  '', '三年级', '四年级', '五年级', '六年级',
  '七年级', '八年级', '九年级', '高一', '高二', '高三',
  '四级', '六级',
];

const XS = 8;

export default function ExamCreate() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const examIdParam = searchParams.get('id');

  const [form, setForm] = useState({
    title: '', difficulty: 2, durationMinutes: 60,
    knowledgePoints: '', grade: '',
  });
  // 生成模式: 'standard' = 常规考试（按年级自动匹配题型）, 'custom' = 自定义题型数量
  const [qMode, setQMode] = useState<'standard' | 'custom'>('standard');
  const [typeCounts, setTypeCounts] = useState<Record<string, number>>({
    choice: 8, fill: 5, reading: 1, writing: 1,
  });
  const [additionalReferences, setAdditionalReferences] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState(false);  // AI生成完成后设为 true
  const [saving, setSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [lastSavedTime, setLastSavedTime] = useState('');
  const [exam, setExam] = useState<any>(null);
  const [classes, setClasses] = useState<ClassData[]>([]);
  const [publishClassId, setPublishClassId] = useState('');
  const [showPublishPicker, setShowPublishPicker] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState('');
  const [loadingExam, setLoadingExam] = useState(false);
  const [refreshingAnswerSheet, setRefreshingAnswerSheet] = useState(false);

  // 生成进度（整体）
  const [genStatus, setGenStatus] = useState<GenStatus>('idle');
  const [activeSkillName, setActiveSkillName] = useState('');
  const [genStreamText, setGenStreamText] = useState('');
  const [latestExamId, setLatestExamId] = useState<number | null>(null);
  const genTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 按题型并行生成进度
  const [parallelTypes, setParallelTypes] = useState<{ qtype: string; label: string; count: number }[]>([]);
  const [parallelResults, setParallelResults] = useState<Record<string, { label: string; count: number; status: 'pending' | 'generating' | 'success' | 'error'; error?: string }>>({});
  const [parallelSuccess, setParallelSuccess] = useState(false);
  const [parallelError, setParallelError] = useState('');

  useEffect(() => {
    teacherApi.listClasses().then(setClasses).catch(() => {});
  }, []);

  useEffect(() => {
    if (!examIdParam) return;
    setLoadingExam(true);
    teacherApi.getExam(examIdParam)
      .then((data) => {
        if (data.questions) {
          data.questions = data.questions.map((q: any, i: number) => ({ ...q, _idx: i }));
        }
        setExam(data);
        // 已有试卷加载后标记为已保存
        if (data.updated_at) {
          setIsSaved(true);
        }
        setForm({
          title: data.title,
          difficulty: data.difficulty,
          durationMinutes: data.duration_minutes,
          knowledgePoints: (data.knowledge_points || []).join(', '),
          grade: data.grade || '',
        });
        if (data.questions?.length) {
          const counts: Record<string, number> = {};
          const allTypes = Object.keys(TYPE_LABELS);
          allTypes.forEach(t => { counts[t] = 0; });
          data.questions.forEach((q: any) => {
            if (counts[q.type] !== undefined) counts[q.type]++;
          });
          const nonZero = Object.fromEntries(
            Object.entries(counts).filter(([, v]) => v > 0)
          );
          if (Object.keys(nonZero).length > 0) setTypeCounts(nonZero);
        }
        if (data.grade && GRADE_QUESTION_CONFIG[data.grade]) {
          setQMode('custom');
        }
      })
      .catch((err: any) => setError(err?.response?.data?.detail || '加载试卷失败'))
      .finally(() => setLoadingExam(false));
  }, [examIdParam]);

  // 常规考试模式：年级变化时自动填充题型
  useEffect(() => {
    if (qMode === 'standard' && form.grade && GRADE_QUESTION_CONFIG[form.grade]) {
      setTypeCounts({ ...GRADE_QUESTION_CONFIG[form.grade].defaults });
    }
  }, [qMode, form.grade]);

  const toggleType = (type: string) => {
    setTypeCounts((prev) => {
      const next = { ...prev };
      if (next[type] > 0) {
        delete next[type];
      } else {
        next[type] = type === 'reading' ? 1 : 5;
      }
      return next;
    });
  };

  const updateTypeCount = (type: string, val: number) => {
    if (val <= 0) {
      setTypeCounts((prev) => {
        const next = { ...prev };
        delete next[type];
        return next;
      });
    } else {
      setTypeCounts((prev) => ({ ...prev, [type]: val }));
    }
  };

  const totalQuestionCount = Object.values(typeCounts).reduce((a, b) => a + b, 0);
  const effectiveQuestionCount = Object.entries(typeCounts).reduce((sum, [type, count]) => {
    return sum + (type === 'reading' ? count * 5 : count);
  }, 0);

  const handleGenerateStream = async () => {
    // 流式并行生成（使用 SSE 方案 A）
    if (!form.title.trim()) { alert('请输入试卷标题'); return; }
    if (totalQuestionCount <= 0) { alert('请选择至少一种题型'); return; }
    setGenerating(true); setGenerated(false); setError(''); setExam(null);
    setGenStatus('idle'); setGenStreamText(''); setLatestExamId(null);
    setParallelSuccess(false); setParallelError('');
    setIsSaved(false);

    // 初始化题型进度
    const typeEntries = Object.entries(typeCounts)
      .filter(([, count]) => count > 0)
      .map(([qtype, count]) => ({
        qtype,
        label: TYPE_LABELS[qtype] || qtype,
        count,
      }));
    setParallelTypes(typeEntries);
    const initResults: Record<string, any> = {};
    typeEntries.forEach(t => {
      initResults[t.qtype] = { label: t.label, count: t.count, status: 'pending' };
    });
    setParallelResults(initResults);

    setGenStatus('generating');

    try {
      const kps = form.knowledgePoints.split(/[,，、、]/).map(s => s.trim()).filter(Boolean);
      const types = Object.keys(typeCounts);

      const response = await teacherApi.generateExamStream({
        title: form.title,
        difficulty: form.difficulty,
        question_count: totalQuestionCount,
        duration_minutes: form.durationMinutes,
        knowledge_points: kps,
        question_types: types,
        question_type_counts: typeCounts,
        grade: form.grade || undefined,
        additional_references: additionalReferences || undefined,
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(errText || `HTTP ${response.status}`);
      }

      const eventStream = response.body?.getReader();
      if (!eventStream) throw new Error('无法读取响应流');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await eventStream.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';  // 保留不完整行

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(line.slice(6));

            if (event.type === 'type_start') {
              setParallelResults(prev => ({
                ...prev,
                [event.qtype]: {
                  ...prev[event.qtype],
                  label: event.label,
                  count: event.count,
                  status: 'generating',
                },
              }));
              setGenStreamText(prev => prev + `▶ 开始生成${event.label}...\n`);
            } else if (event.type === 'type_done') {
              setParallelResults(prev => ({
                ...prev,
                [event.qtype]: {
                  ...prev[event.qtype],
                  label: event.label,
                  count: event.count,
                  status: 'success',
                },
              }));
              setGenStreamText(prev => prev + `✓ ${event.label}生成完成\n`);
            } else if (event.type === 'type_error') {
              setParallelResults(prev => ({
                ...prev,
                [event.qtype]: {
                  ...prev[event.qtype],
                  label: event.label,
                  count: event.count,
                  status: 'error',
                  error: event.error,
                },
              }));
              setGenStreamText(prev => prev + `✕ ${event.label}失败: ${event.error}\n`);
            } else if (event.type === 'exam_done') {
              const data = event.data;
              if (data.questions) {
                data.questions = data.questions.map((q: any, i: number) => ({ ...q, _idx: i }));
              }
              setExam(data);
              setLatestExamId(data?.id || null);
              setGenerated(true);
              setParallelSuccess(true);
              setGenStatus('success');
              setGenStreamText(prev => prev + '\n✅ 试卷生成完成！');
              if (data._partial_warning) {
                setParallelError(data._partial_warning);
              }
              // 2 秒后收起进度
              setTimeout(() => { setGenStatus('idle'); setGenerating(false); }, 2000);
            } else if (event.type === 'error') {
              const errMsg = event.message || '生成失败';
              setParallelError(errMsg);
              setError(errMsg);
              setGenStatus('error');
              setGenStreamText(prev => prev + `\n❌ 失败：${errMsg}`);
              setTimeout(() => { setGenStatus('idle'); setGenerating(false); }, 5000);
            }
          } catch { /* 忽略解析错误 */ }
        }
      }
    } catch (err: any) {
      const errMsg = err?.message || '网络错误';
      setParallelError(errMsg);
      setError(errMsg);
      setGenStatus('error');
      setGenStreamText(prev => prev + `\n❌ 失败：${errMsg}`);
      setGenerating(false);
      setTimeout(() => { setGenStatus('idle'); }, 5000);
    }
  };

  const handleGenerate = async () => {
    if (!form.title.trim()) { alert('请输入试卷标题'); return; }
    if (totalQuestionCount <= 0) { alert('请选择至少一种题型'); return; }
    setGenerating(true); setGenerated(false); setError(''); setExam(null);
    setGenStatus('idle'); setGenStreamText(''); setLatestExamId(null);
    setIsSaved(false);

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

    // 模拟实时输出消息
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
      const kps = form.knowledgePoints.split(/[,，、、]/).map(s => s.trim()).filter(Boolean);
      const types = Object.keys(typeCounts);
      const data = await teacherApi.generateExam({
        title: form.title, difficulty: form.difficulty,
        question_count: totalQuestionCount, duration_minutes: form.durationMinutes,
        knowledge_points: kps, question_types: types,
        question_type_counts: typeCounts,
        grade: form.grade || undefined,
        additional_references: additionalReferences || undefined,
      });
      if (genTimerRef.current) clearInterval(genTimerRef.current);
      if (data.partial_warning) {
        setGenStreamText(prev => prev + `\n⚠️ 部分题目未生成：${data.partial_warning}`);
        setError(data.partial_warning);
        setGenStatus('error');
        // 错误展示 5 秒后收起
        setTimeout(() => { setGenStatus('idle'); setGenerating(false); }, 5000);
      } else {
        setGenStreamText(prev => prev + '\n✅ 生成完成！');
        setGenStatus('success');
        // 成功展示 2 秒后收起进度组件
        setTimeout(() => { setGenStatus('idle'); setGenerating(false); }, 2000);
      }
      if (data.questions) {
        data.questions = data.questions.map((q: any, i: number) => ({ ...q, _idx: i }));
      }
      setExam(data);
      setLatestExamId(data?.id || null);
      setGenerated(true);
    } catch (err: any) {
      if (genTimerRef.current) clearInterval(genTimerRef.current);
      const errMsg = err?.response?.data?.detail || err.message || '生成失败';
      setGenStreamText(prev => prev + `\n❌ 失败：${errMsg}`);
      setError(errMsg);
      setGenStatus('error');
      setGenerating(false);
      // 错误展示 5 秒后收起
      setTimeout(() => { setGenStatus('idle'); }, 5000);
    }
  };

  const handleSaveDraft = async () => {
    if (!exam?.id) return;
    setSaving(true);
    setIsSaved(false);
    try {
      await teacherApi.updateExam(exam.id, {
        title: form.title,
        questions: exam.questions,
        total_score: exam.total_score,
        difficulty: form.difficulty,
        duration_minutes: form.durationMinutes,
        knowledge_points: form.knowledgePoints.split(/[,，、、]/).map(s => s.trim()).filter(Boolean),
        grade: form.grade || undefined,
      });
      setIsSaved(true);
    } catch (err: any) {
      alert(err?.response?.data?.detail || '保存失败');
    } finally { setSaving(false); }
  };

  // 发布时弹窗选择目标班级
  const handlePublishClick = () => {
    setPublishClassId(String(exam?.class_id || ''));
    setShowPublishPicker(true);
  };

  const handlePublishConfirm = async () => {
    if (!exam?.id) return;
    if (!publishClassId) { alert('请选择目标班级'); return; }
    setPublishing(true);
    try {
      const publishResult = await teacherApi.publishExam(exam.id, { class_id: Number(publishClassId) });
      // 更新 exam 状态和答题卡信息
      const updated = {
        ...exam,
        status: 'published',
        class_id: Number(publishClassId),
        answer_sheet: publishResult?.answer_sheet || exam.answer_sheet,
      };
      setExam(updated);
      setShowPublishPicker(false);
      alert('试卷已发布，答题卡已自动生成');
    } catch (err: any) {
      alert(err?.response?.data?.detail || '发布失败');
    } finally { setPublishing(false); }
  };

  const updateQuestion = (i: number, field: string, value: any) => {
    const qs = [...exam.questions];
    qs[i] = { ...qs[i], [field]: value };
    setExam({ ...exam, questions: qs });
  };

  const updateOption = (qIdx: number, oIdx: number, value: string) => {
    const qs = [...exam.questions];
    const opts = [...(qs[qIdx].options || [])];
    opts[oIdx] = value;
    qs[qIdx] = { ...qs[qIdx], options: opts };
    setExam({ ...exam, questions: qs });
  };

  const deleteQuestion = (i: number) => {
    if (!confirm('确定删除第 ' + (i + 1) + ' 题？')) return;
    const qs = exam.questions.filter((_: any, idx: number) => idx !== i);
    setExam({ ...exam, questions: qs });
  };

  const handleExport = () => {
    if (!exam?.questions?.length) return;
    const difficultyLabel = { 1: '简单', 2: '中等', 3: '困难' }[Number(exam.difficulty) as 1|2|3] || '中等';
    const now = new Date().toLocaleDateString('zh-CN');
    const questionsHtml = exam.questions.map((q: any, i: number) => {
      const typeLabel = TYPE_LABELS[q.type] || q.type;
      let body = '';
      if ((q.type === 'choice' || q.type === 'seven_choice') && Array.isArray(q.options) && q.options.length > 0 && !Array.isArray(q.options[0])) {
        body = '<div class="options">' + q.options.map((opt: string, j: number) =>
          '<div class="option">' + String.fromCharCode(65 + j) + '. ' + opt + '</div>'
        ).join('') + '</div>';
      } else if (q.type === 'cloze' && Array.isArray(q.options) && Array.isArray(q.options[0])) {
        body = '<div class="cloze-options">' + q.options.map((blankOpts: string[], bi: number) =>
          '<div class="cloze-blank"><strong>' + ((q.blank_start_number || 1) + bi) + '.</strong> ' +
          blankOpts.map((opt: string, oi: number) =>
            '<span class="cloze-option">' + String.fromCharCode(65 + oi) + '. ' + opt + '</span>'
          ).join(' ')
        ).join('') + '</div>';
      } else if (q.type === 'fill') {
        body = '<div class="fill-blank">______</div>';
      } else if (q.type === 'reading') {
        let readingHtml = '';
        if (q.passage) {
          const paragraphs = q.passage.split(/\n\s*\n/).filter((p: string) => p.trim());
          readingHtml += '<div class="reading-passage">' +
            paragraphs.map((p: string) => '<p class="reading-para">' + p.replace(/\n/g, '<br>') + '</p>').join('') +
            '</div>';
        }
        if (q.sub_questions?.length) {
          readingHtml += '<div class="reading-questions">';
          q.sub_questions.forEach((sq: any, sj: number) => {
            readingHtml += '<div class="reading-sub-q">' +
              '<div class="q-stem"><strong>' + (sq.question_number || sj + 1) + '.</strong> ' + sq.stem + ' <span style="color:#888;font-size:12px;">[' + (sq.score || '?') + '分]</span></div>';
            if (sq.options?.length) {
              readingHtml += '<div class="options">' + sq.options.map((opt: string, oj: number) =>
                '<div class="option">' + String.fromCharCode(65 + oj) + '. ' + opt + '</div>'
              ).join('') + '</div>';
            }
            readingHtml += '<div class="reading-answer-space"></div></div>';
          });
          readingHtml += '</div>';
        }
        body = readingHtml;
      } else if (q.type === 'writing' || q.type === 'applied_writing' || q.type === 'continuation_writing') {
        body = '<div class="writing-stem">' + (q.stem || q.question || '') + '</div>';
        if (!(q.stem || q.question)) {
          body += '<div class="writing-area"></div>';
        }
      }
      const stemText = (q.type === 'reading' || q.type === 'writing' || q.type === 'applied_writing' || q.type === 'continuation_writing') ? '' : (q.stem || q.question || '');
      return '<div class="question">' +
        '<div class="q-header">' +
          '<span class="q-num">' + (i + 1) + '.</span>' +
          '<span class="q-type">（' + typeLabel + '）</span>' +
          '<span class="q-score">[' + (q.score || '') + '分]</span>' +
        '</div>' +
        (stemText ? '<div class="q-stem">' + stemText + '</div>' : '') +
        body +
      '</div>';
    }).join('');

    const html = '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n<title>' + exam.title + '</title>\n<style>\n' +
      '  @page { margin: 2.5cm 2cm; }\n' +
      '  * { margin: 0; padding: 0; box-sizing: border-box; }\n' +
      '  body { font-family: "Times New Roman", "SimSun", "宋体", serif; font-size: 14px; line-height: 1.8; color: #000; padding: 20px; }\n' +
      '  .paper { max-width: 210mm; margin: 0 auto; }\n' +
      '  .header { text-align: center; margin-bottom: 30px; padding-bottom: 15px; border-bottom: 2px solid #000; }\n' +
      '  .header h1 { font-size: 22px; font-weight: bold; letter-spacing: 2px; margin-bottom: 8px; }\n' +
      '  .header .info { display: flex; justify-content: space-between; font-size: 13px; color: #333; }\n' +
      '  .score-table { width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 13px; }\n' +
      '  .score-table th, .score-table td { border: 1px solid #999; padding: 6px 10px; text-align: center; }\n' +
      '  .score-table th { background: #f0f0f0; font-weight: 600; }\n' +
      '  .notice { font-size: 12px; color: #555; margin-bottom: 20px; padding: 8px 12px; border: 1px dashed #ccc; }\n' +
      '  .question { margin-bottom: 20px; padding: 4px 0; }\n' +
      '  .q-header { font-weight: 600; margin-bottom: 4px; font-size: 14px; }\n' +
      '  .q-num { margin-right: 4px; }\n' +
      '  .q-type { color: #555; font-weight: normal; font-size: 13px; margin-right: 6px; }\n' +
      '  .q-score { color: #888; font-weight: normal; font-size: 12px; }\n' +
      '  .q-stem { padding-left: 24px; margin-bottom: 6px; }\n' +
      '  .options { padding-left: 32px; }\n' +
      '  .option { margin: 2px 0; }\n' +
      '  .fill-blank { padding-left: 32px; color: #333; font-size: 16px; letter-spacing: 4px; }\n' +
      '  .cloze-options { padding-left: 24px; margin-top: 8px; }\n' +
      '  .cloze-blank { margin: 6px 0; font-size: 13px; line-height: 1.6; }\n' +
      '  .cloze-option { margin-right: 12px; color: #333; }\n' +
      '  .reading-passage { margin: 4px 0 12px 24px; padding: 12px 16px; font-size: 13px; line-height: 1.8; }\n' +
      '  .reading-para { margin: 0 0 0.6em 0; text-indent: 2em; }\n' +
      '  .reading-questions { padding-left: 24px; }\n' +
      '  .reading-sub-q { margin-bottom: 12px; }\n' +
      '  .reading-sub-q .q-stem { font-size: 13px; padding-left: 0; margin-bottom: 4px; }\n' +
      '  .reading-answer-space { height: 8px; }\n' +
      '  .writing-stem { padding-left: 24px; margin: 4px 0 8px; line-height: 1.8; white-space: pre-wrap; }\n' +
      '  .writing-area { min-height: 200px; margin: 8px 0 0 24px; border-bottom: 1px solid #ccc; }\n' +
      '  .answer-section { margin-top: 24px; padding-top: 16px; border-top: 1px dashed #ccc; }\n' +
      '  .answer-section h3 { font-size: 15px; font-weight: bold; margin-bottom: 10px; }\n' +
      '  .answer-item { font-size: 13px; margin: 3px 0; padding-left: 12px; }\n' +
      '  @media print { body { padding: 0; } .no-print { display: none !important; } .answer-section { page-break-before: always; } }\n' +
    '</style>\n</head>\n<body>\n<div class="paper">\n' +
    '  <div class="header">\n    <h1>' + exam.title + '</h1>\n' +
    '    <div class="info">\n      <span>考试时间：' + (exam.duration_minutes || 60) + ' 分钟</span>\n' +
    '      <span>满分：' + (exam.total_score || 100) + ' 分</span>\n' +
    '      <span>难度：' + difficultyLabel + '</span>\n      <span>日期：' + now + '</span>\n    </div>\n  </div>\n\n' +
    '  <table class="score-table">\n    <tr><th>题号</th>' +
    exam.questions.map((_: any, i: number) => '<th>' + (i + 1) + '</th>').join('') +
    '<th>总分</th></tr>\n    <tr><td>得分</td>' +
    exam.questions.map(() => '<td></td>').join('') +
    '<td></td></tr>\n  </table>\n\n' +
    '  <div class="notice">注意事项：1. 本试卷共 ' + exam.questions.length + ' 题，满分 ' + (exam.total_score || 100) + ' 分。2. 请将答案填写在答题卡上。3. 考试结束后，将本试卷和答题卡一并交回。</div>\n\n' +
    questionsHtml + '\n\n' +
    '  <div class="answer-section">\n    <h3>参考答案</h3>\n' +
    exam.questions.map((q: any, i: number) => {
      if (q.type === 'reading' && q.sub_questions?.length) {
        const subAnswers = q.sub_questions.map((sq: any, sj: number) =>
          '<div class="answer-item" style="padding-left:24px;"><strong>' + (i + 1) + '-' + (sq.question_number || sj + 1) + '.</strong> ' + (sq.answer || '') + (sq.explanation ? '<span style="color:#888;margin-left:8px;">（' + sq.explanation + '）</span>' : '') + '</div>'
        ).join('');
        return '<div class="answer-item"><strong>' + (i + 1) + '.</strong> 阅读理解</div>' + subAnswers;
      }
      return '<div class="answer-item"><strong>' + (i + 1) + '.</strong> ' + (q.answer || '') + (q.explanation ? '<span style="color:#888;margin-left:8px;">（' + q.explanation + '）</span>' : '') + '</div>';
    }).join('') + '\n  </div>\n\n' +
    '  <div class="no-print" style="text-align:center;margin-top:20px;color:#999;font-size:12px;">如需打印，请使用浏览器打印功能（Ctrl+P）</div>\n' +
    '</div>\n</body>\n</html>';

    const win = window.open('', '_blank');
    if (win) {
      win.document.write(html);
      win.document.close();
    } else {
      alert('导出打印被浏览器拦截，请允许弹窗后重试');
    }
  };

  // ── 下载 GraderFlow 答题卡 PDF（带认证，通过 Axios 发送 Bearer Token） ──
  const handleDownloadAnswerSheetPdf = async () => {
    if (!exam?.id) return;
    try {
      const blob = await teacherApi.downloadGraderflowSheetPdf(exam.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `GraderFlow答题卡_${exam.title || exam.id}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert('下载 GraderFlow PDF 失败: ' + (e?.response?.data?.detail || e.message));
    }
  };

  // ── 刷新 GraderFlow 答题卡（重新生成） ──
  const handleRefreshAnswerSheet = async () => {
    if (!exam?.id || refreshingAnswerSheet) return;
    setRefreshingAnswerSheet(true);
    try {
      const config = await teacherApi.regenerateGraderflowSheet(exam.id);
      // 给 html_url 追加时间戳避免浏览器缓存
      if (config.html_url && config.html_url.indexOf('?_t=') === -1) {
        config.html_url += (config.html_url.includes('?') ? '&' : '?_t=') + Date.now();
      }
      setExam((prev: any) => prev ? { ...prev, answer_sheet: config } : prev);
      // 短暂闪现绿色提示反馈
      const feedbackEl = document.getElementById('answer-sheet-refresh-feedback');
      if (feedbackEl) {
        feedbackEl.style.opacity = '1';
        setTimeout(() => { feedbackEl.style.opacity = '0'; }, 2000);
      }
    } catch (e: any) {
      alert('刷新 GraderFlow 答题卡失败: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setRefreshingAnswerSheet(false);
    }
  };

  if (loadingExam) {
    return <div style={{ textAlign: 'center', padding: 60, color: colors['text-tertiary'] }}>加载试卷中...</div>;
  }

  return (
    <>
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      {/* 顶栏 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: space.xl,
      }}>
        <h1 style={{
          margin: 0, fontSize: typography['display-lg'].fontSize,
          fontWeight: typography['display-lg'].fontWeight,
          letterSpacing: typography['display-lg'].letterSpacing,
          color: colors['text-primary'],
        }}>{examIdParam ? '编辑试卷' : 'AI 出卷'}</h1>
        <button onClick={() => navigate('/exams')} style={btnSmallSecondary}>
          <IconBack size={13} color={colors['text-secondary']} /> 返回列表
        </button>
      </div>

      {/* 参数表单 */}
      <div style={{ ...cardStyle, marginBottom: space.xl, maxWidth: 640 }}>
        <div style={{ marginBottom: space.md }}>
          <label style={labelStyle}>试卷标题</label>
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
            style={inputStyle} placeholder="如：Unit 3 单元测试" />
        </div>
        <div style={{ display: 'flex', gap: space.md, marginBottom: space.md }}>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>难度</label>
            <select value={form.difficulty} onChange={(e) => setForm({ ...form, difficulty: Number(e.target.value) })} style={inputStyle}>
              <option value={1}>简单</option>
              <option value={2}>中等</option>
              <option value={3}>困难</option>
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>年级</label>
            <select value={form.grade} onChange={(e) => {
              const g = e.target.value;
              setForm({ ...form, grade: g });
              // 标准模式自动填充题型
              if (qMode === 'standard' && g && GRADE_QUESTION_CONFIG[g]) {
                setTypeCounts({ ...GRADE_QUESTION_CONFIG[g].defaults });
              }
            }} style={inputStyle}>
              <option value="">-- 请选择年级 --</option>
              {GRADE_OPTIONS.filter(Boolean).map((g) => (
                <option key={g} value={g}>{g}</option>
              ))}
            </select>
          </div>
        </div>
        <div style={{ marginBottom: space.md }}>
          <label style={labelStyle}>建议用时（分）</label>
          <input type="number" value={form.durationMinutes}
            onChange={(e) => setForm({ ...form, durationMinutes: Number(e.target.value) })} style={inputStyle} />
        </div>

        {/* 题型模式切换 */}
        <div style={{ marginBottom: space.md }}>
          <label style={{ ...labelStyle, marginBottom: XS }}>题型设置方式</label>
          <div style={{ display: 'flex', gap: XS, marginTop: XS }}>
            <button onClick={() => {
              setQMode('standard');
              if (form.grade && GRADE_QUESTION_CONFIG[form.grade]) {
                setTypeCounts({ ...GRADE_QUESTION_CONFIG[form.grade].defaults });
              } else {
                setTypeCounts({ choice: 8, fill: 5, reading: 1, writing: 1 });
              }
            }} style={{
              flex: 1, padding: '9px 0', borderRadius: radius.pill, border: `1.5px solid ${qMode === 'standard' ? colors.primary : colors.hairline}`,
              background: qMode === 'standard' ? colors.primary : colors.canvas,
              color: qMode === 'standard' ? '#fff' : colors['text-primary'],
              fontSize: 13, fontWeight: 500, cursor: 'pointer', transition: 'all 0.15s',
            }}>
              常规考试
            </button>
            <button onClick={() => setQMode('custom')} style={{
              flex: 1, padding: '9px 0', borderRadius: radius.pill, border: `1.5px solid ${qMode === 'custom' ? colors.primary : colors.hairline}`,
              background: qMode === 'custom' ? colors.primary : colors.canvas,
              color: qMode === 'custom' ? '#fff' : colors['text-primary'],
              fontSize: 13, fontWeight: 500, cursor: 'pointer', transition: 'all 0.15s',
            }}>
              自定义题型数量
            </button>
          </div>
        </div>

        {/* 题型选择 */}
        <div style={{ marginBottom: space.md }}>
          <label style={{ ...labelStyle, marginBottom: XS }}>
            {qMode === 'standard' ? '试卷题型（按年级自动匹配）' : '自定义题型及数量'}
          </label>
          {!form.grade ? (
            <p style={{ fontSize: 12, color: colors['text-tertiary'], marginTop: XS }}>
              请先选择年级以显示对应题型
            </p>
          ) : qMode === 'standard' ? (
            /* 常规考试模式：只读显示各年级题型和数量 */
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: space.sm, marginTop: XS }}>
              {Object.entries(typeCounts).filter(([, count]) => count > 0).map(([type, count]) => (
                <span key={type} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  padding: '6px 14px', borderRadius: radius.pill,
                  border: `1px solid ${colors.success}`, background: colors['block-lime'],
                  fontSize: 13, color: colors['text-primary'], fontWeight: 500,
                }}>
                  {TYPE_LABELS[type] || type}
                  <span style={{ fontSize: 12, color: colors['text-secondary'], marginLeft: 2 }}>
                    × {count}
                  </span>
                </span>
              ))}
            </div>
          ) : (
            /* 自定义题型模式：显示年级对应的题型并允许调数量 */
            <div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: space.sm, marginTop: XS }}>
                {(GRADE_QUESTION_CONFIG[form.grade]?.types || Object.keys(TYPE_LABELS)).map((type) => {
                  const checked = (typeCounts[type] || 0) > 0;
                  return (
                    <label key={type} style={{
                      display: 'flex', alignItems: 'center', gap: XS,
                      padding: '6px 14px', borderRadius: radius.pill, cursor: 'pointer',
                      border: `1px solid ${checked ? colors.success : colors.hairline}`,
                      background: checked ? colors['block-lime'] : colors['surface-soft'],
                      userSelect: 'none', transition: 'all 0.15s',
                    }}>
                      <input type="checkbox" checked={checked}
                        onChange={() => toggleType(type)}
                        style={{ accentColor: colors.success, width: 16, height: 16 }} />
                      <span style={{
                        fontSize: 13, color: colors['text-primary'],
                        fontWeight: checked ? 500 : 400, minWidth: 50,
                      }}>{TYPE_LABELS[type] || type}</span>
                      {checked && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                          <input type="number" min={1} max={50}
                            value={typeCounts[type]}
                            onChange={(e) => updateTypeCount(type, Math.max(1, Number(e.target.value) || 1))}
                            style={{ width: 48, padding: '2px 6px', border: `1px solid ${colors.hairline}`, borderRadius: radius.sm, fontSize: 13, textAlign: 'center' }}
                            onClick={(e) => e.stopPropagation()} />
                          <span style={{ fontSize: 12, color: colors['text-secondary'] }}>{type === 'reading' || type === 'cloze' ? '篇' : '道'}</span>
                        </span>
                      )}
                    </label>
                  );
                })}
              </div>
            </div>
          )}
          {form.grade && (
            <p style={{ fontSize: 12, color: colors['text-tertiary'], marginTop: XS }}>
              共 <strong>{totalQuestionCount}</strong> 大题
              （含阅读理解每篇5道子题，实际共 <strong>{effectiveQuestionCount}</strong> 小题）
            </p>
          )}
        </div>

        <div style={{ marginBottom: space.sm }}>
          <label style={labelStyle}>知识点（逗号分隔）</label>
          <textarea value={form.knowledgePoints} onChange={(e) => setForm({ ...form, knowledgePoints: e.target.value })}
            style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }}
            placeholder="如：一般现在时, 现在进行时, 被动语态" />
        </div>

        {/* 补充输入框 */}
        <div style={{ marginBottom: space.lg }}>
          <label style={labelStyle}>补充要求（可选）</label>
          <textarea value={additionalReferences}
            onChange={(e) => setAdditionalReferences(e.target.value)}
            style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }}
            placeholder="如：教材版本、考察侧重点、特殊排版要求..." />
        </div>

        {!examIdParam && (
          genStatus !== 'idle' ? (
            parallelTypes.length > 1 && genStatus === 'generating' ? (
              <GenerationProgressStream
                types={parallelTypes}
                typeResults={parallelResults}
                streamText={genStreamText}
                error={parallelError}
                success={parallelSuccess}
                successUrl={parallelSuccess && latestExamId ? `/exams/create?id=${latestExamId}` : undefined}
                successLabel="点击查看试卷"
              />
            ) : (
              <GenerationProgress
                status={genStatus}
                skillName={activeSkillName}
                skillTypeLabel="试卷"
                successUrl={genStatus === 'success' && latestExamId ? `/exams/create?id=${latestExamId}` : undefined}
                successLabel="点击查看试卷"
                streamText={genStreamText}
              />
            )
          ) : (
            <button onClick={Object.keys(typeCounts).length > 1 ? handleGenerateStream : handleGenerate}
              disabled={generating}
              style={{
                width: '100%', padding: '12px', borderRadius: radius.pill, border: 'none', cursor: 'pointer',
                background: generating ? colors['text-tertiary'] : generated ? colors.success : colors.primary,
                color: colors['on-primary'], fontSize: 16, fontWeight: 500,
                opacity: generating ? 0.6 : 1,
              }}>
              {generating ? 'AI 生成中...' : generated ? 'AI 生成完成'
                : Object.keys(typeCounts).length > 1 ? 'AI 并行生成试卷' : 'AI 生成试卷'}
            </button>
          )
        )}

        {error && (
          <div style={{
            marginTop: space.md, padding: space.sm, background: '#fef2f2',
            border: '1px solid #fecaca', borderRadius: radius.md,
            color: colors.danger, fontSize: 13,
          }}>{error}</div>
        )}
      </div>

      {/* 试卷预览 */}
      {exam && (
        <div style={{ ...cardStyle, marginBottom: space.xl, background: colors['block-lime'] }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginBottom: space.md,
          }}>
            <h3 style={{
              margin: 0, fontSize: typography.headline.fontSize,
              fontWeight: typography.headline.fontWeight,
              color: colors['text-primary'],
            }}>{exam.title || form.title}</h3>
            <div style={{ display: 'flex', gap: XS, alignItems: 'center' }}>
              {exam.id && exam.status !== 'published' && (
                <>
                  <button onClick={handleSaveDraft} disabled={saving}
                    style={{
                      ...btnSmallSecondary,
                      opacity: saving ? 0.5 : 1,
                      color: isSaved ? '#52c41a' : undefined,
                      borderColor: isSaved ? '#52c41a' : undefined,
                    }}>
                    {saving ? '保存中...' : isSaved ? '已保存' : '保存'}
                  </button>
                </>
              )}
              {exam.id && exam.status === 'draft' && (
                <button onClick={handlePublishClick} style={btnSmall}>
                  <IconCheck size={12} color="#fff" /> 发布
                </button>
              )}
              {exam.questions?.length > 0 && (
                <button onClick={handleExport} style={btnSmallSecondary}>
                  <IconFile size={12} color={colors['text-secondary']} /> 导出打印
                </button>
              )}
            </div>
          </div>

          <p style={{ fontSize: typography['body-sm'].fontSize, color: colors['text-secondary'], margin: `0 0 ${space.md}px` }}>
            总分: {exam.total_score} 分 | 共 {exam.questions?.length || 0} 题
          </p>

          {/* GraderFlow 答题卡信息 */}
          {exam.answer_sheet && (
            <div style={{
              background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: radius.md,
              padding: '10px 14px', marginBottom: space.md, fontSize: 13, position: 'relative',
            }}>
              {/* 刷新成功反馈提示 */}
              <span id="answer-sheet-refresh-feedback" style={{
                position: 'absolute', top: 10, right: 14,
                fontSize: 11, color: '#16a34a', opacity: 0,
                transition: 'opacity 0.3s', pointerEvents: 'none',
              }}>✓ 已刷新</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 16 }}>📋</span>
                <strong style={{ color: '#166534' }}>GraderFlow 答题卡</strong>
                <span style={{
                  background: '#dcfce7', color: '#166534', fontSize: 10,
                  padding: '1px 6px', borderRadius: 3, fontWeight: 600,
                }}>4列矩形框</span>
                <span style={{ color: '#64748b', fontSize: 12 }}>
                  {exam.answer_sheet.total_questions} 题 · {exam.answer_sheet.option_count} 选项
                </span>
                <button
                  onClick={handleRefreshAnswerSheet}
                  disabled={refreshingAnswerSheet}
                  title="重新生成 GraderFlow 答题卡"
                  style={{
                    marginLeft: 'auto', cursor: refreshingAnswerSheet ? 'not-allowed' : 'pointer',
                    border: '1px solid #bbf7d0',
                    background: refreshingAnswerSheet ? '#f0fdf4' : '#dcfce7',
                    borderRadius: 4, padding: '2px 8px',
                    fontSize: 11, color: '#166534', display: 'flex', alignItems: 'center', gap: 3,
                    opacity: refreshingAnswerSheet ? 0.6 : 1,
                    transition: 'opacity 0.2s',
                  }}
                >
                  <span style={{ display: 'inline-flex', animation: refreshingAnswerSheet ? 'spin 1s linear infinite' : 'none' }}>
                    <IconRefresh size={11} color="#166534" />
                  </span> {refreshingAnswerSheet ? '刷新中...' : '刷新'}
                </button>
              </div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 4 }}>
                <a
                  href={exam.answer_sheet.html_url || `/Elearning/api/v1/teacher/exam/${exam.id}/graderflow-sheet-html`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: '#2563eb', textDecoration: 'underline', fontSize: 12 }}
                >HTML 预览</a>
                <span
                  onClick={handleDownloadAnswerSheetPdf}
                  style={{ color: '#2563eb', textDecoration: 'underline', fontSize: 12, cursor: 'pointer' }}
                >下载 PDF</span>
                <span style={{ color: '#64748b', fontSize: 12 }}>
                  (矩形填涂框 · 4列B模式扫描 · 7位考号)
                </span>
              </div>
              <div style={{ marginTop: 4, fontSize: 11, color: '#64748b' }}>
                适合 YOLOv5 检测 + OMR 识别，打印后学生填涂即可扫描批改
              </div>
            </div>
          )}

          {/* 题目列表 */}
          {exam.questions?.map((q: any, i: number) => (
            <div key={i} style={{
              ...cardStyle, marginBottom: space.sm,
              background: colors.canvas, padding: space.md,
            }}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                marginBottom: XS,
              }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: colors['text-primary'] }}>
                  {i + 1}. （{TYPE_LABELS[q.type] || q.type}）[{q.score || '?'}分]
                </span>
                <button onClick={() => deleteQuestion(i)} style={{
                  border: 'none', background: 'none', cursor: 'pointer', color: colors.danger, padding: 4,
                }}>
                  <IconTrash size={14} color={colors.danger} />
                </button>
              </div>

              {/* 题干 */}
              <div style={{ marginBottom: XS }}>
                {q.type === 'reading' ? (
                  <>
                    <textarea value={q.passage || ''} onChange={(e) => updateQuestion(i, 'passage', e.target.value)}
                      style={{ ...inputStyle, minHeight: 80, resize: 'vertical', fontSize: 13 }}
                      placeholder="阅读理解文章内容..." />
                    {q.sub_questions?.map((sq: any, sj: number) => (
                      <div key={sj} style={{ marginTop: XS, paddingLeft: 12, borderLeft: `2px solid ${colors['hairline-soft']}` }}>
                        <div style={{
                          display: 'flex', gap: XS, alignItems: 'center', marginBottom: 4,
                        }}>
                          <span style={{ fontSize: 13, fontWeight: 500, color: colors['text-secondary'] }}>
                            {sq.question_number || sj + 1}. {sq.stem || '子题'}
                          </span>
                          <input value={sq.score || ''}
                            onChange={(e) => {
                              const newQs = [...exam.questions];
                              newQs[i].sub_questions[sj].score = Number(e.target.value) || 0;
                              setExam({ ...exam, questions: newQs });
                            }}
                            style={{ width: 60, ...inputStyle, padding: '2px 6px', fontSize: 12 }}
                            placeholder="分" />
                        </div>
                        {sq.options?.length > 0 && (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                            {sq.options.map((opt: string, oj: number) => (
                              <span key={oj} style={{
                                padding: '2px 8px', background: colors['surface-soft'],
                                borderRadius: radius.sm, fontSize: 12, color: colors['text-secondary'],
                              }}>
                                {String.fromCharCode(65 + oj)}. {opt}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </>
                ) : (
                  <textarea value={q.stem || q.question || ''}
                    onChange={(e) => updateQuestion(i, 'stem', e.target.value)}
                    style={{ ...inputStyle, minHeight: 50, resize: 'vertical' }}
                    placeholder="题目内容..." />
                )}
              </div>

              {/* 选择题选项（普通选择题 + 七选五） */}
              {(q.type === 'choice' || q.type === 'seven_choice') && Array.isArray(q.options) && q.options.length > 0 && !Array.isArray(q.options[0]) && (
                <div style={{ marginTop: XS }}>
                  {q.options.map((opt: string, oi: number) => (
                    <div key={oi} style={{ display: 'flex', gap: XS, marginBottom: 4, alignItems: 'center' }}>
                      <span style={{ fontSize: 13, color: colors['text-secondary'], minWidth: 16 }}>
                        {String.fromCharCode(65 + oi)}.
                      </span>
                      <input value={opt}
                        onChange={(e) => updateOption(i, oi, e.target.value)}
                        style={{ flex: 1, ...inputStyle, padding: '6px 10px', fontSize: 13 }} />
                    </div>
                  ))}
                </div>
              )}

              {/* 完形填空选项（二维数组：每空4个选项） */}
              {q.type === 'cloze' && Array.isArray(q.options) && Array.isArray(q.options[0]) && (
                <div style={{ marginTop: XS, padding: '8px 12px', background: colors['surface-soft'], borderRadius: radius.sm }}>
                  {q.options.map((blankOpts: string[], bi: number) => (
                    <div key={bi} style={{ marginBottom: 6, fontSize: 13, lineHeight: 1.6 }}>
                      <span style={{ fontWeight: 600, color: colors['text-primary'], marginRight: 8 }}>
                        {(q.blank_start_number || 1) + bi}.
                      </span>
                      {blankOpts.map((opt: string, oi: number) => (
                        <span key={oi} style={{ marginRight: 12, color: colors['text-secondary'] }}>
                          {String.fromCharCode(65 + oi)}. {opt}
                        </span>
                      ))}
                    </div>
                  ))}
                </div>
              )}

              {/* 答案 */}
              <div style={{ marginTop: XS, display: 'flex', gap: XS, alignItems: 'center' }}>
                <span style={{ fontSize: 12, fontWeight: 500, color: colors['text-secondary'] }}>答案</span>
                <input value={q.answer || ''} onChange={(e) => updateQuestion(i, 'answer', e.target.value)}
                  style={{ flex: 1, ...inputStyle, padding: '4px 10px', fontSize: 13 }}
                  placeholder={q.type === 'choice' ? '如：A' : '参考答案'} />
              </div>
              <div style={{ marginTop: 4, display: 'flex', gap: XS, alignItems: 'center' }}>
                <span style={{ fontSize: 12, fontWeight: 500, color: colors['text-secondary'] }}>解析</span>
                <input value={q.explanation || ''} onChange={(e) => updateQuestion(i, 'explanation', e.target.value)}
                  style={{ flex: 1, ...inputStyle, padding: '4px 10px', fontSize: 13 }}
                  placeholder="解析说明（选填）" />
              </div>
            </div>
          ))}
        </div>
      )}
      {/* 发布班级选择弹窗 */}
      {showPublishPicker && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000,
        }} onClick={() => setShowPublishPicker(false)}>
          <div style={{
            background: '#fff', borderRadius: radius.lg, padding: space.xl,
            width: 380, maxWidth: '90vw', boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
          }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{
              margin: `0 0 ${space.md}px`, fontSize: typography.headline.fontSize,
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
            <div style={{ display: 'flex', gap: XS }}>
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
    </>
  );
}
