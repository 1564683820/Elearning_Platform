import { PaperDraftEditor } from '../../shared/exams/PaperDraftEditor';
import { useParams } from 'react-router-dom';
import './paperDraftPage.css';
import '../../shared/exams/paperGrading.css';
import './paperGradingPage.css';

export default function PaperDraftPage() {
  const { examId } = useParams();
  return <main className="web-paper-draft"><PaperDraftEditor key={examId ?? 'new'} desktop /></main>;
}
