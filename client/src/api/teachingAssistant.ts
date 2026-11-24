// 教学助手 API 封装
import client, { authenticatedFetch, getBaseURL } from './client';

/* ========== 类型定义 ========== */

export interface SessionItem {
  id: string;
  title: string;
  summary: string;
  class_id: string | number | null;
  status: number;
  created_at: string;
  updated_at: string;
}

export interface MessageData {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  message_type: string;
  sources: SourceItem[] | null;
  created_at: string;
  attachments?: ChatAttachment[];
}

export interface ChatAttachment {
  attachment_id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  parse_status: 'ready';
}

export const CHAT_FILE_ACCEPT = '.pdf,.docx,.txt';
export const CHAT_IMAGE_ACCEPT = '.jpg,.jpeg,.png,.webp';
export const CHAT_FILE_LIMIT = 4;

export interface SourceItem {
  type: string;
  id: string;
  title: string;
  snippet: string;
  chunk_id: string;
  score: number;
  question_number?: number | null;
  date_from?: string;
  date_to?: string;
  exam_stats?: {
    confirmed: number;
    correct: number;
    updated_at?: string | null;
    leading_wrong?: { option: string; count: number } | null;
  };
}

export interface ChatRequest {
  conversation_id?: string | number | null;
  message: string;
  class_id?: string | number | null;
  message_type?: string;
  file_url?: string;
  attachment_ids?: string[];
  request_id?: string;
}

export interface ChatResponse {
  conversation_id: string;
  user_message_id?: string;
  message_id: string;
  content: string;
  sources: SourceItem[];
  intent: string;
  suggested_questions: string[];
}

export type ChatRequestStatus = { status: 'unknown' | 'pending' } | { status: 'completed'; reply: ChatResponse };

