// 批卷页 — 扫描答题卡批卷：学生成绩列表（按成绩降序）
import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { QRCodeCanvas } from 'qrcode.react';
import { teacherApi, ExamResultItem, MobileGradeSession, StudentExamDetail } from '../../api/teacher';
import { getBaseURL } from '../../api/client';
import {
  colors, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary,
} from '../../design-system';

const XS = 8;

export default function ExamGrade() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const examId = searchParams.get('examId') || '';
  const classId = searchParams.get('classId') || '';

  const [examTitle, setExamTitle] = useState('');
  const [className, setClassName] = useState('');
  const [results, setResults] = useState<ExamResultItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // ── 二维码扫码批卷弹窗 ──
  const [qrCodeModal, setQrCodeModal] = useState(false);
  const [qrSession, setQrSession] = useState<MobileGradeSession | null>(null);
  const [qrLoading, setQrLoading] = useState(false);
  const [qrError, setQrError] = useState('');
  const [qrSecondsLeft, setQrSecondsLeft] = useState(0);

  // ── 学生详情弹窗 ──
  const [detailModal, setDetailModal] = useState(false);
  const [detailData, setDetailData] = useState<StudentExamDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');

  useEffect(() => {
    if (examId === '' || classId === '') {
      setError('缺少 examId 或 classId 参数');
      setLoading(false);
      return;
    }
    loadResults();
  }, [examId, classId]);

  const loadResults = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await teacherApi.getExamResults(examId, classId);
      setExamTitle(res.exam_title || '');
      setClassName(res.class_name || '');
      setResults((res.items || []).sort((a, b) => {
        // 按成绩降序（未批改的排在最后）
        const sa = a.score ?? -1;
        const sb = b.score ?? -1;
        return sb - sa;
      }));
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || '加载成绩失败');
    } finally {
      setLoading(false);
    }
  };

  // 查看学生答卷详情
  const openDetail = async (item: ExamResultItem) => {
    if (!item.student_id || item.grading_status === 'pending') return;
    setDetailModal(true);
    setDetailData(null);
    setDetailError('');
    setDetailLoading(true);
    try {
      const data = await teacherApi.getStudentExamDetail(examId, item.student_id);
      setDetailData(data);
    } catch (err: any) {
      setDetailError(err?.response?.data?.detail || err?.message || '加载答卷详情失败');
    } finally {
      setDetailLoading(false);
    }
  };
  const createQrSession = async () => {
    setQrLoading(true);
    setQrError('');
    try {
      const session = await teacherApi.createMobileGradeSession(examId, classId);
      setQrSession(session);
      setQrSecondsLeft(Math.max(0, Math.floor((new Date(session.expires_at).getTime() - Date.now()) / 1000)));
    } catch (err: any) {
      setQrSession(null);
      setQrError(err?.message || '生成二维码失败');
    } finally {
      setQrLoading(false);
    }
  };

  const openQrModal = () => {
    setQrCodeModal(true);
    void createQrSession();
  };

  const buildMobileGradeUrl = () => {
    if (!qrSession) return '';
    return new URL(`${getBaseURL()}${qrSession.path}`, window.location.origin).toString();
  };

  useEffect(() => {
    if (!qrCodeModal || !qrSession) return;
    const updateCountdown = () => {
      setQrSecondsLeft(Math.max(0, Math.floor((new Date(qrSession.expires_at).getTime() - Date.now()) / 1000)));
    };
    updateCountdown();
    const timer = window.setInterval(updateCountdown, 1000);
    return () => window.clearInterval(timer);
  }, [qrCodeModal, qrSession]);

  useEffect(() => {
    if (!qrCodeModal || !examId || !classId) return;

    const refreshResultsQuietly = async () => {
      try {
        const res = await teacherApi.getExamResults(examId, classId);
        setExamTitle(res.exam_title || '');
        setClassName(res.class_name || '');
        setResults((res.items || []).sort((a, b) => (b.score ?? -1) - (a.score ?? -1)));
      } catch {
        // 扫码批改期间的后台刷新失败不打断二维码和当前列表；下一轮会自动重试。
      }
    };

    const timer = window.setInterval(() => void refreshResultsQuietly(), 5000);
    return () => window.clearInterval(timer);
  }, [qrCodeModal, examId, classId]);

  const qrExpired = qrSecondsLeft <= 0;
  const qrCountdown = `${String(Math.floor(qrSecondsLeft / 60)).padStart(2, '0')}:${String(qrSecondsLeft % 60).padStart(2, '0')}`;


  // 批改情况标签
  const renderGradingBadge = (status: string, score: number | null) => {
    const isGraded = status !== 'pending' && score !== null;
    const modeLabel = status === 'omr_done' ? ' (OMR)'
      : status === 'multimodal_done' ? ' (AI)'
      : status === 'ai_done' ? ' (AI)'
      : status === 'manual_done' ? ' (手动)' : '';
    return (
      <span style={{
        display: 'inline-block', padding: '2px 12px', borderRadius: radius.pill,
        fontSize: 12, fontWeight: 500,
        background: isGraded ? colors['block-lime'] : colors['block-cream'],
        color: isGraded ? colors.success : colors.warning,
      }}>
        {isGraded ? `已批改${modeLabel}` : '未批改'}
      </span>
    );
  };

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      {/* 顶部导航 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: space.xl }}>
        <button onClick={() => navigate('/exams')}
          style={{
            background: 'none', border: 'none', fontSize: 28, cursor: 'pointer',
            color: colors['text-secondary'], padding: 0, lineHeight: 1,
            display: 'flex', alignItems: 'center',
          }}
          title="返回试卷列表"
        >‹</button>
        <h1 style={{
          margin: 0, fontSize: typography['display-lg'].fontSize,
          fontWeight: typography['display-lg'].fontWeight,
          letterSpacing: typography['display-lg'].letterSpacing,
          color: colors['text-primary'],
        }}>批卷</h1>
      </div>

      {/* 试卷信息 */}
      <div style={{ ...cardStyle, marginBottom: space.xl, background: colors['block-lilac'] }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h3 style={{
              margin: `0 0 ${space.xs}px`, fontSize: typography.headline.fontSize,
              fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
            }}>{examTitle || '加载中...'}</h3>
            <p style={{ margin: 0, fontSize: 14, color: colors['text-secondary'] }}>
              班级：{className || '加载中...'}　|　考号匹配批改
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            onClick={openQrModal}
            style={{
              ...btnSmall,
              background: colors.canvas,
              color: colors.info,
              border: `1px solid ${colors.info}40`,
              display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={colors.info} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="7" height="7" rx="1" />
              <rect x="14" y="3" width="7" height="7" rx="1" />
              <rect x="3" y="14" width="7" height="7" rx="1" />
              <line x1="14" y1="14" x2="14" y2="14" strokeWidth="3" />
              <line x1="18" y1="14" x2="21" y2="14" />
              <line x1="14" y1="18" x2="21" y2="18" />
              <line x1="14" y1="21" x2="14" y2="21" strokeWidth="3" />
              <line x1="18" y1="21" x2="21" y2="21" />
            </svg>
            手机扫码批卷
          </button>
          </div>
        </div>
      </div>

      {/* 学生成绩列表 */}
      <div style={cardStyle}>
        <h3 style={{
          margin: `0 0 ${space.md}px`, fontSize: typography.headline.fontSize,
          fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
        }}>
          学生成绩
          <span style={{ fontSize: 13, fontWeight: 400, color: colors['text-tertiary'], marginLeft: 8 }}>
            ({results.length} 人)
          </span>
        </h3>

        {loading ? (
          <p style={{ color: colors['text-tertiary'], padding: 40, textAlign: 'center' }}>加载中...</p>
        ) : error ? (
          <div style={{ padding: 40, textAlign: 'center' }}>
            <p style={{ color: colors.danger, margin: 0 }}>❌ {error}</p>
            <button onClick={loadResults} style={{ ...btnSmall, marginTop: space.md }}>重试</button>
          </div>
        ) : results.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center' }}>
            <p style={{ color: colors['text-tertiary'], margin: 0 }}>该班级暂无学生信息</p>
            <p style={{ color: colors['text-tertiary'], fontSize: 13, marginTop: XS }}>
              请先在「班级管理」中导入学生花名册
            </p>
            <p style={{ color: colors['text-tertiary'], fontSize: 13, marginTop: XS }}>
              使用「手机扫码批卷」功能可拍照上传纸质答题卡进行批改
            </p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: typography['body-sm'].fontSize }}>
              <thead>
                <tr style={{
                  borderBottom: `1px solid ${colors.hairline}`,
                  color: colors['text-secondary'],
                  fontSize: typography.caption.fontSize,
                  fontWeight: 500, textTransform: 'uppercase',
                  letterSpacing: typography.eyebrow.letterSpacing,
                  textAlign: 'left',
                }}>
                  <th style={{ padding: `10px ${XS}px` }}>考号</th>
                  <th style={{ padding: `10px ${XS}px` }}>学生姓名</th>
                  <th style={{ padding: `10px ${XS}px` }}>班级</th>
                  <th style={{ padding: `10px ${XS}px` }}>分数</th>
                  <th style={{ padding: `10px ${XS}px` }}>批改情况</th>
                  <th style={{ padding: `10px ${XS}px`, textAlign: 'center' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {results.map((item, idx) => (
                  <tr key={item.exam_number || idx}
                    style={{
                      borderBottom: `1px solid ${colors['hairline-soft']}`,
                      background: (item.grading_status === 'pending' || !item.grading_status)
                        ? colors['block-cream'] + '30'
                        : 'transparent',
                    }}
                  >
                    <td style={{ padding: `10px ${XS}px`, fontWeight: 500, color: colors['text-primary'] }}>
                      {item.exam_number || '-'}
                    </td>
                    <td style={{ padding: `10px ${XS}px`, fontWeight: 500, color: colors['text-primary'] }}>
                      {item.student_name}
                    </td>
                    <td style={{ padding: `10px ${XS}px`, color: colors['text-secondary'] }}>
                      {item.class_name || '-'}
                    </td>
                    <td style={{ padding: `10px ${XS}px`, fontWeight: 600 }}>
                      {item.score !== null && item.score !== undefined ? (
                        <span style={{ color: item.score >= 60 ? colors.success : colors.danger }}>
                          {item.score}
                        </span>
                      ) : (
                        <span style={{ color: colors['text-tertiary'] }}>-</span>
                      )}
                    </td>
                    <td style={{ padding: `10px ${XS}px` }}>
                      {renderGradingBadge(item.grading_status, item.score)}
                    </td>
                    <td style={{ padding: `10px ${XS}px`, textAlign: 'center' }}>
                      {item.student_id && item.grading_status !== 'pending' && item.score !== null ? (
                        <button
                          onClick={() => openDetail(item)}
                          style={{
                            ...btnSmall,
                            background: 'transparent',
                            color: colors.success,
                            border: `1px solid ${colors.success}40`,
                            cursor: 'pointer',
                            fontSize: 12,
                            padding: '3px 10px',
                          }}
                        >
                          详情 ›
                        </button>
                      ) : (
                        <span style={{ color: colors['text-tertiary'], fontSize: 12 }}>-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── 手机扫码批卷二维码弹窗 ── */}
      {qrCodeModal && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: colors.overlay, display: 'flex', alignItems: 'center',
          justifyContent: 'center', zIndex: 1000,
        }} onClick={() => setQrCodeModal(false)}>
          <div style={{
            background: colors.canvas, borderRadius: radius.lg,
            padding: space.xl, width: 400, maxWidth: '90vw',
            textAlign: 'center', boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
          }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{
              margin: `0 0 ${space.sm}px`, color: colors['text-primary'],
              fontSize: typography.headline.fontSize,
            }}>
              手机扫码批卷
            </h3>
            <p style={{
              margin: `0 0 ${space.xs}px`, fontSize: 13, color: colors['text-secondary'],
              lineHeight: 1.5,
            }}>
              打开手机浏览器扫描下方二维码，进入批卷页面拍照上传答题卡
            </p>
            <p style={{
              margin: `0 0 ${space.md}px`, fontSize: 12, fontWeight: 500,
              color: colors.success, background: colors['block-lime'],
              display: 'inline-block', padding: '2px 10px', borderRadius: radius.pill,
            }}>
              OMR 答题卡扫描 · 限时会话
            </p>

            {/* 试卷名称 */}
            <p style={{ margin: `0 0 ${space.md}px`, fontWeight: 600, fontSize: 15, color: colors['text-primary'] }}>
              {examTitle || '加载中...'}
            </p>

            {/* QR Code */}
            {qrLoading ? (
              <div style={{ height: 274, display: 'grid', placeItems: 'center', color: colors['text-secondary'] }}>
                正在生成安全二维码…
              </div>
            ) : qrError ? (
              <div style={{ padding: space.lg, marginBottom: space.md, borderRadius: radius.md, background: '#fff1f0', color: colors.danger }}>
                <p style={{ margin: `0 0 ${space.sm}px` }}>{qrError}</p>
                <button onClick={() => void createQrSession()} style={btnSmall}>重新生成</button>
              </div>
            ) : qrSession ? (
              <>
                <div style={{
                  display: 'inline-block', padding: space.md, position: 'relative',
                  background: '#fff', borderRadius: radius.md,
                  border: `1px solid ${qrExpired ? colors.danger : colors.hairline}`,
                  marginBottom: space.sm,
                }}>
                  <QRCodeCanvas
                    value={buildMobileGradeUrl()}
                    size={240}
                    level="M"
                    bgColor="#fff"
                    fgColor={qrExpired ? '#9ca3af' : '#153f2b'}
                    includeMargin={false}
                  />
                  {qrExpired && (
                    <div style={{
                      position: 'absolute', inset: 0, display: 'grid', placeItems: 'center',
                      background: 'rgba(255,255,255,0.9)', borderRadius: radius.md,
                      color: colors.danger, fontWeight: 700,
                    }}>
                      二维码已过期
                    </div>
                  )}
                </div>
                <p aria-live="polite" style={{
                  margin: `0 0 ${space.md}px`, fontSize: 13,
                  color: qrExpired ? colors.danger : colors['text-secondary'],
                  fontVariantNumeric: 'tabular-nums',
                }}>
                  {qrExpired ? '请刷新二维码后重新扫码' : `剩余有效时间 ${qrCountdown}`}
                </p>
              </>
            ) : null}

            {/* 使用说明 */}
            <div style={{
              background: colors['block-lime'], borderRadius: radius.md,
              padding: space.sm, textAlign: 'left', marginBottom: space.md,
            }}>
              <p style={{ margin: 0, fontSize: 12, color: colors['text-secondary'], lineHeight: 1.6 }}>
                <strong style={{ color: colors['text-primary'] }}>使用步骤：</strong><br />
                1. 打印答题卡发给学生填写<br />
                2. 手机扫描上方二维码打开批卷页<br />
                3. 将整张答题卡四角放入取景框后拍照<br />
                4. 清晰度检查通过后自动识别并批改<br />
                5. 批改结果实时同步到此页面
              </p>
            </div>

            <div style={{ display: 'flex', justifyContent: 'center', gap: space.sm }}>
              <button onClick={() => void createQrSession()} disabled={qrLoading} style={btnSmall}>
                刷新二维码
              </button>
              <button onClick={() => setQrCodeModal(false)} style={btnSmallSecondary}>关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* ── 学生答卷详情弹窗 ── */}
      {detailModal && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: colors.overlay, display: 'flex', alignItems: 'center',
          justifyContent: 'center', zIndex: 1000,
        }} onClick={() => { setDetailModal(false); setDetailData(null); }}>
          <div style={{
            background: colors.canvas, borderRadius: radius.lg,
            padding: space.xl, width: 680, maxWidth: '92vw',
            maxHeight: '85vh', overflowY: 'auto',
            boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
          }} onClick={(e) => e.stopPropagation()}>
            {/* 标题 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.md }}>
              <h3 style={{ margin: 0, fontSize: typography.headline.fontSize, fontWeight: typography.headline.fontWeight, color: colors['text-primary'] }}>
                答卷详情
              </h3>
              <button onClick={() => { setDetailModal(false); setDetailData(null); }} style={{
                background: 'none', border: 'none', fontSize: 20, cursor: 'pointer',
                color: colors['text-tertiary'], padding: '0 4px',
              }}>✕</button>
            </div>

            {detailLoading ? (
              <p style={{ color: colors['text-tertiary'], padding: 40, textAlign: 'center' }}>加载中...</p>
            ) : detailError ? (
              <p style={{ color: colors.danger, padding: 40, textAlign: 'center' }}>❌ {detailError}</p>
            ) : detailData ? (
              <>
                {/* 学生信息 + 得分 */}
                <div style={{
                  background: colors['block-lilac'], borderRadius: radius.md,
                  padding: space.md, marginBottom: space.md,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                  <div>
                    <p style={{ margin: 0, fontWeight: 600, fontSize: 16, color: colors['text-primary'] }}>
                      {detailData.student_name}
                      <span style={{ fontSize: 12, fontWeight: 400, color: colors['text-secondary'], marginLeft: 8 }}>
                        考号 {detailData.exam_number || '-'}
                      </span>
                    </p>
                    <p style={{ margin: '4px 0 0', fontSize: 12, color: colors['text-secondary'] }}>
                      试卷：{detailData.exam_title}　|　
                      {detailData.grading_status === 'multimodal_done' ? '🤖 AI多模态批改' :
                       detailData.grading_status === 'omr_done' ? '⚙️ OMR批改' :
                       detailData.grading_status === 'manual_done' ? '✏️ 手动批改' :
                       detailData.grading_status === 'ai_done' ? '🤖 AI批改' : detailData.grading_status}
                    </p>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <span style={{
                      fontSize: 28, fontWeight: 700,
                      color: detailData.score >= detailData.max_score * 0.6 ? colors.success : colors.danger,
                    }}>
                      {detailData.score}
                    </span>
                    <span style={{ fontSize: 16, color: colors['text-secondary'], fontWeight: 500 }}>
                      /{detailData.max_score}
                    </span>
                    <div style={{ fontSize: 11, color: colors['text-tertiary'], marginTop: 2 }}>得分/满分</div>
                  </div>
                </div>

                {/* 统计概览 */}
                <div style={{
                  display: 'flex', gap: space.sm, marginBottom: space.md,
                  flexWrap: 'wrap',
                }}>
                  <div style={{ flex: 1, minWidth: 80, background: colors['block-lime'], borderRadius: radius.md, padding: '10px 12px', textAlign: 'center' }}>
                    <div style={{ fontSize: 18, fontWeight: 700, color: colors.success }}>
                      {detailData.answers.filter(a => a.is_correct === true).length}
                    </div>
                    <div style={{ fontSize: 11, color: colors['text-secondary'] }}>正确</div>
                  </div>
                  <div style={{ flex: 1, minWidth: 80, background: colors['block-cream'], borderRadius: radius.md, padding: '10px 12px', textAlign: 'center' }}>
                    <div style={{ fontSize: 18, fontWeight: 700, color: colors.danger }}>
                      {detailData.wrong_questions.length}
                    </div>
                    <div style={{ fontSize: 11, color: colors['text-secondary'] }}>错误</div>
                  </div>
                  <div style={{ flex: 1, minWidth: 80, background: colors['block-lilac'], borderRadius: radius.md, padding: '10px 12px', textAlign: 'center' }}>
                    <div style={{ fontSize: 18, fontWeight: 700, color: colors.info }}>
                      {detailData.answers.length > 0
                        ? Math.round(detailData.answers.filter(a => a.is_correct === true).length / detailData.answers.length * 100) + '%'
                        : '-'}
                    </div>
                    <div style={{ fontSize: 11, color: colors['text-secondary'] }}>正确率</div>
                  </div>
                </div>

                {/* 逐题作答表格 */}
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: typography['body-sm'].fontSize }}>
                    <thead>
                      <tr style={{
                        borderBottom: `1px solid ${colors.hairline}`,
                        color: colors['text-secondary'], fontSize: typography.caption.fontSize,
                        fontWeight: 500, textAlign: 'left',
                        background: colors['block-lime'] + '40',
                      }}>
                        <th style={{ padding: '8px 8px', width: 50 }}>题号</th>
                        <th style={{ padding: '8px 8px', width: 90 }}>学生作答</th>
                        <th style={{ padding: '8px 8px', width: 90 }}>正确答案</th>
                        <th style={{ padding: '8px 8px', width: 55, textAlign: 'center' }}>得分</th>
                        <th style={{ padding: '8px 8px', width: 40, textAlign: 'center' }}>对错</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailData.answers.map((a, i) => (
                        <tr key={i} style={{
                          borderBottom: `1px solid ${colors['hairline-soft']}`,
                          background: a.is_correct === false ? colors['block-cream'] + '50' : 'transparent',
                        }}>
                          <td style={{ padding: '8px 8px', fontWeight: 600, color: colors['text-primary'] }}>
                            {a.question_number}
                          </td>
                          <td style={{ padding: '8px 8px', fontWeight: 500, color: colors['text-primary'] }}>
                            {a.student_answer || <span style={{ color: colors['text-tertiary'] }}>-</span>}
                          </td>
                          <td style={{ padding: '8px 8px', color: colors.success, fontWeight: 500 }}>
                            {a.correct_answer || <span style={{ color: colors['text-tertiary'] }}>-</span>}
                          </td>
                          <td style={{ padding: '8px 8px', textAlign: 'center', fontWeight: 600,
                            color: a.is_correct === true ? colors.success : a.is_correct === null ? colors['text-tertiary'] : colors.danger,
                          }}>
                            {a.score !== null ? a.score + '/' + (a.max_score || a.score) : '-'}
                          </td>
                          <td style={{ padding: '8px 8px', textAlign: 'center', fontSize: 16 }}>
                            {a.is_correct === true ? <span style={{ color: colors.success }}>✓</span>
                              : a.is_correct === false ? <span style={{ color: colors.danger }}>✗</span>
                              : <span style={{ color: colors['text-tertiary'] }}>-</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
