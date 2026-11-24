import { useEffect, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { teacherApi, type ExamKnowledge as ExamKnowledgeData } from '../../api/teacher';
import './examKnowledge.css';

export function ExamKnowledge({ back }: { back: string }) {
  const { examId = '', questionNumber = '' } = useParams();
  const location = useLocation();
  const [params] = useSearchParams();
  const dateFrom = params.get('date_from');
  const dateTo = params.get('date_to');
  const number = questionNumber ? Number(questionNumber) : undefined;
  const [data, setData] = useState<ExamKnowledgeData>();
  const [error, setError] = useState('');
  useEffect(() => {
    setError('');
    setData(undefined);
    if (!/^\d+$/.test(examId) || (number !== undefined && (!Number.isSafeInteger(number) || number < 1))) {
      setError('未找到试卷题目');
      return;
    }
    if ((Boolean(dateFrom) !== Boolean(dateTo)) || (number === undefined && !dateFrom)) {
      setError('请选择题号或完整日期范围');
      return;
    }
    const controller = new AbortController();
    const dates = dateFrom && dateTo ? { date_from: dateFrom, date_to: dateTo } : undefined;
    void teacherApi.getExamKnowledge(examId, number, controller.signal, dates)
      .then(result => { if (!controller.signal.aborted) setData(result); })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : '无法读取统计');
      });
    return () => controller.abort();
  }, [dateFrom, dateTo, examId, number]);

  const question = number !== undefined ? data?.questions[0] : undefined;
  const count = data?.count ?? 0;
  const ratio = question && count ? ((question.correct * 100) / count).toFixed(1) + '%' : '—';
  const dates = data?.date_from && data.date_to &&
    (data.date_from === data.date_to ? data.date_from : `${data.date_from} 至 ${data.date_to}`);
  const updatedAt = data?.updated_at;
  const displayTime = updatedAt && new Date(dates && !/(?:Z|[+-]\d{2}:\d{2})$/.test(updatedAt) ? `${updatedAt}Z` : updatedAt)
    .toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: dates ? 'Asia/Shanghai' : undefined });
  const distribution = question ? Object.entries(question.distribution).sort(([left, lCount], [right, rCount]) => {
    if (left === question.answer || right === question.answer) return left === question.answer ? -1 : 1;
    const specials = ['空白', '无效填涂'];
    return Number(specials.includes(left)) - Number(specials.includes(right)) || rCount - lCount || left.localeCompare(right);
  }) : [];

  return <section className="exam-knowledge" aria-labelledby="exam-knowledge-title">
    <header className="exam-knowledge-heading">
      <Link to={back} aria-label="返回"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="m15 18-6-6 6-6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg></Link>
      <h1 id="exam-knowledge-title">{number && Number.isSafeInteger(number) && number > 0 ? `第 ${number} 题统计` : '试卷统计'}</h1>
    </header>
    {error ? <p role="alert">{error}</p> : !data ? <p aria-live="polite">正在加载…</p> : <>
      <p className="exam-knowledge-subtitle">{data.title}</p>
      {dates && <p className="exam-knowledge-subtitle">{dates} · 北京时间</p>}
      <p className="exam-knowledge-subtitle">{count} 份有效答卷{displayTime && ` · ${displayTime} 更新`}</p>
      <div className="exam-knowledge-metric">
        <span>{number !== undefined ? '正确率' : '平均分'}</span>
        <strong>{number !== undefined ? ratio : (data.average?.toFixed(1) ?? '—')}</strong>
        {question && <small>{question.correct} / {count} 份答对</small>}
      </div>
      <h2>{number !== undefined ? '选项分布' : '各题正确率'}</h2>
      {!count ? <p>暂无有效答卷</p> : number === undefined && data.questions.length > 0 ? <ul className="exam-knowledge-questions">
        {data.questions.map(item => <li key={item.number}>
          <Link to={`${location.pathname}/${item.number}${location.search}`} state={location.state}>
            <span>第 {item.number} 题</span><strong>{((item.correct * 100) / count).toFixed(1)}%</strong>
          </Link>
        </li>)}
      </ul> : distribution.length ? <ul className="exam-knowledge-distribution">
        {distribution.map(([label, votes]) => <li key={label}>
          <span>{label === question?.answer ? `正确 ${label}` : label}</span>
          <span className="exam-knowledge-track" aria-hidden="true"><i style={{ width: `${count ? (votes * 100) / count : 0}%` }} data-correct={label === question?.answer} /></span>
          <small>{votes} 份</small>
        </li>)}
      </ul> : <p>暂无单题统计</p>}
    </>}
    <Link className="exam-knowledge-back" to={back}>返回问答</Link>
  </section>;
}
