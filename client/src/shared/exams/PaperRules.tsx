import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { teacherApi, type PaperDraft } from '../../api/teacher';
import { Icon, errorText } from '../mobileControls';

export function PaperRules({ desktop = false }: { desktop?: boolean }) {
  const { examId = '' } = useParams();
  const { state } = useLocation();
  const [draft, setDraft] = useState<PaperDraft>();
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const request = new AbortController();
    setDraft(undefined);
    setError('');
    void teacherApi.getPaperDraft(examId, request.signal).then(result => {
      if (!request.signal.aborted) setDraft(result);
    }).catch(failure => {
      if (!request.signal.aborted) setError(errorText(failure));
    });
    return () => request.abort();
  }, [examId, revision]);

  const back = desktop ? `/exams/paper-drafts/${examId}` : `/exams/${examId}`;
  return <section className="records paper-rules">
    <header className="heading records-heading">
      <Link className="round" to={back} state={state} aria-label="返回"><Icon name="left" /></Link>
      <h1>评分规则与本卷答案</h1>
    </header>
    {error ? <p className="notice failure" role="alert">{error} <button className="plain" onClick={() => setRevision(value => value + 1)}>重试</button></p>
      : draft ? <>
        <p className="caption records-caption">{draft.title}</p>
        <div className="list-card paper-rules-summary">
          {draft.template_name && <strong>{draft.template_name}</strong>}
          <small>{draft.questions.length} 题 · 满分 {draft.questions.reduce((sum, question) => sum + question.score, 0)} 分</small>
        </div>
        {draft.questions.length ? <ol className="paper-rule-questions">{draft.questions.map(question => (
          <li className="list-card" key={question.question_number}>
            <div><strong>第 {question.question_number} 题</strong><small>{question.score} 分</small></div>
            <ul aria-label={question.answer ? `标准答案 ${question.answer}` : '标准答案待填写'}>
              {question.options.map(option => <li key={option} data-answer={option === question.answer}>
                {option}{option === question.answer && <Icon name="check" size={14} />}
              </li>)}
            </ul>
          </li>
        ))}</ol> : <p className="notice">还没有设置评分规则</p>}
      </> : <p className="notice" role="status">正在加载…</p>}
  </section>;
}
