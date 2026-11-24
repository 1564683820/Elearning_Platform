import { useEffect, useState, useSyncExternalStore } from 'react';
import { CHAT_FILE_LIMIT, teachingAssistantApi, type ChatAttachment, type ChatRequest } from '../api/teachingAssistant';
import { rememberChatRequest, recoverChatReply, type ChatDraftRequest } from './chatRequests';
import { teacherSessionPrefix } from './teacherSessionStorage';

interface PendingChatFile {
  id: string;
  name: string;
  type: string;
  file?: File;
  uploaded?: ChatAttachment;
}

interface ComposerDraft {
  text: string;
  files: PendingChatFile[];
  attempt?: ChatDraftRequest;
}

const emptyDraft: ComposerDraft = { text: '', files: [] };
const drafts = new Map<string, ComposerDraft>();
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function readDraft(key: string): ComposerDraft {
  const cached = drafts.get(key);
  if (cached) return cached;
  let stored = emptyDraft;
  try {
    const candidate = JSON.parse(sessionStorage.getItem(key) ?? 'null') as ComposerDraft | null;
    if (typeof candidate?.text === 'string' && Array.isArray(candidate.files)) {
      stored = {
        text: candidate.text,
        files: candidate.files.filter(item => Boolean(item?.uploaded?.attachment_id)).slice(0, CHAT_FILE_LIMIT),
        attempt: candidate.attempt,
      };
    }
  } catch { /* A damaged or unavailable storage entry can start empty. */ }
  drafts.set(key, stored);
  return stored;
}

function writeDraft(key: string, draft: ComposerDraft) {
  drafts.set(key, draft);
  if (key.startsWith('elearning:chat-draft:')) {
    try {
      const files = draft.files.flatMap(({ id, name, type, uploaded }) => uploaded ? [{ id, name, type, uploaded }] : []);
      if (draft.text || files.length || draft.attempt) {
        sessionStorage.setItem(key, JSON.stringify({ text: draft.text, files, attempt: draft.attempt }));
      } else sessionStorage.removeItem(key);
    } catch { /* Keep editing functional if browser storage is unavailable. */ }
  }
  listeners.forEach(listener => listener());
}

export function clearTeacherChatDrafts() {
  const prefix = teacherSessionPrefix('chat-draft');
  if (!prefix) return;
  for (const key of drafts.keys()) if (key.startsWith(prefix)) drafts.delete(key);
  try {
    for (const key of Object.keys(sessionStorage)) if (key.startsWith(prefix)) sessionStorage.removeItem(key);
  } catch { /* Storage is optional. */ }
  listeners.forEach(listener => listener());
}

export function useChatComposer(surface: 'h5' | 'web', sessionId?: string | null) {
  const owner = teacherSessionPrefix('chat-draft');
  const draftKey = (id?: string | null) => `${owner ?? 'anonymous:'}${surface}:${id || 'new'}`;
  const key = draftKey(sessionId);
  const snapshot = useSyncExternalStore(subscribe, () => readDraft(key));

  useEffect(() => {
    if (!owner || !sessionId) return;
    const current = readDraft(key);
    if (!current.attempt) return;
    const request = new AbortController();
    void recoverChatReply(sessionId, current.attempt.id, request.signal).then(reply => {
      if (reply && !request.signal.aborted && readDraft(key) === current) writeDraft(key, emptyDraft);
    });
    return () => request.abort();
  }, [key, owner, sessionId]);

  function setText(text: string) {
    const current = readDraft(key);
    writeDraft(key, { ...current, text, attempt: current.text.trim() === text.trim() ? current.attempt : undefined });
  }

  function add(selected: File[]) {
    if (!selected.length) return '';
    const current = readDraft(key);
    if (current.files.length + selected.length > CHAT_FILE_LIMIT) return '每次最多添加 4 个附件';
    writeDraft(key, { ...current, attempt: undefined, files: [...current.files, ...selected.map(file => ({
      id: crypto.randomUUID(), name: file.name, type: file.type, file,
    }))] });
    return '';
  }

  async function upload(targetSession: string | null | undefined, signal: AbortSignal) {
    const target = draftKey(targetSession);
    const attachments: ChatAttachment[] = [];
    for (const item of readDraft(target).files) {
      signal.throwIfAborted();
      const uploaded = item.uploaded ?? (item.file && await teachingAssistantApi.uploadAttachment(item.file, signal));
      if (!uploaded) continue;
      signal.throwIfAborted();
      if (!item.uploaded) {
        const current = readDraft(target);
        writeDraft(target, { ...current, files: current.files.map(row => row.id === item.id ? { ...row, uploaded, file: undefined } : row) });
      }
      attachments.push(uploaded);
    }
    return attachments;
  }

  return {
    text: snapshot.text, files: snapshot.files, setText, add, upload,
    clear: (id?: string | null) => writeDraft(draftKey(id), emptyDraft),
    remove: (id: string) => {
      const current = readDraft(key);
      writeDraft(key, { ...current, attempt: undefined, files: current.files.filter(item => item.id !== id) });
    },
    begin: (id: string, message: string) => {
      const destination = draftKey(id);
      const current = readDraft(key);
      if (destination !== key) writeDraft(key, emptyDraft);
      writeDraft(destination, { ...current, text: message });
    },
    requestId: (id: string, parameters: ChatRequest) => {
      const target = draftKey(id);
      const current = readDraft(target);
      const attempt = rememberChatRequest(current.attempt, parameters);
      writeDraft(target, { ...current, attempt });
      return attempt.id;
    },
  };
}

export function ChatAttachmentButton({ id, name }: { id: string; name: string }) {
  const [failure, setFailure] = useState('');
  return <span>
    <button type="button" title={name} onClick={() => {
      setFailure('');
      void teachingAssistantApi.downloadAttachment(id, name).catch(() => setFailure('附件下载失败'));
    }}>{name}</button>
    {failure && <span role="alert">{failure}</span>}
  </span>;
}
