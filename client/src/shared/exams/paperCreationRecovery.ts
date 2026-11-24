import type { AnswerSheetTemplateItem, PaperDraftInput } from '../../api/teacher';
import { teacherSessionPrefix } from '../teacherSessionStorage';

export type SelectedPaperTemplate = Pick<AnswerSheetTemplateItem, 'id' | 'name' | 'revision' | 'choice_questions'>;

interface PaperCreationForm {
  input: PaperDraftInput;
  step: number;
  template?: SelectedPaperTemplate;
  cardNumbers?: Record<number, string>;
}

export interface PendingPaperCreation extends PaperCreationForm {
  requestId: string;
  editing?: PaperCreationForm;
}

type PaperCreationRecovery = PendingPaperCreation | { examId: string };

export function paperCreationKey(desktop: boolean) {
  const prefix = teacherSessionPrefix('paper-create-v1');
  return prefix && prefix + (desktop ? 'web' : 'h5');
}

function validForm(entry: Partial<PaperCreationForm> | null | undefined): entry is PaperCreationForm {
  return typeof entry?.input?.title === 'string' && typeof entry.input.description === 'string' &&
    typeof entry.input.class_id === 'string' && Boolean(entry.input.answers) &&
    typeof entry.step === 'number' && Number.isInteger(entry.step) && entry.step >= 0 && entry.step <= 2 &&
    (!entry.template || Array.isArray(entry.template.choice_questions));
}

export function readPaperCreation(key?: string): PaperCreationRecovery | undefined {
  if (!key) return undefined;
  try {
    const entry = JSON.parse(sessionStorage.getItem(key) ?? 'null') as Partial<PendingPaperCreation & { examId: string }> | null;
    if (typeof entry?.examId === 'string' && /^\d+$/.test(entry.examId)) return { examId: entry.examId };
    const { requestId, editing } = entry ?? {};
    if (typeof requestId === 'string' && /^[A-Za-z0-9_-]{8,64}$/.test(requestId) &&
      validForm(entry) && (editing === undefined || validForm(editing))) {
      return { ...entry, requestId, editing };
    }
  } catch { /* Unavailable or invalid storage starts a new form. */ }
  return undefined;
}

export function writePaperCreation(key?: string, entry?: PaperCreationRecovery) {
  if (!key) return;
  try {
    if (entry) sessionStorage.setItem(key, JSON.stringify(entry));
    else sessionStorage.removeItem(key);
  } catch { /* The current editor still retains its in-memory request. */ }
}

export function clearTeacherPaperCreations() {
  writePaperCreation(paperCreationKey(false));
  writePaperCreation(paperCreationKey(true));
}
