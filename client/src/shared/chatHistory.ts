import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { teachingAssistantApi, type MessageData } from '../api/teachingAssistant';

export function useChatHistory(
  sessionId: string | null | undefined,
  setMessages: Dispatch<SetStateAction<MessageData[]>>,
) {
  const controller = useRef<AbortController>();
  const [initial, setInitial] = useState(false);
  const [more, setMore] = useState(false);
  const [beforeId, setBeforeId] = useState<string>();
  const [failure, setFailure] = useState<'initial' | 'older'>();
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    setBeforeId(undefined);
    setFailure(undefined);
    setMore(false);
    setInitial(Boolean(sessionId));
    if (!sessionId) return;
    const request = new AbortController();
    controller.current = request;

    void teachingAssistantApi.getRecentMessages(sessionId, undefined, request.signal)
      .then(page => {
        if (request.signal.aborted) return;
        const ids = new Set(page.items.map(message => message.id));
        setMessages(current => [
          ...page.items,
          ...current.filter(message => message.conversation_id === sessionId && !ids.has(message.id)),
        ]);
        setBeforeId(page.next_before_id ?? undefined);
      })
      .catch(() => { if (!request.signal.aborted) setFailure('initial'); })
      .finally(() => { if (!request.signal.aborted) setInitial(false); });
    return () => request.abort();
  }, [sessionId, setMessages, retry]);

  async function loadOlder() {
    const signal = controller.current?.signal;
    if (!sessionId || !beforeId || !signal || initial || more) return;
    setMore(true);
    setFailure(undefined);
    try {
      const page = await teachingAssistantApi.getRecentMessages(sessionId, beforeId, signal);
      if (signal.aborted) return;
      setMessages(current => {
        const ids = new Set(current.map(message => message.id));
        return [...page.items.filter(message => !ids.has(message.id)), ...current];
      });
      setBeforeId(page.next_before_id ?? undefined);
    } catch {
      if (!signal.aborted) setFailure('older');
    } finally {
      if (!signal.aborted) setMore(false);
    }
  }

  return { initial, more, beforeId, failure, loadOlder, reload: () => setRetry(value => value + 1) };
}
