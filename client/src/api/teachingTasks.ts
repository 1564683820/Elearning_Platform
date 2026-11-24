import client, { authenticatedFetch, getBaseURL } from './client';

export interface TeachingQuestion {
  type: 'choice'; stem: string; options: string[]; answer: 'A' | 'B' | 'C' | 'D';
  explanation: string; score: number; knowledge_point: string; citation_ids: string[];
}
export interface TeachingArtifact {
  title: string; lesson: { title: string; minutes: number; activity: string }[];
  questions: TeachingQuestion[]; total_score: number;
}
export interface TeachingTask {
  id: string; class_id: string; objective: string; status: string; created_at: string;
  artifact: Partial<TeachingArtifact>; artifact_version: number; approved_version: number | null;
  published_exam_id: string | null; error_code: string | null;
  checkpoint: {
    completed?: string[]; config?: { question_count: number; duration_minutes: number };
    analysis?: { submission_count: number; exam_ids: string[]; topics: { knowledge_point: string; wrong: number; observations: number }[] };
    citations?: { id: string; document_id: string; version: string; page: number | null; title: string; snippet: string }[];
    validation_errors?: string[];
    traces?: { node: string; latency_ms: number; model?: string; usage?: Record<string, number> | null; cost?: number | null }[];
  };
}
interface Envelope<T> { data: T }
const root = '/teaching-tasks';
export const teachingTasks = {
  list: async () => (await client.get<Envelope<TeachingTask[]>>(root)).data.data,
  get: async (id: string) => (await client.get<Envelope<TeachingTask>>(`${root}/${id}`)).data.data,
  create: async (body: { class_id: string; objective: string; question_count: number; duration_minutes: number }) =>
    (await client.post<Envelope<TeachingTask>>(root, body)).data.data,
  command: async (task: TeachingTask, action: string) =>
    (await client.post<Envelope<TeachingTask>>(`${root}/${task.id}/${action}`, { version: task.artifact_version })).data.data,
  save: async (task: TeachingTask, artifact: TeachingArtifact) =>
    (await client.put<Envelope<TeachingTask>>(`${root}/${task.id}/artifact`, { version: task.artifact_version, artifact })).data.data,
};

// fetch keeps the JWT in headers; EventSource cannot attach Authorization headers.
export async function watchTeachingTask(id: string, signal: AbortSignal, onTask: (task: TeachingTask) => void) {
  const response = await authenticatedFetch(`${getBaseURL()}${root}/${id}/events`, {
    signal, headers: { Accept: 'text/event-stream' },
  });
  if (!response.ok || !response.body) throw new Error('无法读取任务进度，请刷新后重试。');
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '';
  let terminal = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      let boundary: number;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        if (frame.startsWith('event: revoked')) throw new Error('班级访问权限已变化，请刷新页面。');
        const data = frame.split('\n').filter(line => line.startsWith('data: ')).map(line => line.slice(6)).join('\n');
        if (data) {
          const task = JSON.parse(data) as TeachingTask;
          terminal = !['queued', 'running'].includes(task.status);
          onTask(task);
        }
      }
    }
    if (!terminal && !signal.aborted) throw new Error('进度连接中断，已改为定期刷新。');
  } finally { reader.releaseLock(); }
}
