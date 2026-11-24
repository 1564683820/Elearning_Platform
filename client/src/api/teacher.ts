// 教师端 API 方法封装
import client, { authenticatedFetch, getBaseURL } from './client';

export interface ManualGradeResult {
  submission_id: string | number;
  student_name: string;
  exam_number: string;
  total_score: number;
  max_score: number;
  wrong_count: number;
  answers: {
    question_number: number;
    student_answer: string;
    correct_answer: string;
    is_correct: boolean | null;
    score: number;
    max_score: number;
  }[];
}

export interface ClassData {
  id: number;
  name: string;
  description: string;
  invite_code: string;
  created_by: number;
  stage: number;
  student_count: number;
  is_active: number;
  created_at: string;
}

export interface StudentData {
  id: number;
  student_id: number;
  nickname: string;
  joined_at: string;
  total_words: number;
  total_training: number;
  avg_accuracy: number;
  study_days: number;
}

export interface ClassDashboardData {
  class_id: number;
  class_name: string;
  student_count: number;
  total_words: number;
  total_quiz: number;
  avg_accuracy: number;
  active_today: number;
  top_mistakes: { knowledge_point: string; count: number }[];
  weekly_trend: { date: string; value: number }[];
}

export interface StudentInfoItem {
  student_number: number;
  student_name: string;
  exam_number: string;
  created_account?: string;
}

export interface StudentInfoUploadResult {
  total: number;
  imported: number;
  skipped: number;
  items: StudentInfoItem[];
}

// ========== 学生考试错题(OCR批卷) ==========

export interface WrongQuestionItem {
  question_index: number;
  question_type: string;
  stem: string;
  user_answer: string;
  correct_answer: string;
  max_score: number;
  score: number;
  ai_comment: string;
}

export interface StudentExamResult {
  exam_id: number;
  exam_title: string;
  total_score: number;
  max_score: number;
  grading_status: string;
  submitted_at: string | null;
  wrong_questions: WrongQuestionItem[];
}

export interface StudentExamMistakesOut {
  student_number: number;
  student_name: string;
  exam_number: string;
  exam_count: number;
  total_wrong: number;
  exams: StudentExamResult[];
}

export interface StudentDetailData {
  student_id: number;
  nickname: string;
  joined_days: number;
  total_words: number;
  total_training: number;
  avg_accuracy: number;
  category_breakdown: { category: string; total: number; wrong: number; accuracy: number }[];
  weakness_points: { knowledge_point: string; count: number }[];
  daily_trend: { date: string; value: number }[];
}

// ========== 试卷相关类型 ==========

export interface ExamListItem {
  id: number;
  title: string;
  class_id: number;
  difficulty: number;
  duration_minutes: number;
  total_score: number;
  status: string; // draft | published | graded
  question_count: number;
  submission_count: number;
  avg_score: number | null;
  grade: string;
  published_at: string | null;
  created_at: string;
  has_answer_sheet?: boolean;
  paper_draft?: boolean;
  paper_state?: PaperGradingState['state'] | null;
  class_name?: string | null;
  updated_at?: string | null;
  confirmed_count?: number;
  pending_count?: number;
  paper_blocker?: string | null;
  answer_sheet_summary?: {
    total_questions: number;
    option_count: number;
    html_url: string;
    pdf_url: string;
  };
}

export interface AnswerSheetConfig {
  total_questions: number;
  option_count: number;
  options: string[];
  coordinate_config: {
    canvas_width: number;
    canvas_height: number;
    id_regions: any[];
    id_digits: number;
    id_options: string[];
  };
  regions: Array<{
    question_number: number;
    type: string;
    score: number;
    correct_answer: string;
    options: string[];
    option_count: number;
    option_regions: any[];
  }>;
  html_url: string;
  pdf_url: string;
  png_url: string;
}

/** GraderFlow 答题卡配置（与标准 AnswerSheetConfig 兼容，增加 sheet_format 标识） */
export interface GraderflowSheetConfig extends AnswerSheetConfig {
  sheet_format: "graderflow";
}

// ========== 答题卡模板管理类型 ==========

/** 答题卡模板条目 */
export interface AnswerSheetTemplateItem {
  id: string;
  name: string;
  grade: string;
  description: string;
  question_count: number;
  total_score: number;
  choice_questions: ChoiceQuestionItem[];
  revision?: string;
  is_default: number;
  created_at: string;
  updated_at: string;
  archived_at?: string | null;
  paper_compatible?: boolean;
}

type TemplateResponse = Omit<AnswerSheetTemplateItem, 'id'> & { id: string | number; id_str?: string };

function templateItem({ id, id_str, ...item }: TemplateResponse): AnswerSheetTemplateItem {
  return { ...item, id: id_str ?? String(id) };
}

/** 选择题配置项 */
export interface ChoiceQuestionItem {
  question_number: number;
  score: number;
  type: string;
  option_count: number;
  options: string[];
  correct_answer?: string;
}

/** 创建/更新模板请求 */
export interface CreateTemplateRequest {
  name: string;
  choice_questions: ChoiceQuestionItem[];
  grade?: string;
  description?: string;
  create_only?: boolean;
  is_default?: number;
}

export interface ExamDetail {
  id: number;
  title: string;
  description?: string;
  paper_draft?: boolean;
  paper_draft_editable?: boolean;
  class_id: number;
  difficulty: number;
  duration_minutes: number;
  total_score: number;
  knowledge_points: string[];
  grade: string;
  status: string;
  questions: any[];
  submission_count: number;
  avg_score: number | null;
  created_at: string;
  updated_at?: string;
  published_at: string | null;
  partial_warning?: string;
  answer_sheet?: AnswerSheetConfig;
  question_count?: number;
}

export interface PaperDraft {
  id: string;
  title: string;
  description: string;
  class_id: string;
  template_id: string | null;
  template_revision: string | null;
  template_name: string | null;
  revision: string;
  paper_draft: boolean;
  created_revision?: string | null;
  layout_configured?: boolean;
  questions: { question_number: number; score: number; options: string[]; answer: string }[];
}

export interface ExamSource {
  id: string;
  name: string;
  size: number;
  kind: 'pdf' | 'word' | 'image';
  order: number;
}

export interface PaperDraftInput {
  title: string;
  description: string;
  class_id: string;
  revision?: string;
  template_id?: string;
  template_revision?: string;
  question_numbers?: number[];
  answers: Record<number, string>;
  finalize?: boolean;
  request_id?: string;
}

