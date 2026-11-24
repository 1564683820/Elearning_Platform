import { useEffect, useState, type FormEvent } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { isAxiosError } from 'axios';
import {
  teacherApi, type FixedPaperReview, type FixedPaperReviewQuestion, type FixedPaperReviewReceipt,
  type PendingFixedPaperReviews, type StudentInfoItem,
} from '../../api/teacher';
import { Icon, Select, Sheet, errorText } from '../mobileControls';
import { RecordActionDialog } from './RecordActionDialog';

export function PendingReviews({ desktop = false }: { desktop?: boolean } = {}) {
  const { examId = '' } = useParams();
  const { state, search } = useLocation();
  const filter = new URLSearchParams(search).get('status');
  const history = filter === 'discarded' || filter === 'failed' ? filter : undefined;
  const queueTitle = filter === 'failed' ? '识别失败' : history ? '已放弃答题卡' : '待复核答题卡';
  const [reviews, setReviews] = useState<PendingFixedPaperReviews>();
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const root = `/exams/${examId}`;
  const examPath = `/exams/paper-drafts/${examId}`;
  const recordsSearch = typeof state?.recordsSearch === 'string' && state.recordsSearch.startsWith('?') ? state.recordsSearch : '';
  const back = history ? `${root}/records?status=historical` : state?.fromRecords ? `${root}/records${recordsSearch}` : desktop && !state?.fromCapture ? examPath : state?.fromExam ? root : `${root}/scan`;

  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError('');
    void teacherApi.listFixedPaperReviews(examId, page, abort.signal, history).then(data => {
      if (!abort.signal.aborted) setReviews(previous => page > 1 && previous
        ? { total: data.total, items: [...new Map([...previous.items, ...data.items].map(item => [item.id, item])).values()] }
        : data);
    }).catch(failure => {
      if (!abort.signal.aborted) setError(errorText(failure));
    }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [examId, history, page, retry]);

  return <section className="records">
    <header className="heading records-heading">
      <Link className="round" to={back} aria-label="返回"><Icon name="left" /></Link>
      <h1>{queueTitle}</h1>
    </header>
    {error && <p className="notice failure" role="alert">{error} <button className="secondary" onClick={() => setRetry(value => value + 1)}>重试</button></p>}
    {loading && !reviews && <p className="notice" role="status">正在加载…</p>}
    {reviews && (reviews.items.length ? <>
      <div className="card-list">{reviews.items.map(item => <Link key={item.id} className="list-card review-entry" state={state} to={item.id}>
        <Icon name="files" />
        <span><strong>{item.exam_number ? `考号 ${item.exam_number}` : '考号待核对'}</strong><small>{history ? item.reason : `已识别 ${item.recognized_count} 题`}</small></span>
        <Icon name="right" size={17} />
      </Link>)}</div>
      {!error && reviews.items.length < reviews.total && <button className="secondary wide records-more" disabled={loading} onClick={() => setPage(value => value + 1)}>加载更多</button>}
    </> : <div className="records-empty">
      <div><Icon name="files" size={30} /></div><h2>{filter === 'failed' ? '没有识别失败记录' : history ? '没有已放弃的答题卡' : '没有待复核答题卡'}</h2>
      {!history && <Link className="primary" to={desktop ? examPath : `${root}/scan`}>{desktop ? '返回试卷' : '开始批卷'}</Link>}
    </div>)}
  </section>;
}

function formatPaperMark(mark: string) {
  return /^[A-H]{2,8}$/.test(mark) ? [...mark].join(' / ') : mark || '—';
}

type ReviewSheet = 'number' | 'replace' | 'discard' | 'conflict' | FixedPaperReviewQuestion;

export function FixedCardReview({ desktop = false }: { desktop?: boolean } = {}) {
  const { examId = '', scanId = '' } = useParams();
  return <ReviewDetail key={`${examId}/${scanId}`} examId={examId} scanId={scanId} desktop={desktop} />;
}

