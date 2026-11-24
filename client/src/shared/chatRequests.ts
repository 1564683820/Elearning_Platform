import { teachingAssistantApi, type ChatRequest, type ChatResponse } from '../api/teachingAssistant';

export interface ChatDraftRequest {
  id: string;
  key: string;
}

export function rememberChatRequest(previous: ChatDraftRequest | undefined, parameters: ChatRequest): ChatDraftRequest {
  const { conversation_id, class_id, message, attachment_ids } = parameters;
  const key = JSON.stringify([conversation_id, class_id ?? null, message, [...(attachment_ids ?? [])].sort()]);
  return previous?.key === key ? previous : { key, id: crypto.randomUUID() };
}

export async function recoverChatReply(conversation: string, id: string, signal: AbortSignal): Promise<ChatResponse | undefined> {
  try {
    const result = await teachingAssistantApi.getChatRequest(conversation, id, signal);
    return result.status === 'completed' ? result.reply : undefined;
  } catch {
    // Preserve the draft when the connection has not returned or the session is unavailable.
    return undefined;
  }
}
