// 应用根组件 — 路由配置（默认进入教学页，未登录也可浏览）
// 使用 lazy 懒加载页面组件，降低首屏 JS 体积
import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Layout from './components/Layout';
import AdminLayout from './components/AdminLayout';
import FloatingAssistant from './components/FloatingAssistant';

const Login = lazy(() => import('./pages/Login'));
const ClassManage = lazy(() => import('./pages/ClassManage'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const StudentDetail = lazy(() => import('./pages/StudentDetail'));
const ExamList = lazy(() => import('./pages/ExamList'));
const ExamCreate = lazy(() => import('./pages/ExamCreate'));
const ExamGrade = lazy(() => import('./pages/ExamGrade'));
const ManualGrade = lazy(() => import('./pages/ManualGrade'));
const SchoolAdmin = lazy(() => import('./pages/SchoolAdmin'));
const PPTList = lazy(() => import('./pages/PPTEditor'));
const PPTCreate = lazy(() => import('./pages/PPTEditor/Create'));
const PPTEdit = lazy(() => import('./pages/PPTEditor/Edit'));
const PPTPresenter = lazy(() => import('./pages/PPTEditor/Presenter'));
const PPTReport = lazy(() => import('./pages/PPTEditor/Report'));
const PptxGenerator = lazy(() => import('./pages/PPTEditor/PptxGenerator'));
const PermissionManage = lazy(() => import('./pages/PermissionManage'));
const AuditLog = lazy(() => import('./pages/AuditLog'));
const ReportPreview = lazy(() => import('./pages/ReportPreview'));
const DocumentList = lazy(() => import('./pages/DocumentList'));
const DocumentView = lazy(() => import('./pages/DocumentView'));
const SystemStatus = lazy(() => import('./pages/SystemStatus'));
const Teaching = lazy(() => import('./pages/Teaching'));
const TeachingTasks = lazy(() => import('./pages/TeachingTasks'));
const SceneDialogue = lazy(() => import('./pages/Teaching/scene-dialogue'));
const QuestionBank = lazy(() => import('./pages/QuestionBank'));
const TeachingAssistant = lazy(() => import('./pages/TeachingAssistant'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const ProductIntro = lazy(() => import('./pages/ProductIntro'));
const AdminDashboard = lazy(() => import('./pages/AdminDashboard'));
const AccountManagement = lazy(() => import('./pages/AccountManagement'));
const FeeManagement = lazy(() => import('./pages/FeeManagement'));
const ApiKeyManagement = lazy(() => import('./pages/ApiKeyManagement'));
const UsageStatistics = lazy(() => import('./pages/UsageStatistics'));
const ExamKnowledge = lazy(() => import('./shared/exams/ExamKnowledge').then(module => ({ default: module.ExamKnowledge })));
const PaperDraftPage = lazy(() => import('./pages/ExamList/PaperDraftPage'));
const PaperGradingPage = lazy(() => import('./pages/ExamList/PaperGradingPage'));

function ExamKnowledgePage() {
  const { state } = useLocation();
  const back = typeof state?.from === 'string' && /^\/teaching-assistant(?:\/\d+)?(?:\?|$)/.test(state.from)
    ? state.from : '/teaching-assistant';
  return <ExamKnowledge back={back} />;
}

function App() {
  const routeFallback = (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: '#888' }}>
      loading...
    </div>
  );

  return (
    <Suspense fallback={routeFallback}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/product-intro" element={<ProductIntro />} />
        {/* 授课页路由：全屏沉浸式，不使用 Layout 布局 */}
        <Route path="/ppt/present/:sessionId" element={<PPTPresenter />} />
        {/* 教师端路由：无需登录也可访问，未登录时操作 API 会提示登录 */}
        <Route element={<Layout />}>
          <Route path="/classes" element={<ClassManage />} />
          <Route path="/teaching-tasks" element={<TeachingTasks />} />
          <Route path="/classes/:classId/dashboard" element={<Dashboard />} />
          <Route path="/classes/:classId/students/:studentId" element={<StudentDetail />} />
          <Route path="/exams" element={<ExamList />} />
          <Route path="/exams/create" element={<ExamCreate />} />
          <Route path="/exams/paper-drafts/new" element={<PaperDraftPage />} />
          <Route path="/exams/paper-drafts/:examId" element={<PaperDraftPage />} />
          <Route path="/exams/:examId/records" element={<PaperGradingPage view="records" />} />
          <Route path="/exams/:examId/rules" element={<PaperGradingPage view="rules" />} />
          <Route path="/exams/:examId/records/:recordId" element={<PaperGradingPage view="score" />} />
          <Route path="/exams/:examId/records/:recordId/history" element={<PaperGradingPage view="history" />} />
          <Route path="/exams/:examId/records/:recordId/photo" element={<PaperGradingPage view="photo" />} />
          <Route path="/exams/:examId/fixed-card" element={<PaperGradingPage view="guide" />} />
          <Route path="/exams/:examId/scan" element={<PaperGradingPage view="capture" />} />
          <Route path="/exams/:examId/scan/reviews" element={<PaperGradingPage view="pending" />} />
          <Route path="/exams/:examId/scan/reviews/:scanId" element={<PaperGradingPage view="review" />} />
          <Route path="/exams/:examId/scan/reviews/:scanId/photo" element={<PaperGradingPage view="photo" />} />
          <Route path="/exams/grade" element={<ExamGrade />} />
          <Route path="/exams/manual-grade" element={<ManualGrade />} />
          <Route path="/exams/knowledge/:examId/:questionNumber?" element={<ExamKnowledgePage />} />
          <Route path="/permissions" element={<PermissionManage />} />
          <Route path="/audit-logs" element={<AuditLog />} />
          <Route path="/reports" element={<ReportPreview />} />
          <Route path="/school-admin" element={<SchoolAdmin />} />
          <Route path="/documents" element={<DocumentList />} />
          <Route path="/documents/view/:id" element={<DocumentView />} />
          <Route path="/ppt" element={<PPTList />} />
          <Route path="/ppt/create" element={<PPTCreate />} />
          <Route path="/ppt/edit/:id" element={<PPTEdit />} />
          <Route path="/ppt/report/:sessionId" element={<PPTReport />} />
          <Route path="/ppt-editor" element={<PptxGenerator />} />
          <Route path="/teaching" element={<Teaching />} />
          <Route path="/teaching/scene-dialogue" element={<SceneDialogue />} />
          <Route path="/question-bank" element={<QuestionBank />} />
          <Route path="/system/status" element={<SystemStatus />} />
          <Route path="/teaching-assistant" element={<TeachingAssistant />} />
          <Route path="/teaching-assistant/:sessionId" element={<TeachingAssistant />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Route>
        {/* 管理者端路由 */}
        <Route element={<AdminLayout />}>
          <Route path="/admin/dashboard" element={<AdminDashboard />} />
          <Route path="/admin/users" element={<AccountManagement />} />
          <Route path="/admin/fees" element={<FeeManagement />} />
          <Route path="/admin/apikeys" element={<ApiKeyManagement />} />
          <Route path="/admin/usage" element={<UsageStatistics />} />
        </Route>
        {/* 默认进入教学页 */}
        <Route path="/" element={<Navigate to="/teaching" replace />} />
        <Route path="*" element={<Navigate to="/teaching" replace />} />
      </Routes>
      <FloatingAssistant />
    </Suspense>
  );
}

export default App;
