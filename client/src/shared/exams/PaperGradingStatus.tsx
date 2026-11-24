import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { teacherApi, type PaperGradingState } from '../../api/teacher';
import { Icon, Sheet, errorText } from '../mobileControls';

export const paperStateLabels = {
  draft: '草稿',
  ready: '可批改',
  grading: '批改中',
  completed: '已完成',
};

type Target = 'completed' | 'grading';

export function usePaperGrading(examId?: string) {
  const [status, setStatus] = useState<PaperGradingState>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    setStatus(undefined);
    setError('');
    if (!examId) return;
    const abort = new AbortController();
    void teacherApi.getPaperGradingState(examId, abort.signal).then(value => {
      if (!abort.signal.aborted) setStatus(value);
    }).catch(failure => { if (!abort.signal.aborted) setError(errorText(failure)); });
    return () => abort.abort();
  }, [examId, refresh]);

  async function change(target: Target) {
    if (!examId || !status || busy) return false;
    setBusy(true);
    setError('');
    try {
      setStatus(await teacherApi.setPaperGradingState(examId, target, status.revision));
      return true;
    } catch (failure) {
      setError(errorText(failure));
      return false;
    } finally {
      setBusy(false);
    }
  }

  return { status, error, busy, change, retry: () => setRefresh(value => value + 1) };
}

export function PaperProgress({ status }: { status: PaperGradingState }) {
  return <div className="paper-progress">
    <div><strong>{status.confirmed}</strong><span>已确认</span></div>
    <div><strong>{status.pending}</strong><span>待复核</span></div>
    {status.expected != null && <progress aria-label="批改进度" value={status.confirmed} max={status.expected} />}
  </div>;
}

export function PaperGradingDialog({ examId, status, error, busy, change, retry, close, desktop }: {
  examId: string;
  close: () => void;
  desktop?: boolean;
} & ReturnType<typeof usePaperGrading>) {
  if (!status) return null;
  const reopen = status.state === 'completed';
  const pending = !reopen && status.pending > 0;
  const title = reopen ? '继续批卷？' : pending ? `还有 ${status.pending} 份待复核` : '结束本卷批改？';
  const portal = desktop ? 'web-paper-draft web-paper-grading exam-grading paper-review-portal' : undefined;
  return <Sheet title={title} icon={pending ? 'files' : 'check'} variant="paper-finish" portalClassName={portal}
    close={() => { if (!busy) close(); }}>
    <p>{reopen ? '可继续处理本卷的新答题卡。' : pending ? `处理或放弃这 ${status.pending} 份记录后再结束。` : `已确认 ${status.confirmed} 份。结束后仍可补批。`}</p>
    {error && <p className="notice failure" role="alert">{error} <button className="plain" onClick={() => { close(); retry(); }}>刷新状态</button></p>}
    <div className="actions">
      <button className="secondary" disabled={busy} onClick={close}>{pending ? '返回' : '再看看'}</button>
      {pending ? <Link className="primary" to={`/exams/${examId}/scan/reviews`} state={!desktop ? { fromExam: true } : undefined}>去处理待复核</Link>
        : <button className="primary" disabled={busy} onClick={async () => { if (await change(reopen ? 'grading' : 'completed')) close(); }}>
          {busy ? '正在保存…' : reopen ? '继续批卷' : '结束批卷'}
        </button>}
    </div>
  </Sheet>;
}

export function CopyPaperDraftDialog({ examId, open, close, desktop }: {
  examId: string;
  open: boolean;
  close: () => void;
  desktop?: boolean;
}) {
  const navigate = useNavigate();
  const request = useRef<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!open) return null;

  async function copy() {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      request.current ??= crypto.randomUUID();
      const draft = await teacherApi.copyPaperDraft(examId, request.current);
      close();
      navigate(desktop ? `/exams/paper-drafts/${draft.id}` : `/exams/${draft.id}/edit`);
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  return <Sheet title="复制为新卷？" close={() => { if (!busy) close(); }} icon="files" variant="paper-finish"
    portalClassName={desktop ? 'web-paper-draft web-paper-grading exam-grading paper-review-portal' : undefined}>
    <p>沿用原件、评分规则和答案，新试卷可以继续编辑。</p>
    {error && <p className="notice failure" role="alert">{error}</p>}
    <div className="actions">
      <button type="button" className="secondary" disabled={busy} onClick={close}>取消</button>
      <button type="button" className="primary" disabled={busy} onClick={() => void copy()}>
        {busy ? '正在复制…' : '复制为新卷'}
      </button>
    </div>
  </Sheet>;
}

export function DesktopPaperGrading({ examId, grading }: { examId: string; grading: ReturnType<typeof usePaperGrading> }) {
  const [open, setOpen] = useState(false);
  const [copy, setCopy] = useState(false);
  const status = grading.status;
  if (!status) return grading.error ? <p className="notice failure">{grading.error} <button className="plain" onClick={grading.retry}>重试</button></p> : null;
  if (status.state === 'draft') return status.recognition_blocker ? <p className="notice warning">{status.recognition_blocker}</p> : null;
  if (status.state === 'ready') return null;
  return <section className="desktop-paper-status">
    <span>{paperStateLabels[status.state]}</span>
    <PaperProgress status={status} />
    <button className="secondary" onClick={() => setOpen(true)}>{status.state === 'completed' ? '继续批卷' : '结束批卷'}</button>
    <button className="secondary" onClick={() => setCopy(true)}>复制为新卷</button>
    {open && <PaperGradingDialog examId={examId} {...grading} desktop close={() => setOpen(false)} />}
    <CopyPaperDraftDialog examId={examId} open={copy} desktop close={() => setCopy(false)} />
  </section>;
}