export interface SubmissionItem {
  id: number;
  student_id: number;
  student_name: string;
  score: number;
  total_score: number;
  status: string;
  submitted_at: string;
  teacher_reviewed: boolean;
}

/** 学生成绩列表项（扫描答题卡批卷用） */
export interface ExamResultItem {
  student_id: number | null;
  exam_number: string;
  student_name: string;
  class_name: string;
  score: number | null;
  grading_status: string;
  submission_id: number | null;
}

export interface ExamKnowledge {
  id: string;
  title: string;
  count: number;
  average: number | null;
  updated_at: string | null;
  date_from?: string | null;
  date_to?: string | null;
  questions: {
    number: number; stem: string; answer: string; option_text?: Record<string, string>;
    correct: number; distribution: Record<string, number>;
  }[];
}

export interface PaperGradingState {
  state: 'draft' | 'ready' | 'grading' | 'completed';
  revision: number;
  class_name: string | null;
  layout_configured: boolean;
  recognition_available: boolean;
  recognition_blocker?: string | null;
  capture_aspect_ratio?: number | null;
  exam_title?: string;
  confirmed: number;
  pending: number;
  expected: number | null;
  closed_at: string | null;
}

export interface FixedPaperReviewReceipt {
  submission_id: string;
  grade_version: number;
  score: number;
  max_score: number;
}

export interface FixedPaperReviewQuestion {
  number: number;
  marked: string;
  raw_marked?: string;
  invalid_mark?: boolean;
  answer: string;
  options: string[];
  score: number;
  max_score: number;
  needs_review: boolean;
}

export interface FixedPaperReview {
  id: string;
  status: 'pending_review' | 'confirmed' | 'replaced' | 'discarded' | 'withdrawn' | 'failed';
  exam_title: string;
  revision: string;
  exam_number: string;
  exam_number_length?: number | null;
  exam_number_cells?: {
    position: number;
    state: 'read' | 'empty' | 'ambiguous' | 'unavailable';
    digit?: string | null;
  }[] | null;
  exam_number_overflow?: boolean;
  identity_conflict?: string | null;
  student_name: string | null;
  class_required: boolean;
  class_id: string | null;
  class_name: string | null;
  has_photo: boolean;
  score: number;
  max_score: number;
  questions: FixedPaperReviewQuestion[];
  previous_grade: { submission_id: string; grade_version: number; score: number | null; max_score: number | null; withdrawn?: boolean } | null;
  receipt: FixedPaperReviewReceipt | null;
  regrade_submission_id?: string | null;
  reason?: string | null;
  updated_at?: string | null;
}

export interface PendingFixedPaperReviews {
  total: number;
  items: { id: string; exam_number: string; recognized_count: number; reason?: string | null; updated_at: string | null }[];
}

export type GradingRecordStatus = 'confirmed' | 'review' | 'failed' | 'historical';

export interface GradingRecord {
  id: string;
  exam_number: string;
  student_name: string;
  score: number | null;
  max_score: number | null;
  status: GradingRecordStatus;
  source: 'manual' | 'scan' | 'online' | 'legacy_scan';
  updated_at: string | null;
  record_kind?: 'submission' | 'scan';
}

export interface GradingRecordDetail extends GradingRecord {
  withdrawable_grade_version?: number | null;
  title: string;
  has_photo: boolean;
  questions: { number: number; marked: string; invalid_mark?: boolean; raw: string | null; answer: string; score: number | null; max_score: number }[];
  history: { id: string; action: string; created_at: string | null; old_score: number | null; new_score: number | null; reason?: string | null }[];
}

export interface MobileGradeSession {
  path: string;
  expires_at: string;
  expires_in_seconds: number;
}

/** 学生答卷详情（含逐题结果和错题） */
export interface StudentExamDetail {
  exam_id: number;
  exam_title: string;
  student_id: number;
  student_name: string;
  exam_number: string;
  score: number;
  max_score: number;
  grading_status: string;
  submitted_at: string | null;
  answers: Array<{
    question_number: number;
    student_answer: string;
    correct_answer: string;
    is_correct: boolean | null;
    score: number | null;
    max_score: number;
    confidence: number;
  }>;
  wrong_questions: Array<{
    question_number: number;
    student_answer: string;
    correct_answer: string;
    is_correct: boolean;
    score: number | null;
  }>;
}

export interface ExamStatistics {
  exam_id: number;
  title: string;
  total_submissions: number;
  avg_score: number;
  max_score: number;
  min_score: number;
  distribution: {
    excellent: number; // >= 90%
    good: number;      // >= 75%
    pass: number;      // >= 60%
    fail: number;      // < 60%
  };
  question_stats: {
    question_index: number;
    avg_score: number;
    full_score: number;
  }[];
}

// ========== PPT 相关类型 ==========

