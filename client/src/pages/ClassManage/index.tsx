// 班级管理页 — 创建班级、查看列表、导入学生信息、查看学生错题
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { teacherApi, ClassData, StudentInfoItem, StudentExamMistakesOut, StudentExamResult } from '../../api/teacher';
import {
  colors, radius, typography, space, shadows, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary, inputStyle,
  IconPlus, IconUsers, IconArrowRight, IconRefresh, IconBack,
} from '../../design-system';

// ── 题型中文映射 ──
const TYPE_LABELS: Record<string, string> = {
  choice: '选择题', fill: '填空题', translation: '翻译题',
  writing: '写作题', reading: '阅读理解', other: '其他',
};

export default function ClassManage() {
  const navigate = useNavigate();
  const [classes, setClasses] = useState<ClassData[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', stage: 0 });
  const [loading, setLoading] = useState(true);

  // ── 导入学生 ──
  const [importTarget, setImportTarget] = useState<ClassData | null>(null);
  const [importResult, setImportResult] = useState<any>(null);
  const [importing, setImporting] = useState(false);
  const [importedList, setImportedList] = useState<StudentInfoItem[] | null>(null);

  // ── 学生列表查看 ──
  const [studentListTarget, setStudentListTarget] = useState<ClassData | null>(null);
  const [studentList, setStudentList] = useState<StudentInfoItem[]>([]);
  const [loadingStudentList, setLoadingStudentList] = useState(false);

  // ── 错题弹窗 ──
  const [mistakeTarget, setMistakeTarget] = useState<{ className: string; student: StudentInfoItem } | null>(null);
  const [mistakeData, setMistakeData] = useState<StudentExamMistakesOut | null>(null);
  const [loadingMistakes, setLoadingMistakes] = useState(false);

  const loadClasses = async () => {
    try {
      const data = await teacherApi.listClasses();
      setClasses(data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadClasses(); }, []);

  const handleCreate = async () => {
    try {
      await teacherApi.createClass(form);
      setShowCreate(false);
      setForm({ name: '', description: '', stage: 0 });
      loadClasses();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleRegenerateCode = async (classId: number) => {
    try {
      const result = await teacherApi.regenerateInviteCode(classId);
      alert('新邀请码: ' + result.invite_code);
      loadClasses();
    } catch (err: any) {
      alert(err.message);
    }
  };

  // ── 打开导入弹窗 ──
  const openImport = useCallback(async (cls: ClassData) => {
    setImportTarget(cls);
    setImportResult(null);
    setImportedList(null);
    try {
      const list = await teacherApi.listStudentInfo(cls.id);
      setImportedList(list);
    } catch { /* ignore */ }
  }, []);

  // ── 上传 Excel ──
  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !importTarget) return;
    setImporting(true);
    setImportResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const result = await teacherApi.uploadStudentExcel(importTarget.id, formData);
      setImportResult(result);
      const list = await teacherApi.listStudentInfo(importTarget.id);
      setImportedList(list);
    } catch (err: any) {
      alert(err.message || '导入失败');
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  }, [importTarget]);

  // ── 清空学生信息 ──
  const handleClearInfo = useCallback(async () => {
    if (!importTarget || !window.confirm('确认清空该班级所有已导入的学生信息？')) return;
    try {
      await teacherApi.deleteStudentInfo(importTarget.id);
      setImportedList([]);
      setImportResult(null);
    } catch (err: any) {
      alert(err.message);
    }
  }, [importTarget]);

  // ── 打开学生列表 ──
  const openStudentList = useCallback(async (cls: ClassData) => {
    setStudentListTarget(cls);
    setStudentList([]);
    setLoadingStudentList(true);
    try {
      const list = await teacherApi.listStudentInfo(cls.id);
      setStudentList(list || []);
    } catch (err: any) {
      alert(err.message || '获取学生列表失败');
    } finally {
      setLoadingStudentList(false);
    }
  }, []);

  // ── 查看错题 ──
  const openMistakes = useCallback(async (cls: ClassData, student: StudentInfoItem) => {
    setMistakeTarget({ className: cls.name, student });
    setMistakeData(null);
    setLoadingMistakes(true);
    try {
      const data = await teacherApi.getStudentExamMistakes(cls.id, student.exam_number);
      setMistakeData(data);
    } catch (err: any) {
      alert(err.message || '获取错题失败');
    } finally {
      setLoadingMistakes(false);
    }
  }, []);

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      {/* 顶栏 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: space.xl,
      }}>
        <div>
          <h1 style={{
            margin: 0, fontSize: typography['display-lg'].fontSize,
            fontWeight: typography['display-lg'].fontWeight,
            letterSpacing: typography['display-lg'].letterSpacing,
            lineHeight: typography['display-lg'].lineHeight,
            color: colors['text-primary'],
          }}>班级管理</h1>
          <p style={{ margin: '4px 0 0', color: colors['text-secondary'], fontSize: typography['body-sm'].fontSize }}>
            创建和管理教学班级
          </p>
        </div>
        <button onClick={() => setShowCreate(true)} style={btnPrimary}>
          <IconPlus size={14} color="#fff" /> 创建班级
        </button>
      </div>

      {/* 创建表单 */}
      {showCreate && (
        <div style={{ ...cardStyle, marginBottom: space.xl, background: colors['block-lime'] }}>
          <h3 style={{
            margin: '0 0 space.md', fontSize: typography.headline.fontSize,
            fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
          }}>创建新班级</h3>
          <input
            placeholder="班级名称"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            style={{ ...inputStyle, marginBottom: space.sm }}
          />
          <input
            placeholder="班级描述（选填）"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            style={{ ...inputStyle, marginBottom: space.md }}
          />
          <div style={{ display: 'flex', gap: space.xs }}>
            <button onClick={handleCreate} style={btnPrimary}>确认创建</button>
            <button onClick={() => setShowCreate(false)} style={btnSmallSecondary}>取消</button>
          </div>
        </div>
      )}

      {/* 列表 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: colors['text-tertiary'] }}>
          加载中...
        </div>
      ) : classes.length === 0 ? (
        <div style={{
          ...cardStyle, textAlign: 'center', padding: 60,
          border: `2px dashed ${colors.hairline}`,
        }}>
          <p style={{ color: colors['text-tertiary'], margin: 0, fontSize: 15 }}>
            暂无班级，点击右上角创建
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: space.sm }}>
          {classes.map((cls) => (
            <div key={cls.id} style={{
              ...cardStyle,
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: space.lg,
            }}>
              <div>
                <h3 style={{
                  margin: '0 0 6px', fontSize: typography['card-title'].fontSize,
                  fontWeight: 600, color: colors['text-primary'],
                }}>{cls.name}</h3>
                {cls.description && (
                  <p style={{ margin: '0 0 10px', color: colors['text-secondary'], fontSize: typography['body-sm'].fontSize }}>
                    {cls.description}
                  </p>
                )}
                <div style={{ display: 'flex', gap: 20, fontSize: typography['body-sm'].fontSize, color: colors['text-secondary'] }}>
                  <span>ID: {cls.id}</span>
                  <span>{cls.student_count} 人</span>
                  <span>
                    邀请码{' '}
                    <code style={{
                      background: colors['surface-soft'], padding: '2px 8px',
                      borderRadius: radius.sm, fontSize: 12, color: colors['text-primary'],
                    }}>{cls.invite_code}</code>
                  </span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: space.xs }}>
                <button onClick={() => handleRegenerateCode(cls.id)} style={btnSmallSecondary}>
                  <IconRefresh size={13} color={colors['text-secondary']} />
                </button>
                <button
                  onClick={() => openImport(cls)}
                  style={{ ...btnSmall, background: '#f0f7f0', color: '#2d7d46', border: '1px solid #c8e0c8' }}
                >
                  <IconUsers size={13} color="#2d7d46" /> 导入学生
                </button>
                <button
                  onClick={() => openStudentList(cls)}
                  style={{ ...btnSmall, background: '#eef2ff', color: '#4f46e5', border: '1px solid #c7d2fe' }}
                >
                  <IconUsers size={13} color="#4f46e5" /> 学生列表
                </button>
                <button
                  onClick={() => navigate(`/classes/${cls.id}/dashboard`)}
                  style={{ ...btnSmall, background: colors.primary, color: colors['on-primary'], border: 'none' }}
                >
                  看板 <IconArrowRight size={12} color="#fff" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── 导入学生弹窗 ── */}
      {importTarget && (
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 10000,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onClick={(e) => { if (e.target === e.currentTarget) setImportTarget(null); }}
        >
          <div style={{
            width: 500, maxWidth: 'calc(100vw - 48px)',
            background: '#fff', borderRadius: 16,
            boxShadow: '0 16px 48px rgba(0,0,0,0.18)',
            overflow: 'hidden',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '16px 20px', borderBottom: '1px solid #f0f0f0',
            }}>
              <span style={{ fontSize: 16, fontWeight: 600, color: '#1a2e1a' }}>
                导入学生 — {importTarget.name}
              </span>
              <button
                onClick={() => setImportTarget(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: '#999', padding: 4 }}
              >✕</button>
            </div>
            <div style={{ padding: '20px' }}>
              {/* 上传区域 */}
              <div style={{
                border: `2px dashed ${importResult ? '#2d7d46' : '#d0d5dd'}`,
                borderRadius: 12, padding: '24px 20px',
                textAlign: 'center', background: importResult ? '#f6faf6' : '#f9fafb',
                transition: 'all 0.2s',
              }}>
                {importing ? (
                  <div style={{ color: '#2d7d46', fontSize: 14 }}>
                    <div style={{
                      width: 24, height: 24, border: '3px solid #e0e0e0',
                      borderTopColor: '#2d7d46', borderRadius: '50%',
                      animation: 'badgeSpin 0.8s linear infinite',
                      margin: '0 auto 12px',
                    }} />
                    正在解析导入...
                  </div>
                ) : (
                  <>
                    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke={importResult ? '#2d7d46' : '#9ca3af'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ marginBottom: 8 }}>
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    <p style={{ margin: '0 0 4px', fontSize: 14, color: '#374151' }}>
                      上传包含 <strong>序号</strong>、<strong>姓名</strong>、<strong>考号</strong> 的 Excel 文件
                    </p>
                    <p style={{ margin: '0 0 14px', fontSize: 12, color: '#9ca3af' }}>
                      支持 .xlsx / .xls 格式
                    </p>
                    <label style={{
                      display: 'inline-block', padding: '8px 24px',
                      background: importResult ? '#2d7d46' : '#1a2e1a',
                      color: '#fff', borderRadius: 50, fontSize: 13, fontWeight: 500,
                      cursor: 'pointer', transition: 'background 0.15s',
                    }}>
                      {importResult ? '继续导入' : '选择文件'}
                      <input
                        type="file"
                        accept=".xlsx,.xls"
                        onChange={handleFileChange}
                        style={{ display: 'none' }}
                      />
                    </label>
                  </>
                )}
              </div>
              {importResult && (
                <div style={{
                  marginTop: 16, padding: '12px 16px',
                  background: '#f0faf0', borderRadius: 10,
                  border: '1px solid #c8e8c8',
                }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#2d7d46', marginBottom: 6 }}>
                    ✓ 导入完成
                  </div>
                  <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.6 }}>
                    共 <strong>{importResult.total}</strong> 行数据，
                    成功导入 <strong style={{ color: '#2d7d46' }}>{importResult.imported}</strong> 条，
                    {importResult.skipped > 0 && (
                      <>跳过 <strong style={{ color: '#e68a00' }}>{importResult.skipped}</strong> 条重复考号，</>
                    )}
                    当前班级共有 <strong>{importedList?.length || 0}</strong> 条学生信息。
                  </div>
                  {importResult.items?.some((i: any) => i.created_account) && (
                    <div style={{ fontSize: 13, color: '#1a6b3c', marginTop: 6, lineHeight: 1.6 }}>
                      🔑 自动创建了 <strong>{importResult.items.filter((i: any) => i.created_account).length}</strong> 个学生账号，
                      初始密码统一为 <code style={{ background: '#e6f4e6', padding: '1px 6px', borderRadius: 4, fontSize: 12 }}>123456</code>
                    </div>
                  )}
                </div>
              )}
              {importedList && importedList.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: 8,
                  }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
                      已导入学生（{importedList.length} 人）
                    </span>
                    <button
                      onClick={handleClearInfo}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        fontSize: 12, color: '#e53935', padding: '2px 6px',
                      }}
                    >清空</button>
                  </div>
                  <div style={{
                    maxHeight: 200, overflow: 'auto',
                    border: '1px solid #f0f0f0', borderRadius: 8,
                  }}>
                    <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ background: '#f9fafb', position: 'sticky', top: 0 }}>
                          <th style={{ padding: '6px 10px', textAlign: 'left', color: '#6b7280', fontWeight: 500, borderBottom: '1px solid #f0f0f0' }}>序号</th>
                          <th style={{ padding: '6px 10px', textAlign: 'left', color: '#6b7280', fontWeight: 500, borderBottom: '1px solid #f0f0f0' }}>姓名</th>
                          <th style={{ padding: '6px 10px', textAlign: 'left', color: '#6b7280', fontWeight: 500, borderBottom: '1px solid #f0f0f0' }}>考号</th>
                          <th style={{ padding: '6px 10px', textAlign: 'left', color: '#6b7280', fontWeight: 500, borderBottom: '1px solid #f0f0f0' }}>登录账号</th>
                        </tr>
                      </thead>
                      <tbody>
                        {importedList.map((item, i) => (
                          <tr key={i}>
                            <td style={{ padding: '5px 10px', borderBottom: '1px solid #f5f5f5', color: '#374151' }}>{item.student_number}</td>
                            <td style={{ padding: '5px 10px', borderBottom: '1px solid #f5f5f5', color: '#374151' }}>{item.student_name}</td>
                            <td style={{ padding: '5px 10px', borderBottom: '1px solid #f5f5f5', color: '#9ca3af', fontFamily: 'monospace' }}>{item.exam_number}</td>
                            <td style={{ padding: '5px 10px', borderBottom: '1px solid #f5f5f5', color: '#1a6b3c', fontFamily: 'monospace', fontSize: 11 }}>
                              {(item as any).created_account || '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
            <div style={{
              display: 'flex', justifyContent: 'flex-end',
              padding: '12px 20px', borderTop: '1px solid #f0f0f0',
            }}>
              <button
                onClick={() => setImportTarget(null)}
                style={{
                  padding: '8px 24px', borderRadius: 50,
                  border: 'none', background: '#f0f0f0',
                  color: '#374151', fontSize: 13, cursor: 'pointer',
                }}
              >关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* ── 学生列表弹窗 ── */}
      {studentListTarget && (
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 10000,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onClick={(e) => { if (e.target === e.currentTarget) setStudentListTarget(null); }}
        >
          <div style={{
            width: 520, maxWidth: 'calc(100vw - 48px)',
            background: '#fff', borderRadius: 16,
            boxShadow: '0 16px 48px rgba(0,0,0,0.18)',
            overflow: 'hidden', maxHeight: '80vh', display: 'flex', flexDirection: 'column',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '16px 20px', borderBottom: '1px solid #f0f0f0',
            }}>
              <span style={{ fontSize: 16, fontWeight: 600, color: '#1a2e1a' }}>
                学生列表 — {studentListTarget.name}
              </span>
              <button
                onClick={() => setStudentListTarget(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: '#999', padding: 4 }}
              >✕</button>
            </div>
            <div style={{ padding: '20px', overflow: 'auto', flex: 1 }}>
              {loadingStudentList ? (
                <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>加载中...</div>
              ) : studentList.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40, color: '#999', fontSize: 14 }}>
                  暂无导入的学生信息，请先导入 Excel
                </div>
              ) : (
                <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: '#f9fafb' }}>
                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#6b7280', fontWeight: 500, borderBottom: '1px solid #e5e7eb' }}>序号</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#6b7280', fontWeight: 500, borderBottom: '1px solid #e5e7eb' }}>姓名</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left', color: '#6b7280', fontWeight: 500, borderBottom: '1px solid #e5e7eb' }}>考号</th>
                      <th style={{ padding: '8px 12px', textAlign: 'center', color: '#6b7280', fontWeight: 500, borderBottom: '1px solid #e5e7eb' }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {studentList.map((item, i) => (
                      <tr key={i} style={{ transition: 'background 0.15s' }}
                        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = '#f9fafb'; }}
                        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ''; }}
                      >
                        <td style={{ padding: '10px 12px', borderBottom: '1px solid #f5f5f5', color: '#374151' }}>{item.student_number}</td>
                        <td style={{ padding: '10px 12px', borderBottom: '1px solid #f5f5f5', color: '#1a2e1a', fontWeight: 500 }}>{item.student_name}</td>
                        <td style={{ padding: '10px 12px', borderBottom: '1px solid #f5f5f5', color: '#6b7280', fontFamily: 'monospace' }}>{item.exam_number}</td>
                        <td style={{ padding: '10px 12px', borderBottom: '1px solid #f5f5f5', textAlign: 'center' }}>
                          <button
                            onClick={() => {
                              setStudentListTarget(null);
                              openMistakes(studentListTarget, item);
                            }}
                            style={{
                              padding: '4px 14px', borderRadius: 50, border: 'none',
                              background: '#eef2ff', color: '#4f46e5',
                              fontSize: 12, fontWeight: 500, cursor: 'pointer',
                              transition: 'all 0.15s',
                            }}
                          >查看错题</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div style={{
              display: 'flex', justifyContent: 'flex-end',
              padding: '12px 20px', borderTop: '1px solid #f0f0f0',
            }}>
              <button
                onClick={() => setStudentListTarget(null)}
                style={{
                  padding: '8px 24px', borderRadius: 50,
                  border: 'none', background: '#f0f0f0',
                  color: '#374151', fontSize: 13, cursor: 'pointer',
                }}
              >关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* ── 错题详情弹窗 ── */}
      {mistakeTarget && (
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 10001,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onClick={(e) => { if (e.target === e.currentTarget) setMistakeTarget(null); }}
        >
          <div style={{
            width: 680, maxWidth: 'calc(100vw - 48px)',
            background: '#fff', borderRadius: 16,
            boxShadow: '0 16px 48px rgba(0,0,0,0.18)',
            overflow: 'hidden', maxHeight: '85vh', display: 'flex', flexDirection: 'column',
          }}>
            {/* 头部 */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '16px 20px', borderBottom: '1px solid #f0f0f0',
            }}>
              <div>
                <span style={{ fontSize: 16, fontWeight: 600, color: '#1a2e1a' }}>
                  错题本 — {mistakeTarget.student.student_name}
                </span>
                <span style={{ marginLeft: 10, fontSize: 13, color: '#6b7280' }}>
                  （考号: {mistakeTarget.student.exam_number}）
                </span>
              </div>
              <button
                onClick={() => setMistakeTarget(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: '#999', padding: 4 }}
              >✕</button>
            </div>

            {/* 内容 */}
            <div style={{ padding: '20px', overflow: 'auto', flex: 1 }}>
              {loadingMistakes ? (
                <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>
                  <div style={{
                    width: 28, height: 28, border: '3px solid #e0e0e0',
                    borderTopColor: '#4f46e5', borderRadius: '50%',
                    animation: 'badgeSpin 0.8s linear infinite',
                    margin: '0 auto 12px',
                  }} />
                  加载错题数据...
                </div>
              ) : mistakeData ? (
                <>
                  {/* 概要统计 */}
                  <div style={{
                    display: 'flex', gap: 16, marginBottom: 20,
                    padding: '14px 18px', background: '#f8f6ff',
                    borderRadius: 12, border: '1px solid #e8e4ff',
                  }}>
                    <div style={{ flex: 1, textAlign: 'center' }}>
                      <div style={{ fontSize: 22, fontWeight: 700, color: '#4f46e5' }}>{mistakeData.exam_count}</div>
                      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>参与考试</div>
                    </div>
                    <div style={{ flex: 1, textAlign: 'center' }}>
                      <div style={{ fontSize: 22, fontWeight: 700, color: '#e53935' }}>{mistakeData.total_wrong}</div>
                      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>累计错题</div>
                    </div>
                  </div>

                  {mistakeData.exams.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 40, color: '#999', fontSize: 14 }}>
                      暂无已批改的考试记录
                    </div>
                  ) : (
                    mistakeData.exams.map((exam, ei) => (
                      <div key={ei} style={{
                        marginBottom: 16, border: '1px solid #e5e7eb',
                        borderRadius: 12, overflow: 'hidden',
                      }}>
                        {/* 考试标题栏 */}
                        <div style={{
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                          padding: '10px 14px', background: '#f9fafb',
                          borderBottom: '1px solid #e5e7eb',
                        }}>
                          <span style={{ fontSize: 14, fontWeight: 600, color: '#1a2e1a' }}>
                            {exam.exam_title}
                          </span>
                          <span style={{ fontSize: 13, color: '#6b7280' }}>
                            得分 <strong style={{ color: exam.total_score >= exam.max_score * 0.6 ? '#2d7d46' : '#e53935' }}>{exam.total_score}</strong> / {exam.max_score}
                            &nbsp;·&nbsp;错题 <strong style={{ color: '#e53935' }}>{exam.wrong_questions.length}</strong> 题
                          </span>
                        </div>

                        {/* 错题列表 */}
                        {exam.wrong_questions.length === 0 ? (
                          <div style={{ padding: '16px 14px', textAlign: 'center', color: '#2d7d46', fontSize: 13 }}>
                            ✓ 全部正确，无错题
                          </div>
                        ) : (
                          <div style={{ padding: '10px 14px' }}>
                            {exam.wrong_questions.map((wq, wi) => (
                              <div key={wi} style={{
                                padding: '10px 0',
                                borderBottom: wi < exam.wrong_questions.length - 1 ? '1px solid #f5f5f5' : 'none',
                              }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                  <span style={{
                                    fontSize: 12, fontWeight: 600, color: '#374151',
                                    background: '#fef2f2', padding: '1px 8px', borderRadius: 4,
                                  }}>
                                    {TYPE_LABELS[wq.question_type] || wq.question_type} · 第{wq.question_index + 1}题
                                    <span style={{ marginLeft: 8, color: '#e53935' }}>
                                      {wq.score}/{wq.max_score}分
                                    </span>
                                  </span>
                                </div>
                                <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.5, marginBottom: 4 }}>
                                  {wq.stem}
                                </div>
                                <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
                                  <span>
                                    学生答案: <span style={{ color: '#e53935', fontWeight: 500 }}>{wq.user_answer || '（空）'}</span>
                                  </span>
                                  <span>
                                    正确答案: <span style={{ color: '#2d7d46', fontWeight: 500 }}>{wq.correct_answer}</span>
                                  </span>
                                </div>
                                {wq.ai_comment && (
                                  <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280', fontStyle: 'italic' }}>
                                    {wq.ai_comment}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))
                  )}

                  {/* 教师备注 */}
                  <div style={{
                    padding: '12px 16px', background: '#fffbeb',
                    borderRadius: 10, border: '1px solid #fde68a', fontSize: 13, color: '#92400e', lineHeight: 1.5, marginTop: 8,
                  }}>
                    💡 错题数据来源于 OCR 批卷的逐题评分结果。显示所有得分不足 70% 或标记为错误的题目。
                  </div>
                </>
              ) : null}
            </div>

            {/* 底部 */}
            <div style={{
              display: 'flex', justifyContent: 'flex-end',
              padding: '12px 20px', borderTop: '1px solid #f0f0f0',
            }}>
              <button
                onClick={() => setMistakeTarget(null)}
                style={{
                  padding: '8px 24px', borderRadius: 50,
                  border: 'none', background: '#f0f0f0',
                  color: '#374151', fontSize: 13, cursor: 'pointer',
                }}
              >关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
