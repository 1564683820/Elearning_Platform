import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { teacherApi } from '../../api/teacher';
import { Icon } from '../mobileControls';

export function AnswerCardPhoto() {
  const { examId = '', scanId, recordId = '' } = useParams();
  const { search, state } = useLocation();
  const [photo, setPhoto] = useState('');
  const [context, setContext] = useState<{ title: string; number: string }>();
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const root = `/exams/${examId}`;
  const back = scanId ? `${root}/scan/reviews/${scanId}` : `${root}/records/${recordId}${search}`;
  const backLabel = scanId ? '返回核对' : '返回成绩详情';

  useEffect(() => {
    const abort = new AbortController();
    let photoUrl = '';
    setPhoto('');
    setContext(undefined);
    setError(false);

    const details = scanId
      ? teacherApi.getFixedPaperReview(examId, scanId, abort.signal).then(review => ({
        title: [review.exam_title, review.class_required ? review.class_name : '无关联班级'].filter(Boolean).join(' · '),
        number: review.exam_number,
      }))
      : teacherApi.getGradingRecord(examId, recordId, abort.signal).then(record => ({
        title: record.title, number: record.exam_number,
      }));
    void details.then(value => {
      if (!abort.signal.aborted) setContext(value);
    }, () => { /* Photo access is checked independently of the details. */ });

    const request = scanId
      ? teacherApi.getFixedPaperReviewPhoto(examId, scanId, abort.signal)
      : teacherApi.getGradingRecordPhoto(examId, recordId, abort.signal);
    void request.then(blob => {
      if (!abort.signal.aborted) {
        photoUrl = URL.createObjectURL(blob);
        setPhoto(photoUrl);
      }
    }).catch(() => { if (!abort.signal.aborted) setError(true); });
    return () => {
      abort.abort();
      if (photoUrl) URL.revokeObjectURL(photoUrl);
    };
  }, [examId, scanId, recordId, retry]);

  return <section className="fixed-review answer-card-photo">
    <header className="heading">
      <Link className="round" to={back} state={state} aria-label="返回"><Icon name="left" size={21} /></Link>
      <h1>答题卡照片</h1>
    </header>
    <p className="review-subtitle">{context?.title}</p>
    <figure>
      <div className="answer-card-photo-frame">
        {error ? <div className="answer-card-photo-error" role="alert">
          无法加载答题卡照片
          <button className="secondary" onClick={() => setRetry(value => value + 1)}>重试</button>
        </div> : photo ? <img src={photo} alt="答题卡原图" onError={() => setError(true)} />
          : <p role="status">正在加载照片…</p>}
      </div>
      <figcaption>{context?.number ? `${context.number} · ` : ''}原始照片</figcaption>
    </figure>
    <div className="actions review-actions"><Link className="secondary" to={back} state={state}>{backLabel}</Link></div>
  </section>;
}
