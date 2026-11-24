import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { teacherApi, type GradingRecordDetail, type GradingRecordStatus } from '../../api/teacher';
import { Icon, Select, errorText } from '../mobileControls';
import { RecordActionDialog } from './RecordActionDialog';

const statusLabels: Record<GradingRecordStatus, string> = { confirmed: '已确认', review: '待复核', failed: '识别失败', historical: '历史操作' };
const sourceLabels = { manual: '手工录入', scan: '手机扫描', online: '在线提交', legacy_scan: '原扫码入口' };
const actionLabels: Record<string, string> = { auto_grade: '自动批改', teacher_review: '确认复核', teacher_adjust: '修正成绩', paper_confirm: '确认原成绩', paper_regrade: '确认重批', paper_withdraw: '撤回成绩' };
const statusOptions = [{ value: '', label: '全部状态' }, ...Object.entries(statusLabels).map(([value, label]) => ({ value, label }))];

function headingTime(time: string | null) {
  if (!time) return '';
  const date = new Date(time);
  return date.toLocaleString('zh-CN', date.toDateString() === new Date().toDateString()
    ? { hour: '2-digit', minute: '2-digit' }
    : { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function Header({ back, children, actions }: { back: string; children: ReactNode; actions?: ReactNode }) {
  return <header className="heading records-heading"><Link className="round" to={back} aria-label="返回"><Icon name="left" /></Link><h1>{children}</h1>{actions}</header>;
}

export function GradingRecords({ desktop = false }: { desktop?: boolean } = {}) {
  const { examId = '' } = useParams();
  return <GradingRecordsList key={examId} examId={examId} desktop={desktop} />;
}

function GradingRecordsList({ examId, desktop }: { examId: string; desktop: boolean }) {
  const [params, setParams] = useSearchParams();
  const search = params.get('search') || '';
  const selected = params.get('status') || '';
  const status = Object.prototype.hasOwnProperty.call(statusLabels, selected) ? selected as GradingRecordStatus : undefined;
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<Awaited<ReturnType<typeof teacherApi.getGradingRecords>>>();
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(async () => {
      setError('');
      try {
        const response = await teacherApi.getGradingRecords(examId, { search: search.trim(), status, page }, abort.signal);
        if (!abort.signal.aborted) setResult(previous => page > 1 && previous ? {
          ...response,
          items: [...new Map([...previous.items, ...response.items].map(item => [`${item.record_kind}:${item.id}`, item])).values()],
        } : response);
      } catch (failure) {
        if (!abort.signal.aborted) setError(errorText(failure));
      } finally {
        if (!abort.signal.aborted) setLoading(false);
      }
    }, search ? 200 : 0);
    return () => { window.clearTimeout(timer); abort.abort(); };
  }, [examId, search, status, page, reload]);

  const setFilter = (key: string, value: string) => {
    if ((params.get(key) || '') === value) return;
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setPage(1);
    setResult(undefined);
    setParams(next, { replace: true });
  };
  const suffix = params.size ? `?${params}` : '';
  const root = `/exams/${examId}`;
  return <section className="records records-list">
    <Header back={desktop ? `/exams/paper-drafts/${examId}` : root}>批改记录</Header>
    {result && <p className="caption records-caption">{result.title}</p>}
    <div className="field"><Icon name="search" size={18} /><input aria-label="搜索考号或学生姓名" placeholder="搜索考号或学生姓名" maxLength={64} value={search} onChange={event => setFilter('search', event.target.value)} /></div>
    <div className="records-filter"><Select label="批改记录状态" value={status || ''} options={statusOptions} onChange={value => setFilter('status', value)} /></div>
    {error ? <div className="notice failure" role="alert">{error}<button className="secondary" onClick={() => setReload(reload + 1)}>重试</button></div> : !result ? <p className="notice" aria-live="polite">正在加载…</p> : result.items.length ? <>
      <p className="records-summary">{result.confirmed} 份已确认 · {result.pending} 份待复核</p>
      <div className="card-list">{result.items.map(record => <Link className="list-card grading-record"
        key={`${record.record_kind}:${record.id}`}
        to={record.record_kind === 'scan' ? `${root}/scan/reviews/${record.id}` : `${root}/records/${record.id}${suffix}`}
        state={record.record_kind === 'scan' ? { fromRecords: true, recordsSearch: suffix } : undefined}>
        <strong>{[record.exam_number, record.student_name || (record.status === 'review' && record.exam_number ? '待匹配' : '')].filter(Boolean).join('　') || '考号待核对'}</strong>
        <b>{record.score == null ? '—' : `${record.score} / ${record.max_score ?? '—'}`}</b>
        <small>{sourceLabels[record.source]}{record.updated_at ? ` · ${headingTime(record.updated_at)}` : ''}</small>
        <span data-status={record.status}>{record.record_kind === 'scan' && record.status === 'historical' ? '已放弃' : statusLabels[record.status]}</span>
        <Icon name="right" size={16} />
      </Link>)}</div>
      {result.items.length < result.total && <button className="secondary wide records-more" disabled={loading} onClick={() => { setLoading(true); setPage(page + 1); }}>加载更多</button>}
    </> : <div className="records-empty">
      <div><Icon name="clipboard" size={34} /></div><h2>{search || status ? '未找到批改记录' : '还没有批改记录'}</h2>
      {!desktop && !search && !status && <Link className="primary" to={`${root}/scan`}>开始批卷</Link>}
    </div>}
  </section>;
}

export function RecordDetail({ view = 'score', desktop }: { view?: 'score' | 'history'; desktop?: boolean }) {
  const { examId = '', recordId = '' } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [record, setRecord] = useState<GradingRecordDetail>();
  const [withdraw, setWithdraw] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState('');
  const [regradeError, setRegradeError] = useState('');
  const [regradeBusy, setRegradeBusy] = useState(false);
  const regradeRequest = useRef<{ examId: string; recordId: string; version: number; id: string }>();
  useEffect(() => {
    const abort = new AbortController();
    setError('');
    setRegradeError('');
    setRegradeBusy(false);
    setRecord(undefined);
    async function load() {
      try {
        const result = await teacherApi.getGradingRecord(examId, recordId, abort.signal);
        if (abort.signal.aborted) return;
        setRecord(result);
      } catch (failure) {
        if (!abort.signal.aborted) setError(errorText(failure));
      }
    }
    void load();
    return () => {
      abort.abort();
      regradeRequest.current = undefined;
    };
  }, [examId, recordId, refresh]);
  const suffix = params.size ? `?${params}` : '';
  const root = `/exams/${examId}/records`;
  const base = `${root}/${recordId}`;
  const back = `${view === 'score' ? root : base}${suffix}`;
  const withdrawableVersion = record?.withdrawable_grade_version;
  const canRegrade = view === 'score' && withdrawableVersion != null && record?.has_photo;
  const title = { score: '成绩详情', history: '历史修正' }[view];
  async function regrade() {
    if (!canRegrade || withdrawableVersion == null || regradeBusy) return;
    const previous = regradeRequest.current;
    const request = previous?.examId === examId && previous.recordId === recordId && previous.version === withdrawableVersion
      ? previous : { examId, recordId, version: withdrawableVersion, id: crypto.randomUUID() };
    regradeRequest.current = request;
    setRegradeBusy(true);
    setRegradeError('');
    try {
      const data = await teacherApi.preparePaperRegrade(examId, recordId, request.version, request.id);
      if (regradeRequest.current === request) {
        navigate(`/exams/${examId}/scan/reviews/${data.scan_id}`, { state: { recordsSearch: suffix } });
      }
    } catch (failure) {
      if (regradeRequest.current === request) setRegradeError(errorText(failure));
    } finally {
      if (regradeRequest.current === request) setRegradeBusy(false);
    }
  }
  const actions = view === 'score' && withdrawableVersion != null ? <details className="record-menu">
    <summary className="round" aria-label="更多操作"><Icon name="more" /></summary>
    <button className="secondary" disabled={regradeBusy} onClick={event => {
      event.currentTarget.closest('details')?.removeAttribute('open');
      setWithdraw(true);
    }}>撤回成绩</button>
  </details> : undefined;
  return <section className={`records record-detail ${view === 'score' ? 'record-detail-score' : ''}`}>
    <Header back={back} actions={actions}>{title}</Header>
    {error ? <p className="notice failure" role="alert">{error}</p> : !record ? <p className="notice" aria-live="polite">正在加载…</p> : <>
      <p className="caption records-caption">{view === 'history' ? [record.exam_number, record.student_name].filter(Boolean).join('　') : record.title}{view === 'score' && record.updated_at ? ` · ${record.status === 'confirmed' ? '最近确认 ' : ''}${headingTime(record.updated_at)}` : ''}</p>
      {view === 'score' && <>
        <div className="record-score"><strong>{record.score ?? '—'} / {record.max_score ?? '—'}</strong><small>{[record.exam_number, record.student_name].filter(Boolean).join(' · ') || statusLabels[record.status]}</small></div>
        {record.has_photo && <Link className="list-card record-action" to={`${base}/photo${suffix}`}><span><Icon name="image" /></span><div><strong>答题卡照片</strong><small>{sourceLabels[record.source]}{canRegrade ? ' · 固定版式' : ''}</small></div><Icon name="right" size={17} /></Link>}
        <h2>逐题明细</h2>
        {record.questions.length ? <div className="record-questions">{record.questions.map(question => <div className="list-card" data-wrong={Boolean(question.marked) && question.score != null && question.score < question.max_score} key={question.number}>
          <strong>{String(question.number).padStart(2, '0')}</strong><span>{question.raw !== null ? `原始 ${question.raw || '—'} · ` : ''}确认 {question.invalid_mark ? `${[...question.marked].join(' / ')}（无效填涂）` : question.marked || '—'} · 标准 {question.answer || '—'}</span><b>{question.score ?? '—'} / {question.max_score}</b>
        </div>)}</div> : <p className="notice">暂无逐题明细</p>}
        <Link className="list-card record-action record-history-link" aria-label="历史修正" to={`${base}/history${suffix}`}><span><Icon name="refresh" /></span><div><small>{record.history.length ? [headingTime(record.history[0].created_at), actionLabels[record.history[0].action]].filter(Boolean).join(' ') : '暂无历史修正'}</small></div><Icon name="right" size={17} /></Link>
      </>}
      {view === 'history' && <><p className="caption">{record.status === 'historical' ? '历史成绩' : '当前成绩'} {record.score ?? '—'} / {record.max_score ?? '—'}</p>
        {record.history.length ? <div className="card-list record-history">{record.history.map(log => <div className="list-card record-action" key={log.id}><span><Icon name="check" /></span><div>
          <strong>{[headingTime(log.created_at), actionLabels[log.action] || log.action].filter(Boolean).join(' · ')}</strong>
          {log.reason && <small>{log.reason}</small>}
          {log.new_score != null && <small>{log.old_score != null ? `${log.old_score} / ${record.max_score ?? '—'} → ` : ''}{log.new_score} / {record.max_score ?? '—'}</small>}
        </div></div>)}</div> : <p className="notice">暂无历史修正</p>}
      </>}
      {regradeError && <p className="notice failure" role="alert">{regradeError} <button className="plain" onClick={() => setRefresh(value => value + 1)}>刷新成绩</button></p>}
      {canRegrade ? <button className="secondary wide record-back" disabled={regradeBusy} onClick={() => void regrade()}>{regradeBusy ? '正在打开…' : '重批这份答题卡'}</button>
        : <Link className="secondary wide record-back" to={back}>{view === 'score' ? '返回批改记录' : '返回成绩详情'}</Link>}
    </>}
    {withdraw && withdrawableVersion != null && <RecordActionDialog action="撤回成绩" desktop={desktop} close={() => setWithdraw(false)}
      save={async reason => {
        await teacherApi.withdrawPaperGrade(examId, recordId, withdrawableVersion, reason);
        setWithdraw(false);
        setRefresh(value => value + 1);
      }} />}
  </section>;
}