function ReviewDetail({ examId, scanId, desktop }: { examId: string; scanId: string; desktop: boolean }) {
  const { state } = useLocation();
  const [review, setReview] = useState<FixedPaperReview>();
  const [receipt, setReceipt] = useState<FixedPaperReviewReceipt>();
  const [saved, setSaved] = useState(false);
  const [sheet, setSheet] = useState<ReviewSheet>();
  const [input, setInput] = useState('');
  const [multi, setMulti] = useState(false);
  const [numberConfirmed, setNumberConfirmed] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const root = `/exams/${examId}`;
  const pending = `${root}/scan/reviews`;
  const portalClassName = desktop ? 'web-paper-draft web-paper-grading exam-grading paper-review-portal' : undefined;

  useEffect(() => {
    const abort = new AbortController();
    setReview(undefined);
    setReceipt(undefined);
    setSaved(false);
    setNumberConfirmed('');
    setSheet(undefined);
    setError('');
    void teacherApi.getFixedPaperReview(examId, scanId, abort.signal).then(data => {
      if (!abort.signal.aborted) {
        setReview(data);
        setReceipt(data.receipt ?? undefined);
      }
    }).catch(failure => { if (!abort.signal.aborted) setError(errorText(failure)); });
    return () => abort.abort();
  }, [examId, scanId, retry]);

  const unresolved = review?.questions.filter(question => question.needs_review).length ?? 0;
  const matched = !!review?.student_name;
  const numberLength = review?.exam_number_length;
  const numberNeedsReview = Boolean(review?.identity_conflict) || !review?.exam_number ||
    Boolean(numberLength && review.exam_number.length !== numberLength) || (review.class_required && !matched);
  const needsReview = !!unresolved || numberNeedsReview;
  const numberLabel = review?.exam_number ? `考号 ${review.exam_number}` : '考号待核对';
  const displayIdentity = [numberLabel, review?.student_name].filter(Boolean).join(' · ');
  const old = review?.previous_grade;
  const regradeId = review?.regrade_submission_id;

  function openSheet(next: ReviewSheet) {
    setError('');
    if (next === 'number') setInput(review?.exam_number ?? '');
    else if (typeof next === 'object') {
      setMulti(!!next.invalid_mark);
      setInput(next.invalid_mark || next.options.includes(next.marked) ? next.marked : next.needs_review || next.marked ? '?' : '');
    }
    setSheet(next);
  }

  function chooseOption(option: string) {
    setInput(previous => {
      if (!multi) return option;
      return previous.includes(option) ? previous.replace(option, '') : previous + option;
    });
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!review || busy || !sheet || typeof sheet === 'string' && sheet !== 'number') return;
    if (typeof sheet === 'object' && (multi ? input.length < 2 : input === '?')) return;
    setBusy(true);
    setError('');
    try {
      const updated = await teacherApi.updateFixedPaperReview(examId, scanId, {
        revision: review.revision,
        exam_number: sheet === 'number' ? input.trim() : review.exam_number,
        answers: typeof sheet === 'object' && !multi ? { [sheet.number]: input } : undefined,
        invalid_answers: typeof sheet === 'object' && multi ? { [sheet.number]: [...input] } : undefined,
      });
      setReview(updated);
      if (sheet === 'number') setNumberConfirmed(updated.exam_number);
      setSheet(undefined);
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!review || busy) return;
    setBusy(true);
    setError('');
    try {
      setReceipt(await teacherApi.confirmFixedPaperReview(examId, scanId, review.revision, review.previous_grade));
      setSheet(undefined);
    } catch (failure) {
      if (isAxiosError<{ error_code?: string }>(failure) && failure.response?.status === 409
        && failure.response.data?.error_code === 'paper_review_conflict') {
        setSheet('conflict');
      } else setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  function requestConfirm() {
    if (!review || needsReview || busy) return;
    if (!regradeId && !review.class_required && numberConfirmed !== review.exam_number) openSheet('number');
    else if (review.previous_grade) openSheet('replace');
    else void confirm();
  }

  function closeSheet() {
    if (busy) return;
    setSheet(undefined);
    setError('');
  }

  function reload() { setRetry(value => value + 1); }

  const discarded = review?.status === 'discarded';
  const withdrawn = review?.status === 'withdrawn';
  const failed = review?.status === 'failed';
  const recordsSearch = typeof state?.recordsSearch === 'string' && state.recordsSearch.startsWith('?') ? state.recordsSearch : '';
  const back = regradeId ? `${root}/records/${regradeId}${recordsSearch}`
    : state?.fromRecords ? `${root}/records${recordsSearch}`
    : failed ? `${pending}?status=failed` : discarded ? `${pending}?status=discarded` : withdrawn ? `${root}/records?status=historical` : pending;
  const title = failed ? '识别失败' : discarded ? '答题卡已放弃' : withdrawn ? '成绩已撤回' : review?.status === 'replaced' ? '历史成绩' : receipt ? '成绩已确认' : saved ? '已保存待复核' : needsReview ? '待复核答题卡' : '识别结果';
  return <section className="fixed-review">
    <header className="heading">
      <Link className="round" to={back} state={state} aria-label="返回"><Icon name="left" size={21} /></Link>
      <h1>{title}</h1>
    </header>
    {review && <p className="review-subtitle">{[review.exam_title, review.class_required ? review.class_name : '无关联班级'].filter(Boolean).join(' · ')}</p>}
    {!review && !error && <p className="notice" role="status">正在加载…</p>}
    {error && !sheet && <p className="notice failure" role="alert">{error} <button className="plain" onClick={reload}>重新加载</button></p>}
    {review && (discarded || withdrawn || failed ? <>
      <div className="list-card review-inactive">
        <strong>{displayIdentity}</strong>
        {review.updated_at && <time dateTime={review.updated_at}>{new Date(review.updated_at).toLocaleString('zh-CN')}</time>}
        <p>{review.reason}</p>
      </div>
      {review.has_photo && <Link className="list-card review-entry review-photo-link" to={`${pending}/${scanId}/photo`} state={state}>
        <span className="review-icon"><Icon name="image" /></span><strong>答题卡照片</strong><Icon name="right" size={17} />
      </Link>}
      {failed && <div className="actions review-actions"><Link className="primary" to={`${root}/scan`}>重新拍摄</Link></div>}
    </> : receipt || saved ? <>
      <div className={`review-feedback ${receipt ? 'review-dark' : ''}`}>
        <span><Icon size={receipt ? 40 : 32} name={receipt ? 'check' : 'files'} /></span>
        <strong>{receipt ? `${receipt.score} / ${receipt.max_score}` : numberLabel}</strong>
        <small>{receipt ? displayIdentity : [unresolved ? `${unresolved} 题需核对` : '', numberNeedsReview ? '考号待确认' : ''].filter(Boolean).join(' · ') || '待确认成绩'}</small>
      </div>
      <div className="actions review-actions">
        <Link className="secondary" to={receipt ? `${root}/records` : pending} state={state}>{receipt ? '查看批改记录' : '查看待复核'}</Link>
        {desktop
          ? <Link className="primary" to={receipt ? pending : `/exams/paper-drafts/${examId}`} state={state}>{receipt ? '核对下一份' : '返回试卷'}</Link>
          : <Link className="primary" to={`${root}/scan`}>扫下一份</Link>}
      </div>
    </> : <>
      <div className={`review-score ${needsReview ? '' : 'review-dark'}`}>
        <span>预计得分{needsReview && ' · 待复核'}</span>
        <div><strong>{review.score}</strong><small>/ {review.max_score} 分</small>
          <b>{unresolved ? `${unresolved} 题待核对` : `${review.questions.filter(question => question.marked === question.answer).length} 题正确`}</b>
        </div>
      </div>
      {regradeId ? <div className="list-card review-entry">
        <span className="review-icon"><Icon name="user" /></span><strong>{displayIdentity}</strong>
      </div> : <button className="list-card review-entry review-identity" disabled={busy} onClick={() => openSheet('number')}>
        <span className="review-icon"><Icon name="user" /></span>
        <span><strong>{displayIdentity}{review.class_required && !matched && ' · 未匹配'}</strong><small>{matched ? '已匹配' : '核对考号'}</small></span>
        <Icon name="right" size={17} />
      </button>}
      {review.identity_conflict && <p className="notice warning" role="status">{review.identity_conflict}</p>}
      {review.has_photo && <Link className="list-card review-entry review-photo-link" to={`${pending}/${scanId}/photo`} state={state}>
        <span className="review-icon"><Icon name="image" /></span>
        <strong>答题卡照片</strong><Icon name="right" size={17} />
      </Link>}
      <div className="review-questions">
        <h2>逐题核对</h2>
        <div className="review-columns" aria-hidden="true"><span>题号</span><span>填涂</span><span>标准</span><span>结果</span></div>
        {review.questions.map(question => {
          const multi = question.options.filter(option => question.marked.includes(option)).length > 1;
          const wrong = !!question.marked && question.marked !== question.answer;
          const status = question.needs_review ? multi ? '多涂' : '低置信' : question.invalid_mark ? '无效填涂' : !question.marked ? '空白' : wrong ? '错误' : '正确';
          return <button className="review-columns review-row" key={question.number} disabled={busy}
            data-warning={question.needs_review || wrong} aria-label={`核对第 ${question.number} 题，${status}`} onClick={() => openSheet(question)}>
            <span>{String(question.number).padStart(2, '0')}</span><span>{formatPaperMark(question.marked)}</span>
            <span>{question.answer}</span><strong>{status}</strong>
          </button>;
        })}
      </div>
      <button className="plain review-discard" type="button" disabled={busy} onClick={() => openSheet('discard')}>放弃待复核</button>
      <div className="actions review-actions">
        <button className="secondary" disabled={busy} onClick={() => { setError(''); setSaved(true); }}>保存待复核</button>
        <button className="primary" disabled={busy || needsReview} onClick={requestConfirm}>{busy && !sheet ? '确认中…' : '确认成绩'}</button>
      </div>
    </>)}
    {review && sheet === 'number' && <Sheet title={review.class_required ? '核对考号' : '确认答题卡考号'} icon={review.class_required ? 'user' : 'hash'} variant="paper-review" portalClassName={portalClassName} close={closeSheet}>
      <form onSubmit={saveEdit}>
        {!review.class_required && <p>同一考号只保留一份有效成绩。</p>}
        {review.exam_number_overflow && <p role="status">最后一格右侧有笔迹，请对照照片核对格内考号。</p>}
        {review.exam_number_cells && (review.exam_number_overflow || review.exam_number_cells.some(cell => cell.state !== 'read')) && <p aria-label="逐格识别结果">
          {review.exam_number_cells.map(cell => (
            <span key={cell.position} title={`第 ${cell.position} 位`}>
              {cell.state === 'read' ? cell.digit : cell.digit ? `${cell.digit}?` : '□'}{' '}
            </span>
          ))}
        </p>}
        <label className="field"><Icon name="hash" size={17} /><input aria-label={numberLength ? `考号，共 ${numberLength} 位` : '考号'}
          value={input} maxLength={numberLength ?? 64} inputMode={numberLength ? 'numeric' : undefined}
          pattern={numberLength ? `[0-9]{1,${numberLength}}` : undefined} autoCapitalize={numberLength ? 'off' : 'characters'}
          autoComplete="off" disabled={busy} onChange={event => setInput(event.target.value)} /></label>
        {review.class_id && <ReviewRoster classId={review.class_id} value={input} onChange={setInput} />}
        {error && <p className="notice failure" role="alert">{error}</p>}
        <div className="actions"><button type="button" className="secondary" disabled={busy} onClick={closeSheet}>取消</button>
          <button className="primary" disabled={busy || !input.trim()}>{review.class_required ? '保存考号' : '确认考号'}</button></div>
      </form>
    </Sheet>}
    {review && sheet === 'discard' && <RecordActionDialog action="放弃待复核" desktop={desktop} close={closeSheet} save={async reason => {
      await teacherApi.discardFixedPaperReview(examId, scanId, review.revision, reason);
      reload();
    }} />}
    {review && sheet === 'conflict' && <Sheet title="另一台设备已保存" icon="refresh" variant="paper-conflict" portalClassName={portalClassName} close={closeSheet}>
      <p>核对最新成绩后可重批。</p>
      <div className="actions">
        <button className="secondary" onClick={closeSheet}>返回</button>
        <button className="primary" onClick={reload}>刷新并核对</button>
      </div>
    </Sheet>}
    {review && old && sheet === 'replace' && <Sheet title={old.withdrawn ? '已有撤回记录' : '已有这份成绩'} icon="files" variant="paper-review" portalClassName={portalClassName} close={closeSheet}>
      <p>{review.exam_number} · {old.score ?? '—'} / {old.max_score ?? review.max_score} → {review.score} / {review.max_score}。确认后保留历史记录。</p>
      {error && <p className="notice failure" role="alert">{error} <button className="plain" onClick={reload}>重新加载</button></p>}
      <div className="actions"><button className="secondary" disabled={busy} onClick={closeSheet}>{old.withdrawn ? '取消' : '保留原成绩'}</button>
        <button className="primary" disabled={busy} onClick={() => void confirm()}>{busy ? '确认中…' : '确认重批'}</button></div>
    </Sheet>}
    {sheet && typeof sheet === 'object' && <Sheet title={`核对第 ${sheet.number} 题`} icon="template" variant="paper-review" portalClassName={portalClassName} close={closeSheet}>
      <form className="review-question-form" onSubmit={saveEdit}>
        <p>原始识别 {formatPaperMark(sheet.raw_marked ?? sheet.marked)} · 本题标准答案 {sheet.answer}</p>
        <div className="review-option-grid" role="group" aria-label="实际填涂"
          style={{ gridTemplateColumns: `repeat(${Math.min(4, sheet.options.length)}, minmax(0, 1fr))` }}>
          {sheet.options.map(option => <button key={option} type="button" className="secondary" disabled={busy}
            aria-pressed={multi ? input.includes(option) : input === option}
            onClick={() => chooseOption(option)}>{option}</button>)}
        </div>
        <div className="review-option-modes">
          <button type="button" className="plain" disabled={busy} aria-pressed={!multi && input === ''}
            onClick={() => { setMulti(false); setInput(''); }}>记为空白</button>
          <button type="button" className="plain" disabled={busy} aria-pressed={multi} onClick={() => {
            setMulti(!multi);
            setInput(multi ? '?' : sheet.options.filter(option => (sheet.raw_marked ?? sheet.marked).includes(option)).join(''));
          }}>确认多涂</button>
        </div>
        {multi && input.length < 2 && <p role="status">请选择至少两个实际填涂的选项。</p>}
        {error && <p className="notice failure" role="alert">{error}</p>}
        <div className="actions"><button type="button" className="secondary" disabled={busy} onClick={closeSheet}>取消</button>
          <button className="primary" disabled={busy || (multi ? input.length < 2 : input === '?')}>保存更正</button></div>
      </form>
    </Sheet>}
  </section>;
}

function ReviewRoster({ classId, value, onChange }: { classId: string; value: string; onChange: (value: string) => void }) {
  const [students, setStudents] = useState<StudentInfoItem[]>();
  const [error, setError] = useState('');
  useEffect(() => {
    const abort = new AbortController();
    void teacherApi.listStudentInfo(classId, abort.signal).then(items => {
      if (!abort.signal.aborted) setStudents(items);
    }).catch(failure => { if (!abort.signal.aborted) setError(errorText(failure)); });
    return () => abort.abort();
  }, [classId]);

  const entry = value.trim().toUpperCase();
  const options = students?.map(student => ({
    value: student.exam_number,
    label: `${student.student_name} · ${student.exam_number}`,
  })) ?? [];
  return <div className="review-roster">
    {options.length > 0 ? <Select label="班级花名册" value={entry} options={[{ value: '', label: '从花名册选择' }, ...options]}
      onChange={examNumber => { if (examNumber) onChange(examNumber); }} />
      : <p role={error ? 'alert' : 'status'}>{error || (students ? '班级暂无花名册' : '正在加载花名册…')}</p>}
  </div>;
}
