import { FixedCardCapture } from '../../shared/exams/FixedCardCapture';
import { FixedCardGuidePage } from '../../shared/exams/FixedCardGuide';
import { AnswerCardPhoto } from '../../shared/exams/AnswerCardPhoto';
import { FixedCardReview, PendingReviews } from '../../shared/exams/FixedCardReview';
import { GradingRecords, RecordDetail } from '../../shared/exams/Records';
import { PaperRules } from '../../shared/exams/PaperRules';
import './paperDraftPage.css';
import '../../shared/exams/paperGrading.css';
import './paperGradingPage.css';

const pages = {
  records: <GradingRecords desktop />,
  rules: <PaperRules desktop />,
  score: <RecordDetail desktop />,
  history: <RecordDetail view="history" />,
  photo: <AnswerCardPhoto />,
  capture: <FixedCardCapture desktop />,
  guide: <FixedCardGuidePage desktop />,
  pending: <PendingReviews desktop />,
  review: <FixedCardReview desktop />,
};

export default function PaperGradingPage({ view }: { view: keyof typeof pages }) {
  return <div className="web-paper-draft web-paper-grading exam-grading">{pages[view]}</div>;
}
