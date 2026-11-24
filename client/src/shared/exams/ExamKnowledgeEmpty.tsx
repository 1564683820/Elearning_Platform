import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { teachingAssistantApi } from '../../api/teachingAssistant';
import { Icon } from '../mobileControls';
import './examKnowledgeEmpty.css';

export function useExamKnowledgeAvailability(active: boolean) {
  const [available, setAvailable] = useState<boolean>();
  useEffect(() => {
    setAvailable(undefined);
    if (!active) return;
    const controller = new AbortController();
    void teachingAssistantApi.getExamKnowledgeAvailability(controller.signal).then(result => {
      if (!controller.signal.aborted) setAvailable(result?.has_confirmed_results !== false);
    }).catch(() => {
      if (!controller.signal.aborted) setAvailable(true);
    });
    return () => controller.abort();
  }, [active]);
  return active ? available : undefined;
}

export function ExamKnowledgeEmpty() {
  return <section className="exam-knowledge-empty" aria-labelledby="exam-knowledge-empty-title">
    <div className="exam-knowledge-empty-icon"><Icon name="messages" size={34} /></div>
    <h2 id="exam-knowledge-empty-title">暂无历史批改资料</h2>
    <p>可以添加文件或图片提问。</p>
    <Link className="exam-knowledge-empty-action" to="/exams">去试卷</Link>
  </section>;
}