export interface PPTListItem {
  id: number;
  title: string;
  lesson_type: string;
  lesson_type_name: string;
  subject: string;
  grade: string;
  slide_count: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface PPTDetail {
  id: number;
  teacher_id: number;
  class_id: number | null;
  title: string;
  lesson_type: string;
  lesson_type_name: string;
  subject: string;
  grade: string;
  outline: any[];
  pages_json: any[];
  html_content?: string;
  theme_name: string;
  version: number;
  thumbnail_url: string;
  slide_count: number;
  interaction_config: any;
  status: string;
  created_at: string;
  updated_at: string;
}

// ========== 主题管理相关类型 ==========
export interface ThemeItem {
  id: number;
  name: string;
  display_name: string;
  description: string;
  preview_color: string;
  preview_url: string;
  sort_order: number;
  is_builtin: boolean;
}

export interface ThemeDetail extends ThemeItem {
  css_variables: string;
  css_content: string;
}

// ========== 版本历史相关类型 ==========
export interface PptVersionItem {
  id: number;
  ppt_id: number;
  version: number;
  theme_name: string;
  change_summary: string;
  created_at: string;
}

export interface PptVersionDetail extends PptVersionItem {
  html_content: string;
  pages_json: any[];
}

// ========== PPT 导出 ==========
export interface PptExportOut {
  id: number;
  title: string;
  html_content: string;
  theme_name: string;
  slide_count: number;
}

export interface ClassroomSession {
  id: number;
  ppt_id: number;
  title: string;
  status: string;
  current_page: number;
  student_count: number;
  interaction_data: any;
  started_at: string;
  ended_at: string | null;
}

export interface ClassroomReport {
  session: ClassroomSession;
  interaction_summary: {
    total_votes: number;
    total_quizzes: number;
    total_danmaku: number;
    total_questions: number;
    total_page_flips: number;
    quiz_accuracy_summary: { total: number; correct: number; accuracy: number };
  };
  page_stats: any[];
}

// ========== AI 查询 ==========

export interface AIQueryRequest {
  class_id: string | number;
  question: string;
}

export interface AIQueryResponse {
  answer: string;
  context_summary: any;
}

// ========== 文档管理相关类型 ==========

export interface DocumentOut {
  id: number;
  filename: string;
  file_type: string;      // pdf / word / ppt / txt / image
  file_size: number;
  storage_key: string;
  parse_status: number;   // 0=待处理 1=解析中 2=已完成 3=失败
  vector_status: number;
  doc_category: string;
  stage_category: string;
  doc_tags: string;
  created_at: string;
}

export const DOC_CATEGORY_NAMES: Record<string, string> = {
  exam: '试卷',
  teaching_plan: '教案',
  courseware: '课件/PPT',
  textbook: '教材',
  reference: '参考资料',
  other: '其他',
};

export const STAGE_CATEGORY_NAMES: Record<string, string> = {
  preschool: '启蒙',
  primary: '小学',
  junior: '初中',
  senior: '高中',
  college: '四六级',
  other: '其他',
};

export const PARSE_STATUS_NAMES: Record<number, string> = {
  0: '待处理',
  1: '解析中',
  2: '已完成',
  3: '失败',
};

export interface StepProgress {
  label: string;
  percent: number;
  status: string;   // pending | running | done | error
  message: string;
  current?: number;
  total?: number;
}

// ========== 异步上传 Job 进度类型 ==========
export interface UploadJobStep {
  label: string;
  percent: number;
  status: string;   // pending | running | done | error
  message: string;
}

export interface UploadJobData {
  job_id: string;
  doc_id: number;
  status: string;       // pending | processing | done | error
  percent: number;
  steps: Record<string, UploadJobStep>;
  error: string | null;
  created_at: number;
}

export const JOB_STEP_LABELS: Record<string, string> = {
  upload: '文档上传',
  cleanup: '清理旧版本',
  parse: '解析与分块',
  chunk: '父级分块入库',
  embed: '向量化入库',
};

export const PARSE_STATUS_COLORS: Record<number, string> = {
  0: '#999',
  1: '#1976d2',
  2: '#2d7d46',
  3: '#e53935',
};

export const VECTOR_STATUS_NAMES: Record<number, string> = {
  0: '未入库',
  1: '入库中',
  2: '已入库',
  3: '入库失败',
};

export const VECTOR_STATUS_COLORS: Record<number, string> = {
  0: '#999',
  1: '#1976d2',
  2: '#2d7d46',
  3: '#e53935',
};

// 获取响应体中的数据
function extractData<T>(res: { data: { data: T } }): T {
  return res.data.data;
}

// ========== 题库管理相关类型 ==========

export interface QuestionBankItem {
  id: number;
  type: number;
  stage: number;
  difficulty: number;
  content: Record<string, any>;
  source: string;
  is_active: number;
  created_at: string;
}

export interface QuestionBankStats {
  total: number;
  by_type: { type_id: number; type_name: string; count: number }[];
  by_category: { category: string; name: string; count: number }[];
}

// ========== 题库管理 API ==========

export const questionBankApi = {
  /** 获取各题型统计 */
  getStats: (stage?: number) =>
    client.get('/question-bank/stats', { params: { stage: stage || 0 } }).then(extractData<QuestionBankStats>),

  /** 获取题库列表 */
  list: (params?: {
    page?: number;
    page_size?: number;
    type_id?: number;
    stage?: number;
    difficulty?: number;
    keyword?: string;
  }) =>
    client.get('/question-bank/list', { params }).then(extractData<{
      items: QuestionBankItem[];
      total: number;
      page: number;
      page_size: number;
      total_pages: number;
    }>),

  /** 获取题目详情 */
  get: (questionId: number) =>
    client.get(`/question-bank/${questionId}`).then(extractData<QuestionBankItem>),

  /** 删除题目 */
  delete: (questionId: number) =>
    client.delete(`/question-bank/${questionId}`).then(extractData<{ id: number; deleted: boolean }>),

  /** AI 批量生成题目 */
  aiGenerate: (data: {
    qtype: string;
    stage?: number;
    count?: number;
    difficulty?: string;
  }) => client.post('/question-bank/ai-generate', data).then(extractData<{
    qtype: string;
    requested_count: number;
    generated_count: number;
    results: { index: number; id: number | null; title?: string; error?: string }[];
  }>),
};

export const teacherApi = {
  // 班级管理
  createClass: (data: { name: string; description?: string; stage?: number }) =>
    client.post('/teacher/classes', data).then(extractData<ClassData>),

  listClasses: () =>
    client.get('/teacher/classes').then(extractData<ClassData[]>),

  getClass: (classId: string | number) =>
    client.get(`/teacher/classes/${classId}`).then(extractData<ClassData>),

  updateClass: (classId: string | number, data: Partial<ClassData>) =>
    client.put(`/teacher/classes/${classId}`, data).then(extractData<ClassData>),

  regenerateInviteCode: (classId: string | number) =>
    client.post(`/teacher/classes/${classId}/invite-code`).then(extractData<{ invite_code: string }>),

  deleteClass: (classId: string | number) =>
    client.delete(`/teacher/classes/${classId}`).then(extractData<{ message: string }>),

  // 学生管理
  listStudents: (classId: string | number) =>
    client.get(`/teacher/classes/${classId}/students`).then(extractData<StudentData[]>),

  removeStudent: (classId: string | number, studentId: number) =>
    client.delete(`/teacher/classes/${classId}/students/${studentId}`),

  // 原生 fetch 由浏览器为 FormData 设置 multipart boundary。
  uploadStudentExcel: async (classId: string | number, formData: FormData) => {
    const url = `${getBaseURL()}/teacher/classes/${classId}/students/upload-excel`;
    const res = await authenticatedFetch(url, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error((err as any).detail || '上传失败');
    }
    const json = await res.json();
    return json.data as StudentInfoUploadResult;
  },

  listStudentInfo: (classId: string | number, signal?: AbortSignal) =>
    client.get(`/teacher/classes/${classId}/student-info`, { signal }).then(extractData<StudentInfoItem[]>),

  deleteStudentInfo: (classId: string | number) =>
    client.delete(`/teacher/classes/${classId}/student-info`),

  // 学生考试错题(OCR批卷)
  getStudentExamMistakes: (classId: string | number, examNumber: string) =>
    client.get(`/teacher/classes/${classId}/student-info/${encodeURIComponent(examNumber)}/exam-mistakes`)
      .then(extractData<StudentExamMistakesOut>),

  // 数据看板
  getClassDashboard: (classId: string | number) =>
    client.get(`/teacher/classes/${classId}/dashboard`).then(extractData<ClassDashboardData>),

  getStudentDetail: (classId: string | number, studentId: string | number) =>
    client.get(`/teacher/classes/${classId}/students/${studentId}`).then(extractData<StudentDetailData>),

  // ========== PPT 管理 ==========

  ppt: {
    getLessonTypes: () =>
      client.get('/teacher/ppt/lesson-types').then(extractData<{ value: string; label: string }[]>),

    generate: (data: {
      title: string;
      lesson_type: string;
      subject?: string;
      grade?: string;
      class_id?: string | number;
      slide_count?: number;
      knowledge_points?: string[];
      theme_name?: string;
      visual_style?: string;
    }) => client.post('/teacher/ppt/generate', data).then(extractData<any>),

    /** 教学助手：生成 PPT 大纲（章节+子主题） */
    generateOutline: (data: {
      title: string;
      lesson_type: string;
      subject?: string;
      grade?: string;
      knowledge_points?: string[];
    }) => client.post('/teacher/ppt/generate-outline', data).then(extractData<{
      sections: { title: string; subtopics: string[] }[];
    }>),

    /** 教学助手：基于大纲+主题生成完整 PPT */
    generateFromOutline: (data: {
      title: string;
      lesson_type: string;
      subject?: string;
      grade?: string;
      knowledge_points?: string[];
      sections: { title: string; subtopics: string[] }[];
      theme_name: string;
      visual_style?: string;
    }) => client.post('/teacher/ppt/generate-from-outline', data).then(extractData<any>),

    list: (params?: { status?: string; page?: number; page_size?: number }) =>
      client.get('/teacher/ppt/list', { params }).then(extractData<{ items: PPTListItem[]; total: number }>),

    get: (pptId: string | number) =>
      client.get(`/teacher/ppt/${pptId}`).then(extractData<PPTDetail>),

    update: (pptId: string | number, data: any) =>
      client.put(`/teacher/ppt/${pptId}`, data).then(extractData<any>),

    delete: (pptId: string | number) =>
      client.delete(`/teacher/ppt/${pptId}`).then(extractData<any>),

    publish: (pptId: string | number) =>
      client.post(`/teacher/ppt/${pptId}/publish`).then(extractData<any>),

    regeneratePage: (pptId: string | number, data: { page_index: number; outline_title: string; lesson_type: string; subject?: string; grade?: string }) =>
      client.post(`/teacher/ppt/${pptId}/regenerate-page`, data).then(extractData<any>),

    // 课堂管理
    startClassroom: (pptId: string | number) =>
      client.post('/teacher/ppt/classroom/start', { ppt_id: pptId }).then(extractData<ClassroomSession>),

    endClassroom: (sessionId: string | number) =>
      client.post(`/teacher/ppt/classroom/${sessionId}/end`).then(extractData<any>),

    getReport: (sessionId: string | number) =>
      client.get(`/teacher/ppt/classroom/${sessionId}/report`).then(extractData<ClassroomReport>),

    listSessions: (params?: { status?: string; page?: number; page_size?: number }) =>
      client.get('/teacher/ppt/classroom/list', { params }).then(extractData<{ items: ClassroomSession[]; total: number }>),

    // ========== 主题管理 ==========
    listThemes: (params?: { page?: number; page_size?: number }) =>
      client.get('/teacher/ppt/themes/list', { params }).then(extractData<{ items: ThemeItem[]; total: number }>),

    getTheme: (themeId: string | number) =>
      client.get(`/teacher/ppt/themes/${themeId}`).then(extractData<ThemeDetail>),

    createTheme: (data: {
      name: string; display_name: string; css_variables: string; css_content: string;
      description?: string; preview_color?: string;
    }) => client.post('/teacher/ppt/themes', data).then(extractData<any>),

    updateTheme: (themeId: string | number, data: {
      display_name?: string; css_variables?: string; css_content?: string;
      description?: string; preview_color?: string;
    }) => client.put(`/teacher/ppt/themes/${themeId}`, data).then(extractData<any>),

    deleteTheme: (themeId: string | number) =>
      client.delete(`/teacher/ppt/themes/${themeId}`).then(extractData<any>),

    // ========== 内容分析与风格推荐（Phase 3.1）==========
    /** 分析 PPT 页面数据的内容特征，推荐视觉风格和布局策略 */
    analyzeContent: (data: { pages: Record<string, unknown>[] }) =>
      client.post('/teacher/ppt/analyze-content', data).then(extractData<{
        profile: Record<string, unknown>;
        recommendedStyle: string;
        layoutStrategy: Record<string, string>;
        styleCandidates: { style: string; reason: string }[];
      }>),

    // ========== 版本历史 ==========
    listVersions: (pptId: string | number, params?: { page?: number; page_size?: number }) =>
      client.get(`/teacher/ppt/${pptId}/versions`, { params }).then(extractData<{ items: PptVersionItem[]; total: number }>),

    getVersion: (pptId: string | number, versionId: string | number) =>
      client.get(`/teacher/ppt/${pptId}/versions/${versionId}`).then(extractData<PptVersionDetail>),

    // ========== PPT 导出 ==========
    export: (pptId: string | number) =>
      client.get(`/teacher/ppt/${pptId}/export`).then(extractData<PptExportOut>),



    // ========== 可视化编辑持久化 ==========
    /** 保存可视化编辑（文字/位置调整），注入 pages_json._visual_edits */
    saveVisualEdits: (pptId: string | number, data: { page_edits: Record<string, { tag: string; text?: string; x?: number; y?: number }[]> }) =>
      client.post(`/teacher/ppt/${pptId}/visual-edits`, data).then(extractData<PPTDetail>),

    // ========== 重设主题 ==========
    retheme: (pptId: string | number, themeName: string) =>
      client.post(`/teacher/ppt/${pptId}/retheme`, null, {
        params: { theme_name: themeName },
      }).then(extractData<PPTDetail>),

    // ===== PPT 幻灯片内嵌 TTS 音频 =====
    tts: (data: { text: string; voice?: string }) =>
      client.post('/teacher/ppt/tts', data).then(extractData<{ url: string }>),

    // ===== PPT 幻灯片插图生成 =====
    generateImage: (data: { prompt: string; style?: string }) =>
      client.post('/teacher/ppt/generate-image', data).then(extractData<{ url: string }>),

    // ========== 课堂互动 ==========
    createVote: (sessionId: string | number, data: { question: string; options: string[] }) =>
      client.post(`/teacher/ppt/classroom/${sessionId}/vote/create`, data).then(extractData<any>),

    closeVote: (sessionId: string | number, voteId: string) =>
      client.post(`/teacher/ppt/classroom/${sessionId}/vote/${voteId}/close`).then(extractData<any>),

    getVoteResults: (sessionId: string | number, voteId: string) =>
      client.get(`/teacher/ppt/classroom/${sessionId}/vote/${voteId}/results`).then(extractData<any>),

    createQuiz: (sessionId: string | number, data: { question: string; options: string[]; correct_answer: number }) =>
      client.post(`/teacher/ppt/classroom/${sessionId}/quiz/create`, data).then(extractData<any>),

    getQuizResults: (sessionId: string | number, quizId: string) =>
      client.get(`/teacher/ppt/classroom/${sessionId}/quiz/${quizId}/results`).then(extractData<any>),

    getDanmaku: (sessionId: string | number, params?: { since_id?: string; limit?: number }) =>
      client.get(`/teacher/ppt/classroom/${sessionId}/danmaku`, { params }).then(extractData<any>),

    sendDanmaku: (sessionId: string | number, data: { content: string; student_name?: string }) =>
      client.post(`/teacher/ppt/classroom/${sessionId}/danmaku`, data).then(extractData<any>),

    syncPage: (sessionId: string | number, pageIndex: number) =>
      client.post(`/teacher/ppt/classroom/${sessionId}/page-sync`, null, { params: { page_index: pageIndex } }).then(extractData<any>),

    pauseSession: (sessionId: string | number) =>
      client.post(`/teacher/ppt/classroom/${sessionId}/pause`).then(extractData<any>),

    resumeSession: (sessionId: string | number) =>
      client.post(`/teacher/ppt/classroom/${sessionId}/resume`).then(extractData<any>),

    // 幻灯片练习题答题记录（iframe postMessage → 后端记录）
    recordSlideAnswer: (sessionId: string | number, data: { page_index: number; question_index: number; selected: number; correct: boolean }) =>
      client.post(`/teacher/ppt/classroom/${sessionId}/slide-answer`, data).then(extractData<any>),

    // ========== SVG 在线编辑器 ==========

    /** 初始化编辑器：生成所有幻灯片 SVG 并加载到内存 */
    editorStart: (pptId: string | number) =>
      client.post(`/teacher/ppt/${pptId}/editor/start`).then(extractData<{
        ppt_id: number;
        title: string;
        slide_count: number;
        loaded_pages: number;
        message: string;
      }>),

    /** 获取指定页可编辑 SVG（含临时 ID 和可选图标内联） */
    getEditorSlide: (pptId: string | number, page: number, inlineIcon?: boolean) =>
      client.get(`/teacher/ppt/${pptId}/editor/slide/${page}`, {
        params: { inline_icon: inlineIcon ?? true },
      }).then(extractData<{
        page: number;
        svg: string;
        edit_depth: number;
        annotations: Record<string, string>;
        existing_annotations: { element_id: string; tag: string; annotation: string }[];
        icon_inline_warnings: { icon: string; reason: string }[];
        canvas_width?: number;
        canvas_height?: number;
      }>),

    /** 提交 SVG 元素编辑 */
    submitEdit: (pptId: string | number, page: number, data: {
      element_id: string;
      text?: string;
      attrs?: Record<string, string | null>;
      promote_tspan?: { x?: string; y?: string };
      changes?: { kind: string; key: string; old: string; new: string }[];
    }) =>
      client.post(`/teacher/ppt/${pptId}/editor/slide/${page}/edit`, data).then(extractData<{
        element_id: string;
        edit_depth: number;
        message: string;
      }>),

    /** 撤销最近一次编辑 */
    undoEdit: (pptId: string | number, page: number) =>
      client.post(`/teacher/ppt/${pptId}/editor/slide/${page}/undo`).then(extractData<{
        message: string;
        edit_depth: number;
      }>),

    /** 设置/更新 SVG 元素注解 */
    setAnnotation: (pptId: string | number, page: number, data: {
      element_id: string;
      annotation: string;
    }) =>
      client.post(`/teacher/ppt/${pptId}/editor/slide/${page}/annotate`, data).then(extractData<{
        element_id: string;
        annotation: string;
        annotations: Record<string, string>;
      }>),

    /** 删除 SVG 元素注解 */
    deleteAnnotation: (pptId: string | number, page: number, elementId: string) =>
      client.delete(`/teacher/ppt/${pptId}/editor/slide/${page}/annotate/${encodeURIComponent(elementId)}`).then(extractData<{
        element_id: string;
        annotations: Record<string, string>;
      }>),

    /** 保存所有编辑：应用编辑 → 重建 PPTX → 更新数据库 */
    saveAllEdits: (pptId: string | number) =>
      client.post(`/teacher/ppt/${pptId}/editor/save-all`).then(extractData<{
        status: string;
        files_modified: number[];
        message: string;
      }>),

    /** 查看编辑器当前状态（调试用） */
    getEditorState: (pptId: string | number) =>
      client.get(`/teacher/ppt/${pptId}/editor/state`).then(extractData<{
        active: boolean;
        svg_count?: number;
        pages?: Record<string, { edit_count: number; annotations: Record<string, string> }>;
        message?: string;
      }>),
  },

  // ========== 知识图谱 ==========

  knowledgeGraph: {
    // AI 生成知识图谱（第一阶段）
    generate: (data: {
      title: string;
      lesson_type: string;
      subject?: string;
      grade?: string;
      supplement?: string;
      expected_sections?: number;
      expected_nodes_per_section?: number;
    }) => client.post('/teacher/ppt/knowledge-graph/generate', data).then(extractData<any>),

    // SSE 流式生成（带进度推送）
    generateSSE: (data: {
      title: string;
      lesson_type: string;
      subject?: string;
      grade?: string;
      supplement?: string;
      expected_sections?: number;
      expected_nodes_per_section?: number;
    }): Promise<Response> => {
      return authenticatedFetch(`${getBaseURL()}/teacher/ppt/knowledge-graph/generate-sse`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });
    },

    // 获取图谱详情
    get: (kgId: string | number) =>
      client.get(`/teacher/ppt/knowledge-graph/${kgId}`).then(extractData<any>),

    // 保存修改（整树替换）
    update: (kgId: string | number, data: { content: any[]; title?: string }) =>
      client.put(`/teacher/ppt/knowledge-graph/${kgId}`, data).then(extractData<any>),

    // 确认锁定图谱
    confirm: (kgId: string | number) =>
      client.post(`/teacher/ppt/knowledge-graph/${kgId}/confirm`).then(extractData<any>),

    // 基于图谱生成 PPT（第二阶段）
    // 从知识图谱生成 PPT（含 Phase 3.3 spec_lock 设计规格锁定）
    generatePpt: (
      kgId: string | number, themeName?: string,
      visualStyle?: string, specLock?: Record<string, unknown>,
    ) =>
      client.post(`/teacher/ppt/knowledge-graph/${kgId}/generate-ppt`, null, {
        params: {
          theme_name: themeName || 'classic',
          visual_style: visualStyle || '',
          spec_lock: specLock ? JSON.stringify(specLock) : '',
        },
      }).then(extractData<any>),

    // 图谱列表
    list: (params?: { status?: string; page?: number; page_size?: number }) =>
      client.get('/teacher/ppt/knowledge-graph/list', { params }).then(extractData<any>),
  },

