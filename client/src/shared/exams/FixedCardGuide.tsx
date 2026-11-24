import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { teacherApi } from '../../api/teacher';
import { Icon, Sheet } from '../mobileControls';
import illustration from './assets/fixed-card-illustration.png';

export function FixedCardGuidePage({ desktop = false }: { desktop?: boolean }) {
  const { examId = '' } = useParams();
  return <FixedCardGuide examId={examId} desktop={desktop}
    back={desktop ? `/exams/paper-drafts/${examId}` : `/exams/${examId}`} />;
}

export function FixedCardGuide({ examId, back, onBack, desktop = false }: {
  examId?: string;
  back?: string;
  onBack?: () => void;
  desktop?: boolean;
}) {
  const [sample, setSample] = useState<{ url: string; version: string } | null>();
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [retry, setRetry] = useState(0);
  const loading = Boolean(examId) && sample === undefined && !error;

  useEffect(() => {
    setSample(undefined);
    setError(false);
    setExpanded(false);
    if (!examId) return;
    const abort = new AbortController();
    let url = '';
    void teacherApi.getFixedCardReference(examId, abort.signal).then(reference => {
      if (abort.signal.aborted) return;
      if (reference) {
        url = URL.createObjectURL(reference.image);
        setSample({ url, version: reference.version });
      } else setSample(null);
    }).catch(() => { if (!abort.signal.aborted) setError(true); });
    return () => {
      abort.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [examId, retry]);

  return <section className="fixed-card-guide">
    <header className="heading">
      {back ? <Link className="round" to={back} aria-label="返回"><Icon name="left" size={21} /></Link>
        : <button type="button" className="round" aria-label="返回" onClick={onBack}><Icon name="left" size={21} /></button>}
      <h1>固定版式答题卡</h1>
    </header>
    <p className="fixed-card-guide-caption">{sample?.version ? `本卷版式 · ${sample.version}` : '版式以需求方提供的样张为准'}</p>
    <figure className="fixed-card-guide-stage">
      {loading ? <p role="status">正在加载样张…</p> : error ? <p role="alert">无法加载答题卡样张</p>
        : <img src={sample?.url ?? illustration} alt={sample ? '本卷固定答题卡原版' : '固定答题卡示意，以正式样张为准'}
            onError={sample ? () => setError(true) : undefined} />}
    </figure>
    <div className="fixed-card-guide-help">
      <Icon name="info" size={19} />
      <div><strong>使用指定答题卡</strong><p>请使用提供的原版答题卡。</p></div>
    </div>
    <div className="fixed-card-guide-actions">
      {error ? <button type="button" className="secondary wide" onClick={() => setRetry(value => value + 1)}>重试</button>
        : <button type="button" className="primary wide" disabled={!sample} onClick={() => setExpanded(true)}>
            {sample ? '查看原版答题卡' : loading ? '正在加载…' : '样张待提供'}
          </button>}
    </div>
    {sample && expanded && <Sheet title="原版答题卡"
      portalClassName={desktop ? 'web-paper-draft web-paper-grading exam-grading paper-review-portal' : undefined}
      close={() => setExpanded(false)}>
      <img className="fixed-card-guide-enlarged" src={sample.url} alt="本卷固定答题卡原版" />
    </Sheet>}
  </section>;
}
