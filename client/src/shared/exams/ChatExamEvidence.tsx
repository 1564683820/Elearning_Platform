import type { SourceItem } from '../../api/teachingAssistant';
import './chatExamEvidence.css';

export function examSourcePath(source: SourceItem, surface: 'web' | 'h5', sessionId?: string) {
  const { date_from, date_to } = source;
  if (!source.question_number && !(date_from && date_to)) return `/exams/${source.id}/records`;
  const params = new URLSearchParams();
  if (date_from && date_to) {
    params.set('date_from', date_from);
    params.set('date_to', date_to);
  }
  if (surface === 'h5' && sessionId) params.set('session', sessionId);
  const path = surface === 'h5' ? '/sources' : '/exams/knowledge';
  const question = source.question_number ? `/${source.question_number}` : '';
  return `${path}/${source.id}${question}${params.size ? `?${params}` : ''}`;
}

export function singleExamEvidence(sources: SourceItem[] | null | undefined) {
  const exams = sources?.filter(source => source.type === 'exam_result') ?? [];
  if (exams.length !== 1) return undefined;
  const source = exams[0];
  const stats = source.exam_stats;
  if (!source.question_number || !stats || !Number.isSafeInteger(stats.confirmed) || stats.confirmed <= 0 ||
      !Number.isSafeInteger(stats.correct) || stats.correct < 0 || stats.correct > stats.confirmed) return undefined;
  return { questionNumber: source.question_number, stats };
}

export function ChatExamEvidence({ evidence }: { evidence: NonNullable<ReturnType<typeof singleExamEvidence>> }) {
  const { questionNumber, stats } = evidence;
  const { confirmed, correct, leading_wrong: wrong } = stats;
  const hasLeadingWrong = wrong && /^[A-H]$/.test(wrong.option) && Number.isSafeInteger(wrong.count) &&
    wrong.count > 0 && wrong.count <= confirmed - correct;
  return <div className="chat-exam-evidence">
    <strong className="chat-exam-evidence-title">{hasLeadingWrong
      ? `${wrong.count} 份答卷错选 ${wrong.option}`
      : `第 ${questionNumber} 题统计`}</strong>
    <div className="chat-exam-evidence-metric">
      <strong>{(correct * 100 / confirmed).toFixed(1)}%</strong>
      <span>正确率 · {correct} / {confirmed} 份</span>
    </div>
  </div>;
}
