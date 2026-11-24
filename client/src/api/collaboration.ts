// 协作增强 API 方法封装
import client from './client';

function extractData<T>(res: { data: { data: T } }): T {
  return res.data.data;
}

// ========== 类型定义 ==========

export interface AssistantData {
  teacher_id: number;
  nickname: string;
  role: string;
  joined_at: string;
}

export interface AuditLogData {
  id: number;
  class_id: number | null;
  operator_id: number;
  operator_role: string;
  action_type: string;
  target_type: string | null;
  target_id: number | null;
  detail: any;
  created_at: string;
}

export interface AuditLogListData {
  items: AuditLogData[];
  total: number;
  page: number;
  page_size: number;
}

export interface PersonalReportData {
  user_id: number;
  nickname: string;
  period_start: string;
  period_end: string;
  study_days: number;
  total_words: number;
  total_training: number;
  total_exams: number;
  overall_accuracy: number;
  module_breakdown: { category: string; total: number; accuracy: number }[];
  weakness_points: { knowledge_point: string; count: number }[];
  daily_trend: { date: string; words: number }[];
  improvement_suggestions: string[];
}

export interface ClassReportData {
  class_id: number;
  class_name: string;
  student_count: number;
  period_start: string;
  period_end: string;
  overall_accuracy: number;
  total_words: number;
  total_exams: number;
  total_training: number;
  avg_study_days: number;
  top_mistakes: { knowledge_point: string; count: number }[];
  accuracy_trend: { week: string; accuracy: number; total: number }[];
  student_ranking: { student_id: number; name: string; accuracy: number; total_quiz: number }[];
}

export interface SchoolAdminData {
  id: number;
  user_id: number;
  school_name: string;
  contact_phone: string | null;
  permissions: any;
  is_active: number;
  created_at: string;
}

export interface SchoolDashboardData {
  school_name: string;
  total_classes: number;
  total_students: number;
  total_teachers: number;
  total_exams: number;
  class_stats: { class_id: number; class_name: string; student_count: number; stage: number }[];
}

// ========== API 方法 ==========

export const collaborationApi = {
  // 助教管理
  addAssistant: (data: { class_id: string | number; student_id: string | number; permissions?: any }) =>
    client.post('/collaboration/assistants', data).then(extractData<AssistantData>),

  removeAssistant: (classId: string | number, assistantId: string | number) =>
    client.delete(`/collaboration/assistants/${classId}/${assistantId}`),

  listAssistants: (classId: string | number) =>
    client.get(`/collaboration/assistants/${classId}`).then(extractData<AssistantData[]>),

  updateRole: (data: { teacher_id: number; role: string }) =>
    client.put('/collaboration/assistants/role', data),

  // 多教师协作批改
  assignGradingTask: (data: { submission_id: string | number; grader_id?: string | number; grader_role?: string; assigned_questions?: number[] }) =>
    client.post('/collaboration/grading/assign', data),

  submitGradingResult: (data: { submission_id: string | number; question_scores: any[]; overall_comment?: string }) =>
    client.post('/collaboration/grading/submit', data),

  reviewAndFinalize: (data: { submission_id: string | number; adjustments: any; final_score: number }) =>
    client.post('/collaboration/grading/review', data),

  getGradingStatus: (examId: string | number) =>
    client.get(`/collaboration/grading/status/${examId}`).then(extractData<any[]>),

  // 审计日志
  queryAuditLogs: (params: {
    class_id?: string | number; action_type?: string; operator_id?: number;
    start_date?: string; end_date?: string; page?: number; page_size?: number;
  }) => client.get('/collaboration/audit-logs', { params }).then(extractData<AuditLogListData>),


  // 学习报告
  getPersonalReport: (params: { class_id?: string | number; period_start?: string; period_end?: string }) =>
    client.get('/collaboration/reports/personal', { params }).then(extractData<PersonalReportData>),

  getClassReport: (classId: string | number, params?: { period_start?: string; period_end?: string }) =>
    client.get(`/collaboration/reports/class/${classId}`, { params }).then(extractData<ClassReportData>),

  // 学校管理
  createSchoolAdmin: (data: { user_id: string | number; school_name: string; contact_phone?: string; permissions?: any }) =>
    client.post('/collaboration/school/admins', data).then(extractData<SchoolAdminData>),

  listSchoolAdmins: () =>
    client.get('/collaboration/school/admins').then(extractData<SchoolAdminData[]>),

  getSchoolDashboard: () =>
    client.get('/collaboration/school/dashboard').then(extractData<SchoolDashboardData>),

  toggleSchoolAdmin: (userId: string | number) =>
    client.post(`/collaboration/school/admins/${userId}/toggle`),
};
