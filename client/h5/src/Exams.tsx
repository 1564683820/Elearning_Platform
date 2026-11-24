import { PaperDraftEditor } from '../../src/shared/exams/PaperDraftEditor';
import { useEffect, useRef, useState, type ComponentProps, type FormEvent, type ReactNode } from 'react';
import { Link, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { teacherApi, type AnswerSheetTemplateItem, type ChoiceQuestionItem, type ExamDetail, type ExamListItem, type ExamSource, type PaperDraft, type PaperGradingState } from '../../src/api/teacher';
import { ExamSourcePreview, SourceCard } from '../../src/shared/exams/ExamSources';
import { Icon, Select, Sheet, errorText } from './ui';
import { FixedCardCapture } from '../../src/shared/exams/FixedCardCapture';
import { FixedCardGuidePage } from '../../src/shared/exams/FixedCardGuide';
import '../../src/shared/exams/paperGrading.css';
import { AnswerCardPhoto } from '../../src/shared/exams/AnswerCardPhoto';
import { FixedCardReview, PendingReviews } from '../../src/shared/exams/FixedCardReview';
import { GradingRecords, RecordDetail } from '../../src/shared/exams/Records';
import { PaperRules } from '../../src/shared/exams/PaperRules';
import { CopyPaperDraftDialog, PaperGradingDialog, PaperProgress, paperStateLabels, usePaperGrading } from '../../src/shared/exams/PaperGradingStatus';

const states: Record<string, string> = { draft: '草稿', ready: '可批改', published: '已发布', grading: '批改中', done: '已完成', archived: '已归档' };

function visibleState(item: ExamListItem) {
  return item.paper_state === 'completed' ? 'done' : item.paper_state ?? item.status;
}

function Title({ children, back, outside }: { children: ReactNode; back?: string; outside?: ReactNode }) {
  return <header className="heading">
    {back && <Link className="round" to={back} aria-label="返回"><Icon name="left" /></Link>}
    <h1>{children}</h1>{outside}
  </header>;
}

const paperFilterOptions = [{ value: '', label: '全部状态' },
  ...Object.entries(paperStateLabels).map(([value, label]) => ({ value, label }))];

function updateLabel(item: ExamListItem) {
  const timestamp = item.updated_at || item.created_at;
  if (!timestamp) return '';
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return '';
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return '今天更新';
  today.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return '昨天更新';
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
}

function ExamList() {
  const [params, setParams] = useSearchParams();
  const search = params.get('search') || '';
  const selected = params.get('status') || '';
  const status = paperFilterOptions.some(option => option.value === selected) ? selected as PaperGradingState['state'] | '' : '';
  const [result, setResult] = useState<{ items: ExamListItem[]; total: number }>();
  const [page, setPage] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const request = new AbortController();
    setLoading(true);
    setError('');
    const timer = window.setTimeout(async () => {
      try {
        const data = await teacherApi.listExams({
          grading_view: true, search: search.trim() || undefined, paper_status: status || undefined, page,
        }, request.signal);
        if (!request.signal.aborted) setResult(previous => page > 1 && previous ? {
          ...data, items: [...new Map([...previous.items, ...data.items].map(item => [item.id, item])).values()],
        } : data);
      } catch (failure) {
        if (!request.signal.aborted) setError(errorText(failure));
      } finally {
        if (!request.signal.aborted) setLoading(false);
      }
    }, search ? 220 : 0);
    return () => { window.clearTimeout(timer); request.abort(); };
  }, [search, status, page, revision]);

  function changeFilters(query: string, state: string) {
    const next = new URLSearchParams();
    if (query) next.set('search', query);
    if (state) next.set('status', state);
    if (next.toString() === params.toString()) return;
    setPage(1);
    setResult(undefined);
    setLoading(true);
    setParams(next, { replace: true });
  }
  const rows = result?.items ?? [];
  const filtered = Boolean(search.trim() || status);
  return <section className="exam-list-screen">
    <Title outside={<Link className="round" to="/exams/new" aria-label="添加试卷"><Icon name="plus" /></Link>}>试卷</Title>
    <div className="field"><Icon name="search" size={18} /><input aria-label="搜索试卷名称" placeholder="搜索试卷名称"
      maxLength={256} value={search} onChange={event => changeFilters(event.target.value, status)} /></div>
    <div className="filters"><Select label="试卷状态" value={status} onChange={next => changeFilters(search, next)} options={paperFilterOptions} />
      {rows.length > 0 && <Link className="secondary" to="/exams/templates">题型分数模板</Link>}</div>
    {error && <div className="notice failure" role="alert"><p>{error}</p><button className="secondary" onClick={() => setRevision(value => value + 1)}>重试</button></div>}
    {loading && !result && <p className="notice" role="status">正在加载…</p>}
    {rows.length > 0 ? <>
      <div className="card-list">
        {rows.map(item => {
          const state = visibleState(item);
          const blocker = state === 'draft' && item.paper_blocker;
          return <Link className="list-card exam-card" key={item.id} to={`/exams/${item.id}`} state={{ examListSearch: params.toString() }}>
            <strong>{item.title}</strong><Icon name="right" size={18} />
            <small>{[item.class_name || (Number(item.class_id) ? '已关联班级' : '未关联班级'), updateLabel(item)].filter(Boolean).join(' · ')}</small>
            {blocker ? <p>{blocker === '请先保存本卷标准答案' ? '标准答案待填写' : blocker}</p>
              : (state === 'grading' || state === 'done') && item.paper_state && <p>已确认 {item.confirmed_count ?? 0} 份{item.pending_count ? ` · 待复核 ${item.pending_count} 份` : ''}</p>}
            <span className={`badge ${state === 'draft' ? 'draft' : ''}`}>{states[state] || state}</span>
          </Link>;
        })}
      </div>
      {!error && rows.length < (result?.total ?? 0) && <button className="secondary wide exam-list-more" disabled={loading} onClick={() => { setLoading(true); setPage(value => value + 1); }}>加载更多</button>}
    </> : !loading && !error && <div className="exam-list-empty" data-filtered={filtered}>
      <div><Icon name={filtered ? 'searchOff' : 'files'} size={34} /></div>
      <h2>{filtered ? '没有匹配的试卷' : '还没有试卷'}</h2>
      {filtered ? <button className="primary" onClick={() => changeFilters('', '')}>清除条件</button>
        : <Link className="primary" to="/exams/new">添加试卷</Link>}
    </div>}
  </section>;
}