  // ========== AI 自然语言查询 ==========
  aiQuery: (data: AIQueryRequest) =>
    client.post('/teacher/ai-query', data).then(extractData<AIQueryResponse>),

  /** SSE 流式 AI 查询 */
  aiQueryStream: (data: AIQueryRequest, signal?: AbortSignal): Promise<Response> => {
    return authenticatedFetch(`${getBaseURL()}/teacher/ai-query/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
      signal,
    });
  },

  // ========== 试卷管理 ==========
  generateExam: (data: {
    class_id?: string | number;
    title: string;
    knowledge_points?: string[];
    question_types?: string[];
    question_type_counts?: Record<string, number>;
    difficulty?: number;
    question_count?: number;
    duration_minutes?: number;
    grade?: string;
    additional_references?: string;
  }) => client.post('/teacher/exam/generate', data).then(extractData<ExamDetail>),

  /** SSE 流式生成试卷，返回 fetch Response 供逐事件消费 */
  generateExamStream: (data: {
    class_id?: string | number;
    title: string;
    knowledge_points?: string[];
    question_types?: string[];
    question_type_counts?: Record<string, number>;
    difficulty?: number;
    question_count?: number;
    duration_minutes?: number;
    grade?: string;
    additional_references?: string;
  }): Promise<Response> => {
    return authenticatedFetch(`${getBaseURL()}/teacher/exam/generate-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
  },

  listExams: (params?: { class_id?: number; status?: string; page?: number; page_size?: number; grading_view?: boolean; search?: string; paper_status?: PaperGradingState['state'] }, signal?: AbortSignal) =>
    client.get('/teacher/exam/list', { params, signal }).then(extractData<{ items: ExamListItem[]; total: number }>),

  getExam: (examId: string | number, signal?: AbortSignal) =>
    client.get(`/teacher/exam/${examId}`, { signal }).then(extractData<ExamDetail>),

  getExamKnowledge: (examId: string, questionNumber?: number, signal?: AbortSignal, dates?: { date_from: string; date_to: string }) =>
    client.get(`/teacher/exam/${examId}/grading-knowledge`, {
      params: { question_number: questionNumber, ...dates }, signal,
    }).then(extractData<ExamKnowledge>),

  getPaperGradingState: (examId: string, signal: AbortSignal) =>
    client.get(`/teacher/exam/${examId}/paper-grading-state`, { signal }).then(extractData<PaperGradingState>),

  getFixedCardReference: (examId: string, signal: AbortSignal) =>
    client.get<Blob>(`/teacher/exam/${examId}/fixed-card/reference`, { signal, responseType: 'blob' })
      .then(result => result.status === 204 ? null : {
        image: result.data,
        version: String(result.headers['x-paper-layout-version'] ?? ''),
      }),

  setPaperGradingState: (examId: string, state: 'grading' | 'completed', revision: number) =>
    client.put(`/teacher/exam/${examId}/paper-grading-state`, { state, revision }).then(extractData<PaperGradingState>),

  recognizeFixedCard: (examId: string, image: Blob, requestId: string, signal: AbortSignal) => {
    const form = new FormData();
    form.append('image', image, image instanceof File ? image.name : 'capture.jpg');
    form.append('request_id', requestId);
    return client.post(`/teacher/exam/${examId}/fixed-scan`, form, {
      signal, headers: { 'Content-Type': 'multipart/form-data' },
    }).then(extractData<{ scan_id: string; state: 'review' | 'retake' | 'layout_mismatch' }>);
  },

  listFixedPaperReviews: (examId: string, page: number, signal: AbortSignal, status?: 'discarded' | 'failed') =>
    client.get(`/teacher/exam/${examId}/fixed-reviews`, { params: { page, status }, signal })
      .then(extractData<PendingFixedPaperReviews>),

  getFixedPaperReview: (examId: string, scanId: string, signal: AbortSignal) =>
    client.get(`/teacher/exam/${examId}/fixed-reviews/${scanId}`, { signal }).then(extractData<FixedPaperReview>),

  getFixedPaperReviewPhoto: (examId: string, scanId: string, signal: AbortSignal) =>
    client.get<Blob>(`/teacher/exam/${examId}/fixed-reviews/${scanId}/photo`, { signal, responseType: 'blob' })
      .then(result => result.data),

  updateFixedPaperReview: (examId: string, scanId: string, data: {
    revision: string; exam_number: string; answers?: Record<number, string>; invalid_answers?: Record<number, string[]>;
  }) => client.put(`/teacher/exam/${examId}/fixed-reviews/${scanId}`, data).then(extractData<FixedPaperReview>),

  discardFixedPaperReview: (examId: string, scanId: string, revision: string, reason: string) =>
    client.post(`/teacher/exam/${examId}/fixed-reviews/${scanId}/discard`, { revision, reason })
      .then(extractData<{ discarded: true }>),

  preparePaperRegrade: (examId: string, submissionId: string, gradeVersion: number, requestId: string) =>
    client.post(`/teacher/exam/${examId}/grading-records/${submissionId}/regrade`, {
      grade_version: gradeVersion, request_id: requestId,
    }).then(extractData<{ scan_id: string }>),

  withdrawPaperGrade: (examId: string, submissionId: string, gradeVersion: number, reason: string) =>
    client.post(`/teacher/exam/${examId}/grading-records/${submissionId}/withdraw`, { grade_version: gradeVersion, reason })
      .then(extractData<{ grade_version: number }>),

  confirmFixedPaperReview: (examId: string, scanId: string, revision: string, previous: FixedPaperReview['previous_grade']) =>
    client.post(`/teacher/exam/${examId}/fixed-reviews/${scanId}/confirm`, {
      revision, previous_submission_id: previous?.submission_id, previous_grade_version: previous?.grade_version,
    }).then(extractData<FixedPaperReviewReceipt>),

  getGradingRecords: (examId: string, params: { search: string; status?: GradingRecordStatus; page: number }, signal: AbortSignal) =>
    client.get(`/teacher/exam/${examId}/grading-records`, { params: { ...params, include_scans: true }, signal })
      .then(extractData<{ title: string; total: number; confirmed: number; pending: number; items: GradingRecord[] }>),

  getGradingRecord: (examId: string, submissionId: string, signal: AbortSignal) =>
    client.get(`/teacher/exam/${examId}/grading-records/${submissionId}`, { signal }).then(extractData<GradingRecordDetail>),

  getGradingRecordPhoto: (examId: string, submissionId: string, signal: AbortSignal) =>
    client.get<Blob>(`/teacher/exam/${examId}/grading-records/${submissionId}/photo`, { signal, responseType: 'blob' })
      .then(result => result.data),

  getPaperDraft: (examId: string, signal?: AbortSignal) =>
    client.get(`/teacher/exam/${examId}/paper-draft`, { signal }).then(extractData<PaperDraft>),

  copyPaperDraft: (examId: string, requestId: string) =>
    client.post(`/teacher/exam/${examId}/paper-copy`, { request_id: requestId }).then(extractData<PaperDraft>),

  listExamSources: (examId: string, signal?: AbortSignal) =>
    client.get(`/teacher/exam/${examId}/sources`, { signal }).then(extractData<ExamSource[]>),

  uploadExamSource: (examId: string, file: File) => {
    const body = new FormData();
    body.append('file', file);
    return client.post(`/teacher/exam/${examId}/sources`, body, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(extractData<ExamSource>);
  },

  removeExamSource: (examId: string, sourceId: string) =>
    client.delete(`/teacher/exam/${examId}/sources/${sourceId}`),

  downloadExamSource: (examId: string, sourceId: string, signal?: AbortSignal) =>
    client.get<Blob>(`/teacher/exam/${examId}/sources/${sourceId}`, { signal, responseType: 'blob' }).then(result => result.data),

  previewExamSource: (examId: string, sourceId: string, page: number, signal: AbortSignal) =>
    client.get<Blob>(`/teacher/exam/${examId}/sources/${sourceId}/preview`, { params: { page }, signal, responseType: 'blob' })
      .then(result => ({ blob: result.data, pages: Number(result.headers['x-page-count']) || 1 })),

  savePaperDraft: (data: PaperDraftInput, examId?: string) =>
    (examId ? client.put(`/teacher/exam/${examId}/paper-draft`, data) : client.post('/teacher/exam/paper-drafts', data))
      .then(extractData<PaperDraft>),

  updateExam: (examId: number, data: Partial<ExamDetail>) =>
    client.put(`/teacher/exam/${examId}`, data).then(extractData<{ exam_id: number; status: string }>),

  publishExam: (examId: number, data?: { class_id: string | number }) =>
    client.post(`/teacher/exam/${examId}/publish`, data).then(extractData<{ exam_id: number; status: string; answer_sheet?: AnswerSheetConfig | null }>),

  deleteExam: (examId: number) =>
    client.delete(`/teacher/exam/${examId}`).then(extractData<{ message: string }>),

  /** 获取答题卡配置 */
  getAnswerSheetConfig: (examId: number) =>
    client.get(`/teacher/exam/${examId}/answer-sheet-template`).then(extractData<AnswerSheetConfig>),

  // ========== 答题卡模板管理 ==========

  /** 获取模板列表（支持按年级过滤） */
  listAnswerSheetTemplates: ({ grade, paperOnly }: { grade?: string; paperOnly?: boolean } = {}) =>
    client.get('/teacher/exam/templates/list', { params: { grade, paper_only: paperOnly } })
      .then(extractData<TemplateResponse[]>).then(items => items.map(templateItem)),

  /** 获取单个模板详情 */
  getAnswerSheetTemplate: (templateId: string | number) =>
    client.get(`/teacher/exam/answer-sheet-templates/${templateId}`)
      .then(extractData<TemplateResponse>).then(templateItem),

  /** 创建或更新答题卡模板 */
  createAnswerSheetTemplate: (data: CreateTemplateRequest) =>
    client.post('/teacher/exam/answer-sheet-template', data)
      .then(extractData<TemplateResponse>).then(templateItem),

  updateAnswerSheetTemplate: (templateId: string, data: CreateTemplateRequest & { revision: string }) =>
    client.put(`/teacher/exam/answer-sheet-templates/${templateId}`, data)
      .then(extractData<TemplateResponse>).then(templateItem),

  /** 停用答题卡模板 */
  archiveAnswerSheetTemplate: (templateId: string) =>
    client.delete(`/teacher/exam/answer-sheet-templates/${templateId}`)
      .then(extractData<{ archived: boolean }>),

  /** 从选择题JSON生成答题卡HTML */
  answerSheetFromJson: (data: { title: string; choice_questions: any[]; page_size?: string }) =>
    client.post('/teacher/exam/answer-sheet-from-json', data)
      .then(extractData<{ html: string; title: string }>),

  /** 下载答题卡PDF（返回 Blob 以支持带认证下载） */
  downloadAnswerSheetPdf: (examId: number) =>
    client.get(`/teacher/exam/${examId}/answer-sheet-pdf`, {
      responseType: 'blob',
    }).then(res => res.data as Blob),

  /** 重新生成答题卡（刷新HTML/坐标配置） */
  regenerateAnswerSheet: (examId: number) =>
    client.post(`/teacher/exam/${examId}/regenerate-answer-sheet`)
      .then(extractData<AnswerSheetConfig>),

  /** 从选择题JSON生成答题卡PDF（模板页下载PDF） */
  downloadAnswerSheetFromJsonPdf: (data: { title: string; choice_questions: any[]; page_size?: string }) =>
    client.post('/teacher/exam/answer-sheet-from-json/pdf', data, {
      responseType: 'blob',
    }).then(res => res.data as Blob),

  // ========== GraderFlow 答题卡（4列矩形填涂框，B模式扫描） ==========

  /** 获取 GraderFlow 答题卡配置 */
  getGraderflowSheetConfig: (examId: number) =>
    client.get(`/teacher/exam/${examId}/graderflow-sheet-template`).then(extractData<GraderflowSheetConfig>),

  /** 下载 GraderFlow 答题卡 PDF（返回 Blob 以支持带认证下载） */
  downloadGraderflowSheetPdf: (examId: number) =>
    client.get(`/teacher/exam/${examId}/graderflow-sheet-pdf`, {
      responseType: 'blob',
    }).then(res => res.data as Blob),

  /** 重新生成 GraderFlow 答题卡（刷新HTML/坐标配置） */
  regenerateGraderflowSheet: (examId: number) =>
    client.post(`/teacher/exam/${examId}/regenerate-graderflow-sheet`)
      .then(extractData<GraderflowSheetConfig>),

  // ========== 批卷 ==========
  gradeSubmission: (data: { exam_id: number; answers: any[] }) =>
    client.post('/teacher/exam/grade', data).then(extractData<any>),

  /** 手动批卷：获取试卷批卷信息（题目/选项列表，不含答案） */
  getExamGradingInfo: (examId: string | number) =>
    client.get(`/teacher/exam/${examId}/grading-info`).then(extractData<{
      exam_id: number;
      title: string;
      class_id: number;
      total_questions: number;
      total_score: number;
      questions: { question_number: number; options: string[]; option_count: number }[];
    }>),

  manualGrade: (examId: string | number, formData: FormData) =>
    client.post(`/teacher/exam/${examId}/manual-grade`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(extractData<ManualGradeResult>),

  getSubmissions: (examId: number, params?: { page?: number; page_size?: number }) =>
    client.get(`/teacher/exam/${examId}/submissions`, { params }).then(extractData<{ items: SubmissionItem[]; total: number }>),

  /** 获取班级学生考试成绩列表（扫描答题卡批卷专用） */
  getExamResults: (examId: string | number, classId: string | number) =>
    client.get(`/teacher/exam/${examId}/results`, { params: { class_id: classId } }).then(extractData<{ items: ExamResultItem[]; total: number; exam_title: string; class_name: string }>),

  /** 创建仅限当前试卷、短时有效的手机扫码批卷会话 */
  createMobileGradeSession: (examId: string | number, classId?: string | number) =>
    client.post(`/teacher/exam/${examId}/mobile-grade-session`, {
      class_id: classId ? Number(classId) : 0,
    }).then(extractData<MobileGradeSession>),

  /** 获取学生答卷详情（含逐题结果和错题） */
  getStudentExamDetail: (examId: string | number, studentId: number) =>
    client.get(`/teacher/exam/${examId}/student/${studentId}`).then(extractData<StudentExamDetail>),

  teacherReview: (examId: number, submissionId: number, data: { adjustments: any[] }) =>
    client.post(`/teacher/exam/${examId}/submissions/${submissionId}/review`, data).then(extractData<any>),

  // ========== 统计 ==========
  getExamStatistics: (examId: number) =>
    client.get(`/teacher/exam/${examId}/statistics`).then(extractData<ExamStatistics>),

  // ========== 文档管理 ==========

  documents: {
    /** 获取文档分类和学段选项 */
    getCategories: () =>
      client.get('/documents/categories').then(extractData<{
        doc_categories: { value: string; label: string }[];
        stage_categories: { value: string; label: string }[];
      }>),

    /** 文档列表 */
    list: (params?: {
      page?: number;
      page_size?: number;
      doc_category?: string;
      stage_category?: string;
    }) =>
      client.get('/documents/', { params }).then(extractData<{
        items: DocumentOut[];
        total: number;
        page: number;
        page_size: number;
      }>),

    /** 上传文档（自动后台解析并向量化） */
    upload: (formData: FormData) =>
      client.post('/documents/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }).then(extractData<DocumentOut>),

    /** 异步上传文档 — 立即返回 job_id，前端轮询 jobs/{job_id} 获取进度 */
    uploadAsync: (formData: FormData) =>
      client.post('/documents/upload-async', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }).then(extractData<{ job_id: string; doc_id: number; status: string; message: string }>),

    /** 获取异步上传 Job 的实时进度 */
    getJobProgress: (jobId: string) =>
      client.get(`/documents/jobs/${encodeURIComponent(jobId)}`).then(extractData<UploadJobData>),

    /** 更新文档分类/学段/标签（后端为 Form 参数，需用 URLSearchParams） */
    update: (docId: number, data: {
      doc_category?: string;
      stage_category?: string;
      doc_tags?: string;
    }) => {
      const params = new URLSearchParams();
      Object.entries(data).forEach(([k, v]) => { if (v !== undefined) params.append(k, v); });
      return client.put(`/documents/${docId}`, params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      }).then(extractData<DocumentOut>);
    },

    /** 重新处理文档（重新解析并向量化） */
    reprocess: (docId: number) =>
      client.post(`/documents/${docId}/reprocess`).then(extractData<{ doc_id: number; status: string; message: string }>),

    /** 获取文档处理进度 */
    getProgress: (docId: number) =>
      client.get(`/documents/${docId}/progress`).then(extractData<{
        status: string;
        percent: number;
        steps: Record<string, StepProgress>;
        message?: string;
      }>),

    /** 删除文档 */
    delete: (docId: number) =>
      client.delete(`/documents/${docId}`).then(extractData<{ message: string }>),

    /** 获取文档提取文本内容（用于文本预览） */
    getTextContent: (docId: string | number): Promise<{ text: string; chars: number; filename: string; hint?: string } | null> => {
      if (!localStorage.getItem('token')) return Promise.resolve(null);
      return authenticatedFetch(`${getBaseURL()}/documents/${docId}/text-content`)
        .then(res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .catch(() => null);
    },
  },
};