export interface MemoryItem {
  id: string;
  teacher_id: string;
  memory_type: string;
  memory_key: string;
  memory_value: string;
  importance: number;
  trigger_keywords: string[] | null;
  access_count: number;
  last_accessed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UploadResult {
  file_url: string;
  file_type: string;
  file_name: string;
  ocr_text?: string;
}

/* ========== Agent Skills 类型定义 ========== */

export type SkillType = 'ppt' | 'exam' | 'qa';

export const SKILL_TYPE_LABELS: Record<SkillType, string> = {
  ppt: 'PPT设计',
  exam: '试卷设计',
  qa: '问答',
};

export interface SkillItem {
  id: string;
  teacher_id: string;
  name: string;
  description: string;
  skill_type: SkillType;
  file_name: string;
  raw_content: string;
  design_tokens: Record<string, unknown> | null;
  prompt_snippet: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SkillListResponse {
  items: SkillItem[];
  total: number;
  ppt_count: number;
  exam_count: number;
}

/* ========== 辅助函数 ========== */

function extractData<T>(response: { data: { code?: number; data: T } }): T {
  return response.data.data;
}

/* ========== API 方法 ========== */

export const teachingAssistantApi = {
  getExamKnowledgeAvailability(signal?: AbortSignal) {
    return client
      .get('/teaching-assistant/exam-knowledge/availability', { signal })
      .then(extractData<{ has_confirmed_results: boolean }>);
  },

  // 会话列表
  listSessions(page = 1, pageSize = 20) {
    return client
      .get('/teaching-assistant/sessions', { params: { page, page_size: pageSize } })
      .then(extractData<{ items: SessionItem[]; total: number }>);
  },

  // 创建会话
  createSession(classId?: string | number | null) {
    return client
      .post('/teaching-assistant/sessions', { class_id: classId ?? null })
      .then(extractData<SessionItem>);
  },

  // 获取会话消息
  getMessages(conversationId: string | number) {
    return client
      .get(`/teaching-assistant/sessions/${conversationId}/messages`)
      .then(extractData<{ items: MessageData[] }>);
  },

  getRecentMessages(conversationId: string, beforeId?: string, signal?: AbortSignal) {
    return client
      .get(`/teaching-assistant/sessions/${conversationId}/messages`, {
        params: { latest: true, before_id: beforeId }, signal,
      })
      .then(extractData<{ items: MessageData[]; next_before_id?: string | null }>);
  },

  // 删除（归档）会话
  deleteSession(conversationId: string | number) {
    return client
      .delete(`/teaching-assistant/sessions/${conversationId}`)
      .then(extractData<null>);
  },

  // 批量删除会话（同时清除向量数据库）
  batchDeleteSessions(sessionIds: (string | number)[]) {
    return client
      .delete('/teaching-assistant/sessions/batch', { data: { session_ids: sessionIds } })
      .then(extractData<{ deleted: number }>);
  },

  // 非流式对话
  chat(params: ChatRequest) {
    return client
      .post('/teaching-assistant/chat', params)
      .then(extractData<ChatResponse>);
  },

  // 流式对话（SSE），返回 fetch 响应用于手动解析
  chatStream(params: ChatRequest, signal?: AbortSignal): Promise<Response> {
    return authenticatedFetch(`${getBaseURL()}/teaching-assistant/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
      signal,
    });
  },

  getChatRequest(conversationId: string, requestId: string, signal?: AbortSignal): Promise<ChatRequestStatus> {
    return client.get(`/teaching-assistant/sessions/${conversationId}/requests/${encodeURIComponent(requestId)}`, { signal, timeout: 4000 })
      .then(extractData<ChatRequestStatus>);
  },

  // 上传文件
  uploadFile(file: File): Promise<UploadResult> {
    const formData = new FormData();
    formData.append('file', file);
    return client
      .post('/teaching-assistant/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then(extractData<UploadResult>);
  },

  uploadAttachment(file: File, signal?: AbortSignal): Promise<ChatAttachment> {
    const data = new FormData();
    data.append('file', file);
    return client.post('/teaching-assistant/upload', data, {
      params: { structured: true }, signal,
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(extractData<ChatAttachment>);
  },

  async downloadAttachment(id: string, name: string) {
    const response = await authenticatedFetch(`${getBaseURL()}/teaching-assistant/attachments/${encodeURIComponent(id)}`);
    if (!response.ok) throw new Error('附件暂不可用');
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  },

  // 获取长期记忆列表
  listMemory(page = 1, pageSize = 20) {
    return client
      .get('/teaching-assistant/memory', { params: { page, page_size: pageSize } })
      .then(extractData<{ items: MemoryItem[]; total: number }>);
  },

  // 删除记忆
  deleteMemory(memoryId: string | number) {
    return client
      .delete(`/teaching-assistant/memory/${memoryId}`)
      .then(extractData<null>);
  },

  /* ========== Agent Skills 方法 ========== */

  // 上传 SKILL.md 文件
  uploadSkill(file: File, skillType: SkillType = 'ppt'): Promise<SkillItem> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('skill_type', skillType);
    return client
      .post('/teaching-assistant/skills/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then(extractData<SkillItem>);
  },

  // 获取技能列表（支持按类型过滤）
  listSkills(skillType?: SkillType): Promise<SkillListResponse> {
    const params: Record<string, string> = {};
    if (skillType) params.skill_type = skillType;
    return client
      .get('/teaching-assistant/skills', { params })
      .then(extractData<SkillListResponse>);
  },

  // 获取技能详情
  getSkill(skillId: string | number): Promise<SkillItem> {
    return client
      .get(`/teaching-assistant/skills/${skillId}`)
      .then(extractData<SkillItem>);
  },

  // 激活技能
  activateSkill(skillId: string | number): Promise<SkillItem> {
    return client
      .post(`/teaching-assistant/skills/${skillId}/activate`)
      .then(extractData<SkillItem>);
  },

  // 停用技能
  deactivateSkill(skillId: string | number): Promise<SkillItem> {
    return client
      .post(`/teaching-assistant/skills/${skillId}/deactivate`)
      .then(extractData<SkillItem>);
  },

  // 删除技能
  deleteSkill(skillId: string | number): Promise<null> {
    return client
      .delete(`/teaching-assistant/skills/${skillId}`)
      .then(extractData<null>);
  },

  // 获取当前激活技能（可按类型过滤: ppt / exam，不传则返回所有类型）
  getActiveSkill(skillType?: SkillType): Promise<{ items: SkillItem[]; name: string } | null> {
    const params: Record<string, string> = {};
    if (skillType) params.skill_type = skillType;
    return client
      .get('/teaching-assistant/skills/active/current', { params })
      .then(extractData<{ items: SkillItem[]; name: string } | null>);
  },
};