function PaperCardContents({ icon, title, subtitle }: { icon: ComponentProps<typeof Icon>['name']; title: string; subtitle?: string }) {
  return <>
    <span className="review-icon"><Icon name={icon} /></span>
    <span><strong>{title}</strong>{subtitle && <small>{subtitle}</small>}</span>
    <Icon name="right" size={17} />
  </>;
}

function ExamView() {
  const { examId = '' } = useParams();
  return <ExamViewDetail key={examId} examId={examId} />;
}

function ExamViewDetail({ examId }: { examId: string }) {
  const { state: locationState } = useLocation();
  const listBack = typeof locationState?.examListSearch === 'string' && locationState.examListSearch
    ? `/exams?${locationState.examListSearch}` : '/exams';
  const navigate = useNavigate();
  const [exam, setExam] = useState<ExamDetail>();
  const [error, setError] = useState('');
  const [sourceError, setSourceError] = useState('');
  const [sources, setSources] = useState<ExamSource[]>([]);
  const [preview, setPreview] = useState<ExamSource>();
  const [snapshot, setSnapshot] = useState<PaperDraft>();
  const [reload, setReload] = useState(0);
  const [menu, setMenu] = useState(false);
  const menuRoot = useRef<HTMLDivElement>(null);
  const [dialog, setDialog] = useState(false);
  const [copy, setCopy] = useState(false);
  const grading = usePaperGrading(exam?.paper_draft ? examId : undefined);
  const progress = grading.status;
  useEffect(() => {
    let live = true;
    const abort = new AbortController();
    setExam(undefined);
    setError('');
    setSourceError('');
    setSources([]);
    setMenu(false);
    setDialog(false);
    setCopy(false);
    void teacherApi.getExam(examId, abort.signal).then(item => { if (live) setExam(item); })
      .catch(failure => { if (live) setError(errorText(failure)); });
    void teacherApi.listExamSources(examId, abort.signal).then(items => {
      if (!abort.signal.aborted) setSources(items);
    }).catch(failure => { if (!abort.signal.aborted) setSourceError(errorText(failure)); });
    return () => { live = false; abort.abort(); };
  }, [examId, reload]);
  useEffect(() => {
    if (!exam?.paper_draft) return;
    const request = new AbortController();
    void teacherApi.getPaperDraft(examId, request.signal).then(draft => {
      if (!request.signal.aborted) setSnapshot(draft);
    }, () => { /* The shared rules page can load the snapshot independently. */ });
    return () => request.abort();
  }, [exam?.paper_draft, examId]);
  useEffect(() => {
    if (!menu) return;
    function dismiss(event: PointerEvent) {
      if (event.target instanceof Node && !menuRoot.current?.contains(event.target)) setMenu(false);
    }
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [menu]);

  if (exam && progress) {
    const draft = progress.state === 'draft';
    const ready = progress.state === 'ready';
    const completed = progress.state === 'completed';
    const started = !draft && !ready;
    const root = `/exams/${examId}`;
    const count = snapshot?.questions.length ?? exam.question_count ?? exam.questions.length;
    const score = snapshot ? snapshot.questions.reduce((sum, question) => sum + question.score, 0) : exam.total_score;
    const rules = `${count} 题 · 满分 ${score} 分`;
    const answered = snapshot?.questions.filter(question => question.answer).length;
    const blocker = progress.recognition_blocker;
    const edit = (step?: 'template' | 'answers') =>
      navigate(`${root}/edit${step ? `?step=${step}` : ''}`, { state: locationState });
    return <section className="paper-live" data-draft={draft}>
      <Title back={listBack} outside={<div className="paper-live-more" ref={menuRoot} onKeyDown={event => {
        if (event.key === 'Escape') {
          setMenu(false);
          menuRoot.current?.querySelector('button')?.focus();
        }
      }}>
        <button className="round" aria-label="批改操作" aria-expanded={menu} onClick={() => setMenu(value => !value)}><Icon name="more" /></button>
        {menu && <div className="paper-live-menu">
          {(draft || ready) && <button onClick={() => edit()}><Icon name="edit" size={16} />编辑试卷</button>}
          {started && !completed && <button onClick={() => { setMenu(false); setDialog(true); }}><Icon name="files" size={16} />结束批卷</button>}
          {started && <button onClick={() => { setMenu(false); setCopy(true); }}><Icon name="files" size={16} />复制为新卷</button>}
        </div>}
      </div>}>{exam.title}</Title>
      <p className="caption paper-live-class">{[exam.grade, progress.class_name || '无关联班级'].filter(Boolean).join(' · ')}</p>
      <span className={`badge paper-live-badge ${draft ? 'draft' : ''}`}>{paperStateLabels[progress.state]}</span>
      {draft ? <div className="paper-draft-warning" role="status"><Icon name="warning" size={19} /><div>
        <strong>试卷配置尚未完成</strong>
        <p>{blocker === '请先保存本卷标准答案' ? '补齐标准答案后校验固定版式。' : blocker || '继续编辑试卷。'}</p>
      </div></div> : <PaperProgress status={progress} />}
      <div className="card-list paper-live-cards">
        {!draft && <>
          <Link className="list-card review-entry" to={`${root}/records`} state={locationState}>
            <PaperCardContents icon="clipboard" title="批改记录" />
          </Link>
          <Link className="list-card review-entry" to={`${root}/fixed-card`} state={locationState}>
            <PaperCardContents icon="scan" title="固定版式答题卡" subtitle={progress.layout_configured ? '需求方提供' : '版式待配置'} />
          </Link>
        </>}
        {sources.map(source => <button type="button" className="list-card review-entry" key={source.id} onClick={() => setPreview(source)}>
          <PaperCardContents icon={source.kind === 'image' ? 'image' : 'files'} title="试卷原件" subtitle={source.name} />
        </button>)}
        {sourceError && <p className="notice failure" role="alert">{sourceError} <button className="plain" onClick={() => setReload(value => value + 1)}>重试</button></p>}
        {draft ? <>
          <button type="button" className="list-card review-entry" onClick={() => edit('template')}>
            <PaperCardContents icon="template" title="题型分数模板" subtitle={count ? rules : '待选择'} />
          </button>
          <button type="button" className="list-card review-entry" onClick={() => edit('answers')}>
            <PaperCardContents icon="clipboard" title="本卷答案" subtitle={answered == null ? undefined : `已设置 ${answered} / ${count} 题`} />
          </button>
        </> : <Link className="list-card review-entry" to={`${root}/rules`} state={locationState}>
          <PaperCardContents icon="clipboard" title="评分规则与本卷答案"
            subtitle={[rules, snapshot?.template_name].filter(Boolean).join(' · ')} />
        </Link>}
      </div>
      {grading.error && !dialog && <p className="notice failure" role="alert">{grading.error}</p>}
      <div className="actions review-actions paper-live-actions">
        {!draft && <Link className="secondary" to="/" state={{ paperQuestion: `「${exam.title}」哪些题失分较多？` }}>询问本卷</Link>}
        {draft ? <button className="primary" onClick={() => edit()}>继续编辑</button>
          : completed ? <button className="primary" onClick={() => setDialog(true)}>继续批卷</button>
          : progress.recognition_available ? <Link className="primary" to={`/exams/${examId}/scan`}>{ready ? '开始批卷' : '继续批卷'}</Link>
          : <button className="primary" disabled>继续批卷</button>}
      </div>
      {!draft && !completed && blocker && <p className="notice warning">{blocker}</p>}
      {dialog && <PaperGradingDialog examId={examId} {...grading} close={() => setDialog(false)} />}
      <CopyPaperDraftDialog key={examId} examId={examId} open={copy} close={() => setCopy(false)} />
      {preview && <ExamSourcePreview key={preview.id} examId={examId} source={preview} close={() => setPreview(undefined)} />}
    </section>;
  }
  return <>
    <Title back={listBack}>{exam?.title || '试卷详情'}</Title>
    {error ? <p className="notice failure" role="alert">{error} <button className="plain" onClick={() => setReload(value => value + 1)}>重试</button></p>
      : exam?.paper_draft ? grading.error
        ? <p className="notice failure" role="alert">{grading.error} <button className="plain" onClick={grading.retry}>重试</button></p>
        : <p className="notice" role="status">正在加载…</p>
      : exam ? <>
      <span className="badge">{states[exam.status] || exam.status}</span>
      {exam.description && <p className="caption">{exam.description}</p>}
      <div className="card-list">
        {sources.map(source => <SourceCard source={source} key={source.id} onClick={() => setPreview(source)} />)}
        {sourceError && <p className="notice failure" role="alert">{sourceError}</p>}
        <div className="list-card"><strong>题型分数模板</strong><small>{exam.question_count ?? exam.questions.length} 题 · 满分 {exam.total_score} 分</small></div>
        <Link className="list-card exam-card" to={`/exams/${examId}/records`}><strong>批改记录</strong><Icon name="right" size={18} /><small>{exam.submission_count} 份提交</small></Link>
        {(exam.paper_draft_editable ?? (exam.status === 'draft' && !exam.answer_sheet)) &&
          <Link className="primary wide" to={`/exams/${examId}/edit`} state={locationState}>继续编辑</Link>}
      </div>
      {preview && <ExamSourcePreview key={preview.id} examId={examId} source={preview} close={() => setPreview(undefined)} />}
    </> : <p className="notice">正在加载…</p>}
  </>;
}

function Templates() {
  const [templates, setTemplates] = useState<AnswerSheetTemplateItem[]>();
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    void teacherApi.listAnswerSheetTemplates({ paperOnly: true }).then(items => { if (live) setTemplates(items); }).catch(failure => { if (live) setError(errorText(failure)); });
    return () => { live = false; };
  }, []);
  return <div className="template-screen">
    <Title back="/exams" outside={<Link className="round" to="new" aria-label="新建模板"><Icon name="plus" /></Link>}>题型分数模板</Title>
    {error ? <p className="notice failure">{error}</p> : !templates ? <p className="notice">正在加载…</p> : templates.length ? <div className="card-list templates">
      {templates.map(item => <Link className="list-card template-card" to={item.id} key={item.id}>
        <span className="template-icon"><Icon name="template" /></span>
        <span><strong>{item.name}</strong><small>{item.question_count} 题 · 满分 {item.total_score} 分</small></span>
        <Icon name="right" size={17} />
      </Link>)}
    </div> : <div className="templates-empty">
      <span className="template-icon"><Icon name="template" size={34} /></span>
      <h2>还没有评分模板</h2><Link className="primary" to="new">新建模板</Link>
    </div>}
    {!!templates?.length && <div className="template-footer"><Link className="primary wide" to="new">新建模板</Link></div>}
  </div>;
}

