import { useState, type FormEvent } from 'react';
import { Sheet, errorText } from '../mobileControls';

export function RecordActionDialog({ action, desktop, close, save }: {
  action: '放弃待复核' | '撤回成绩';
  desktop?: boolean;
  close: () => void;
  save: (reason: string) => Promise<unknown>;
}) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const portal = desktop ? 'web-paper-draft web-paper-grading exam-grading paper-review-portal' : undefined;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !reason.trim()) return;
    setBusy(true);
    setError('');
    try {
      await save(reason.trim());
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  return <Sheet title={`${action}？`} icon="archive" variant="paper-finish" portalClassName={portal}
    close={() => { if (!busy) close(); }}>
    <form className="record-change-form" onSubmit={submit}>
      <p>{action === '撤回成绩' ? '原图和历史会保留，这份成绩将退出统计。' : '原图和操作记录会保留。'}</p>
      <textarea aria-label="操作原因" placeholder="填写原因" maxLength={200} required disabled={busy}
        value={reason} onChange={event => setReason(event.target.value)} />
      {error && <p className="notice failure" role="alert">{error}</p>}
      <div className="actions">
        <button className="secondary" type="button" disabled={busy} onClick={close}>取消</button>
        <button className="primary" disabled={busy || !reason.trim()}>{busy ? '提交中…' : `确认${action === '撤回成绩' ? '撤回' : '放弃'}`}</button>
      </div>
    </form>
  </Sheet>;
}
