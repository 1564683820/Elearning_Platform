import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import client from '../../api/client';
import { teachingTasks, watchTeachingTask, TeachingTask, TeachingArtifact } from '../../api/teachingTasks';
import './style.css';

const labels: Record<string, string> = { created: '待启动', queued: '等待执行', running: '正在备课', awaiting_input: '需要补充资料',
  awaiting_review: '等待教师审核', approved: '审核通过', published: '已发布', cancelled: '已取消', failed: '执行失败' };
const steps = [['analyze', '分析错题'], ['retrieve', '检索教材'], ['plan', '规划教案'], ['generate', '生成练习'], ['validate', '质量检查'], ['await_review', '教师审核']];
const errors: Record<string, string> = { no_exams: '班级暂无试卷，请先创建并完成考试。', no_graded_wrong_answers: '最近两次试卷中暂无可用的已批改错题与知识点。',
  no_accessible_materials: '请上传属于本班级或您个人的教材，并完成解析与向量化。', no_verified_retrieval_evidence: '没有检索到可核对原文的教材片段，请检查资料解析及向量服务。',
  artifact_validation: '生成内容未通过检查，请补充目标或资料后重试。', access_revoked: '班级权限已失效。', transient_dependency_error: '外部服务暂时不可用。' };

export default function TeachingTasksPage() {
  const [tasks, setTasks] = useState<TeachingTask[]>([]);
  const [selected, setSelected] = useState<TeachingTask | null>(null);
  const [classes, setClasses] = useState<{ id: string; name: string }[]>([]);
  const [classId, setClassId] = useState('');
  const [objective, setObjective] = useState('分析最近两次考试中的薄弱知识点，设计定向巩固教案与练习。');
  const [count, setCount] = useState(10);
  const [minutes, setMinutes] = useState(20);
  const [draft, setDraft] = useState<TeachingArtifact | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const selection = useRef(0);
  const choose = (task: TeachingTask) => {
    selection.current += 1;
    setSelected(task); setDirty(false);
    setDraft(task.artifact.questions ? task.artifact as TeachingArtifact : null);
  };
  useEffect(() => {
    let active = true;
    Promise.all([teachingTasks.list(), client.get<{ data: { id: string; name: string }[] }>('/teacher/classes')])
      .then(([items, response]) => { if (active) { setTasks(items); setClasses(response.data.data); } })
      .catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!selected || !['queued', 'running'].includes(selected.status)) return;
    const id = selected.id, generation = selection.current;
    let active = true;
    const controller = new AbortController();
    const update = (task: TeachingTask) => {
        if (!active || generation !== selection.current) return;
        setSelected(task); setTasks(items => items.map(item => item.id === task.id ? task : item));
        if (task.artifact.questions) setDraft(task.artifact as TeachingArtifact);
    };
    let timer: number | undefined;
    watchTeachingTask(id, controller.signal, update).catch((e: Error) => {
      if (!active || controller.signal.aborted) return;
      setError(e.message);
      // Persisted snapshots let the UI recover even if a proxy buffers/drops SSE.
      timer = window.setInterval(() => {
        teachingTasks.get(id).then(update).catch((error: Error) => { if (active) setError(error.message); });
      }, 3000);
    });
    return () => { active = false; controller.abort(); if (timer) window.clearInterval(timer); };
  }, [selected?.id, selected?.status]);
  async function operate(work: () => Promise<TeachingTask>) {
    const generation = selection.current;
    setBusy(true); setError('');
    try {
      const task = await work();
      setTasks(items => [task, ...items.filter(item => item.id !== task.id)]);
      if (generation === selection.current) choose(task);
    } catch (e) { setError(e instanceof Error ? e.message : '操作失败'); }
    finally { setBusy(false); }
  }
  const editable = !!selected && ['awaiting_review', 'approved'].includes(selected.status);
  const updateDraft = (value: TeachingArtifact) => { setDraft(value); setDirty(true); };
  return <div className="teaching-tasks">
    <header className="tt-header"><div><span className="tt-eyebrow">TEACHING WORKSPACE / 教学工作台</span><h1>让错题成为下一堂课的起点</h1>
      <p>基于班级真实表现与教材证据备课，由教师审核后发布练习。</p></div><span className="tt-marker">教师掌握最后一笔</span></header>
    {error && <div className="tt-error" role="alert">{error}</div>}
    <div className="tt-grid"><aside className="tt-panel">
      <h2>新建教学任务</h2><form onSubmit={event => { event.preventDefault(); void operate(() => teachingTasks.create({ class_id: classId, objective, question_count: count, duration_minutes: minutes })); }}>
        <label>目标班级<select required value={classId} onChange={e => setClassId(e.target.value)}><option value="">请选择班级</option>{classes.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label>教学目标<textarea required maxLength={2000} value={objective} onChange={e => setObjective(e.target.value)} rows={4} /></label>
        <div className="tt-pair"><label>练习题数<input type="number" min={1} max={30} value={count} onChange={e => setCount(Number(e.target.value))} /></label>
          <label>教案时长 / 分钟<input type="number" min={5} max={120} value={minutes} onChange={e => setMinutes(Number(e.target.value))} /></label></div>
        <button disabled={busy || !classId} className="tt-primary">创建任务</button>
      </form><h2 className="tt-history">近期任务</h2>
      {!tasks.length && <p className="tt-muted">暂无任务。选择班级，开始第一次定向备课。</p>}
      {tasks.map(task => <button disabled={busy || dirty} key={task.id} className={`tt-task ${selected?.id === task.id ? 'active' : ''}`} onClick={() => choose(task)}>
        <span>{task.objective}</span><small>{labels[task.status] || task.status} · {new Date(task.created_at).toLocaleDateString()}</small></button>)}
    </aside><main className="tt-panel tt-detail">{!selected ? <div className="tt-empty"><span>01 → 06</span><h2>从统计到课堂，留下每一步依据</h2><p>选择任务后查看执行进度、教材引用和待审核的教案。</p></div> : <>
      <div className="tt-title"><div><span className="tt-eyebrow">任务 {selected.id}</span><h2>{labels[selected.status] || selected.status}</h2></div>
        <div className="tt-actions">{selected.status === 'created' && <button className="tt-primary" disabled={busy} onClick={() => void operate(() => teachingTasks.command(selected, 'run'))}>开始备课</button>}
          {['failed', 'awaiting_input'].includes(selected.status) && <button disabled={busy} onClick={() => void operate(() => teachingTasks.command(selected, 'retry'))}>重新执行</button>}
          {!['published', 'cancelled'].includes(selected.status) && <button disabled={busy} onClick={() => void operate(() => teachingTasks.command(selected, 'cancel'))}>取消任务</button>}</div></div>
      <ol className="tt-steps">{steps.map(([key, label], index) => <li key={key} className={selected.checkpoint.completed?.includes(key) ? 'done' : ''}><b>{String(index+1).padStart(2, '0')}</b>{label}</li>)}</ol>
      {selected.error_code && <div className="tt-error">{errors[selected.error_code] || '执行未完成，请检查模型配置与服务状态后重试。'}</div>}
      {selected.checkpoint.validation_errors?.map((text, i) => <p role="alert" key={i}>{text}</p>)}
      {selected.checkpoint.analysis && <section><h3>班级薄弱点 <small>最近 {selected.checkpoint.analysis.exam_ids.length} 次考试 / {selected.checkpoint.analysis.submission_count} 份已批改作答</small></h3>
        <div className="tt-topics">{selected.checkpoint.analysis.topics.map(topic => <div key={topic.knowledge_point}><strong>{topic.knowledge_point}</strong><span>{topic.wrong} / {topic.observations} 次作答未得满分</span></div>)}</div></section>}
      {!!selected.checkpoint.citations?.length && <section><h3>教材证据</h3>{selected.checkpoint.citations.map(citation => <details key={citation.id}><summary>{citation.id} · {citation.title} · {citation.page ? `第 ${citation.page} 页` : '原文未保留页码'}</summary><blockquote>{citation.snippet}</blockquote><small>文档 {citation.document_id} · 内容版本 {citation.version.slice(0, 12)}</small></details>)}</section>}
      {draft && <section><h3>审核与编辑 <small>版本 {selected.artifact_version}{dirty ? ' · 有未保存修改' : ''}</small></h3>
        <label>练习名称<input disabled={!editable || busy} value={draft.title} maxLength={256} onChange={e => updateDraft({ ...draft, title: e.target.value })} /></label>
        {draft.lesson.map((step, i) => <div className="tt-lesson" key={i}><label>教学环节<input disabled={!editable || busy} value={step.title} onChange={e => updateDraft({ ...draft, lesson: draft.lesson.map((s, n) => n === i ? { ...s, title: e.target.value } : s) })} /></label>
          <label>分钟<input type="number" min={1} disabled={!editable || busy} value={step.minutes} onChange={e => updateDraft({ ...draft, lesson: draft.lesson.map((s, n) => n === i ? { ...s, minutes: Number(e.target.value) } : s) })} /></label>
          <label className="tt-wide">课堂活动<textarea disabled={!editable || busy} value={step.activity} onChange={e => updateDraft({ ...draft, lesson: draft.lesson.map((s, n) => n === i ? { ...s, activity: e.target.value } : s) })} /></label></div>)}
        {draft.questions.map((question, i) => {
          const update = (changes: Partial<typeof question>) => updateDraft({ ...draft, questions: draft.questions.map((q, n) => n === i ? { ...q, ...changes } : q) });
          return <fieldset disabled={!editable || busy} key={i}><legend>题目 {i+1} · {question.knowledge_point} · {question.citation_ids.join(', ')}</legend>
            <label>题干<textarea value={question.stem} onChange={e => update({ stem: e.target.value })} /></label>
            <div className="tt-pair">{question.options.map((option, n) => <label key={n}>选项 {'ABCD'[n]}<input value={option} onChange={e => update({ options: question.options.map((o, x) => x === n ? e.target.value : o) })} /></label>)}</div>
            <div className="tt-pair"><label>正确答案<select value={question.answer} onChange={e => update({ answer: e.target.value as typeof question.answer })}>{['A', 'B', 'C', 'D'].map(a => <option key={a}>{a}</option>)}</select></label>
              <label>分值<input type="number" min={1} value={question.score} onChange={e => { const score = Number(e.target.value); updateDraft({ ...draft, total_score: draft.total_score-question.score+score, questions: draft.questions.map((q, n) => n === i ? { ...q, score } : q) }); }} /></label></div>
            <label>解析<textarea value={question.explanation} onChange={e => update({ explanation: e.target.value })} /></label></fieldset>;
        })}
        <div className="tt-review"><span>总分 {draft.total_score} · 保存修改会使已有审核失效</span><div className="tt-actions">
          {editable && <button disabled={busy || !dirty} onClick={() => void operate(() => teachingTasks.save(selected, draft))}>保存修改</button>}
          {selected.status === 'awaiting_review' && <button disabled={busy || dirty} onClick={() => void operate(() => teachingTasks.command(selected, 'approve'))}>审核通过</button>}
          {selected.status === 'approved' && <button className="tt-primary" disabled={busy || dirty} onClick={() => void operate(() => teachingTasks.command(selected, 'publish'))}>发布到本班级</button>}
          {selected.published_exam_id && <Link to="/exams">已发布，查看试卷</Link>}</div></div>
      </section>}
      {!!selected.checkpoint.traces?.length && <details><summary>执行记录</summary>{selected.checkpoint.traces.map((trace, i) => <p key={i}>{trace.node} · {trace.latency_ms} ms {trace.model && `· ${trace.model}`} {trace.usage?.total_tokens != null && `· ${trace.usage.total_tokens} tokens`}</p>)}<small>费用仅在供应商返回计费数据时记录，当前未估算。</small></details>}
    </>}</main></div>
  </div>;
}