const templateOptions = Array.from({ length: 7 }, (_, index) => ({ value: String(index + 2), label: `${index + 2} 个` }));
const templateScores = Array.from({ length: 100 }, (_, index) => ({ value: String(index + 1), label: `${index + 1} 分` }));

function TemplateEditor({ onCancel, onSaved }: {
  onCancel?: () => void;
  onSaved?: (item: AnswerSheetTemplateItem) => void;
} = {}) {
  const { templateId } = useParams();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [count, setCount] = useState(20);
  const [options, setOptions] = useState(4);
  const [score, setScore] = useState(2);
  const [rows, setRows] = useState<ChoiceQuestionItem[]>([]);
  const [original, setOriginal] = useState<AnswerSheetTemplateItem>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<'archive' | 'batch'>();
  const [archiveError, setArchiveError] = useState('');
  const makeRow = (index: number, optionCount: number, points: number): ChoiceQuestionItem => ({
    question_number: index + 1, option_count: optionCount, score: points, type: 'single',
    options: Array.from({ length: optionCount }, (_, n) => String.fromCharCode(65 + n)),
  });
  useEffect(() => {
    let live = true;
    if (!templateId) {
      setRows(Array.from({ length: 20 }, (_, index) => makeRow(index, 4, 2)));
      return;
    }
    void teacherApi.getAnswerSheetTemplate(templateId).then(item => {
      if (!live) return;
      setOriginal(item);
      setName(item.name);
      setRows(item.choice_questions.map((row, index) => ({
        ...row, question_number: row.question_number ?? index + 1,
        option_count: row.option_count ?? row.options?.length ?? 0,
      })));
      setCount(item.choice_questions.length);
    }).catch(failure => { if (live) setError(errorText(failure)); });
    return () => { live = false; };
  }, [templateId]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy || !rows.length) return;
    setError('');
    setBusy(true);
    try {
      const title = name.trim();
      if (!title) throw new Error('请输入模板名称');
      const data = { name: title, choice_questions: rows, grade: original?.grade, description: original?.description, is_default: original?.is_default };
      if (templateId) {
        if (!original?.revision) throw new Error('暂无法取得模板版本，请重新打开');
        await teacherApi.updateAnswerSheetTemplate(templateId, { ...data, revision: original.revision });
      } else {
        const created = await teacherApi.createAnswerSheetTemplate({ ...data, create_only: true });
        if (onSaved) {
          onSaved(created);
          return;
        }
      }
      navigate('/exams/templates');
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  function applyBatch() {
    const next = Array.from({ length: count }, (_, index) => makeRow(index, options, score));
    setRows(next);
    setConfirm(undefined);
  }

  async function archive() {
    if (!templateId || busy) return;
    setBusy(true);
    setArchiveError('');
    try {
      await teacherApi.archiveAnswerSheetTemplate(templateId);
      navigate('/exams/templates', { replace: true });
    } catch (failure) {
      setArchiveError(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  const readonly = !!original?.archived_at;
  const compatible = original?.paper_compatible !== false;
  return <div className="template-screen template-edit-screen">
    {onCancel ? <header className="heading"><button type="button" className="round" aria-label="返回" disabled={busy} onClick={onCancel}><Icon name="left" /></button><h1>新建模板</h1></header>
      : <Title back="/exams/templates" outside={original && !readonly && <button className="round template-archive" aria-label="停用模板" type="button" disabled={busy} onClick={() => { setArchiveError(''); setConfirm('archive'); }}><Icon name="archive" /></button>}>
        {templateId ? '编辑模板' : '新建模板'}
      </Title>}
    {templateId && !original && <p className={error ? 'notice failure' : 'notice'}>{error || '正在加载…'}</p>}
    {readonly && <p className="notice">模板已停用</p>}
    {!compatible && <p className="notice">此模板不适用于纸质单选批改。</p>}
    {compatible && (!templateId || original) && <form className="editor template-editor" onSubmit={save}>
      <fieldset disabled={busy || readonly}>
      <label>模板名称<span className="draft-entry"><Icon name="template" size={17} /><input required value={name} onChange={event => setName(event.target.value)} placeholder="请输入模板名称" maxLength={128} /></span></label>
      <div className="batch"><h2>批量设置</h2><div className="batch-fields">
        <label>题量<input type="number" min={1} max={200} value={count} onChange={event => setCount(event.target.valueAsNumber || 0)} /></label>
        <div className="editor-field">选项数量<Select label="选项数量" value={String(options)} options={templateOptions} onChange={value => setOptions(Number(value))} /></div>
        <div className="editor-field">每题分值<Select label="每题分值" value={String(score)} options={templateScores} onChange={value => setScore(Number(value))} /></div>
      </div><button type="button" className="plain" disabled={!Number.isInteger(count) || count < 1 || count > 200} onClick={() => {
        if (count < rows.length || rows.some(row => row.option_count !== options || row.score !== score)) setConfirm('batch');
        else applyBatch();
      }}>应用到所有题目</button></div>
      <h2>逐题配置</h2>
      <div className="template-table-labels" aria-hidden="true"><span>题号 / 题型</span><span>选项</span><span>分值</span></div>
      {rows.map((row, index) => <div key={index} className="question-row">
        <strong>{String(index + 1).padStart(2, '0')} 单选</strong>
        <Select label={`第 ${index + 1} 题选项数`} value={String(row.option_count)} options={templateOptions} onChange={value => setRows(previous => previous.map((item, i) => i === index ? makeRow(i, Number(value), item.score) : item))} />
        <Select label={`第 ${index + 1} 题分值`} value={String(row.score)} options={templateScores} onChange={value => setRows(previous => previous.map((item, i) => i === index ? { ...item, score: Number(value) } : item))} />
      </div>)}
      <p className="caption">共 {rows.length} 道单选题 · 满分 {rows.reduce((sum, row) => sum + row.score, 0)} 分</p>
      </fieldset>
      {error && <p className="notice failure">{error}</p>}
      {!readonly && <div className="template-footer"><button className="primary wide" disabled={busy || !rows.length}>{busy ? '保存中…' : templateId ? '保存新版本' : '保存模板'}</button></div>}
    </form>}
    {confirm === 'batch' && <Sheet title="应用批量设置？" variant="draft" close={() => setConfirm(undefined)}>
      <p>将按新题量统一设置每题的选项和分值。</p>
      <div className="actions"><button className="secondary" onClick={() => setConfirm(undefined)}>取消</button><button className="primary" onClick={applyBatch}>确认应用</button></div>
    </Sheet>}
    {confirm === 'archive' && <Sheet title="停用这个模板？" variant="archive" close={() => { if (!busy) setConfirm(undefined); }}>
      <p>已有试卷继续使用原版本。</p>
      {archiveError && <p className="notice failure" role="alert">{archiveError}</p>}
      <div className="actions"><button className="secondary" disabled={busy} onClick={() => setConfirm(undefined)}>继续使用</button><button className="danger" disabled={busy} onClick={() => void archive()}>{busy ? '停用中…' : '停用模板'}</button></div>
    </Sheet>}
  </div>;
}

function MobilePaperDraftEditor() {
  const { examId } = useParams();
  return <PaperDraftEditor key={examId ?? 'new'} renderTemplateCreator={props => <TemplateEditor {...props} />} />;
}

export function Exams() {
  const { pathname } = useLocation();
  return <main className={`page exams exam-grading ${pathname === '/exams' ? '' : 'subpage'}`}><Routes>
    <Route index element={<ExamList />} />
    <Route path="new" element={<MobilePaperDraftEditor />} />
    <Route path="templates" element={<Templates />} />
    <Route path="templates/new" element={<TemplateEditor />} />
    <Route path="templates/:templateId" element={<TemplateEditor />} />
    <Route path=":examId" element={<ExamView />} />
    <Route path=":examId/edit" element={<MobilePaperDraftEditor />} />
    <Route path=":examId/fixed-card" element={<FixedCardGuidePage />} />
    <Route path=":examId/records" element={<GradingRecords />} />
    <Route path=":examId/rules" element={<PaperRules />} />
    <Route path=":examId/records/:recordId" element={<RecordDetail />} />
    <Route path=":examId/records/:recordId/history" element={<RecordDetail view="history" />} />
    <Route path=":examId/records/:recordId/photo" element={<AnswerCardPhoto />} />
    <Route path=":examId/scan" element={<FixedCardCapture />} />
    <Route path=":examId/scan/reviews" element={<PendingReviews />} />
    <Route path=":examId/scan/reviews/:scanId" element={<FixedCardReview />} />
    <Route path=":examId/scan/reviews/:scanId/photo" element={<AnswerCardPhoto />} />
  </Routes></main>;
}
