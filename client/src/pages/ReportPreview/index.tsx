// 报告预览页 — 学生学习报告 + 班级学期报告，支持导出 PDF
import { useState, useEffect } from 'react';
import { teacherApi, ClassData } from '../../api/teacher';
import { collaborationApi, PersonalReportData, ClassReportData } from '../../api/collaboration';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary, chipStyle,
  inputStyle, labelStyle,
  IconChart, IconUsers, IconBook, IconActivity, IconArrowRight, IconFile,
  progressBarStyle, progressBarFill,
} from '../../design-system';

const XS = 8;
const XSS = 4;

// Progress bar for report module breakdown
function ModuleBar({ label, accuracy }: { label: string; accuracy: number }) {
  const barColor = accuracy >= 80 ? colors.success : accuracy >= 60 ? colors.warning : colors.danger;
  return (
    <div style={{ marginBottom: XS }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: typography['body-sm'].fontSize }}>
        <span style={{ color: colors['text-primary'] }}>{label}</span>
        <span style={{ color: barColor, fontWeight: 500 }}>{accuracy}%</span>
      </div>
      <div style={progressBarStyle(100)}>
        <div style={{ ...progressBarFill(accuracy), background: barColor }} />
      </div>
    </div>
  );
}

export default function ReportPreview() {
  const [mode, setMode] = useState<'personal' | 'class'>('personal');
  const [classes, setClasses] = useState<ClassData[]>([]);
  const [selectedClassId, setSelectedClassId] = useState<string | null>(null);
  const [studentId, setStudentId] = useState('');

  const [periodStart, setPeriodStart] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 30);
    return d.toISOString().split('T')[0];
  });
  const [periodEnd, setPeriodEnd] = useState(() => new Date().toISOString().split('T')[0]);

  const [personalReport, setPersonalReport] = useState<PersonalReportData | null>(null);
  const [classReport, setClassReport] = useState<ClassReportData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    teacherApi.listClasses().then(setClasses).catch(() => {});
  }, []);

  const loadPersonalReport = async () => {
    if (!studentId) return;
    setLoading(true);
    try {
      const result = await collaborationApi.getPersonalReport({
        class_id: selectedClassId || undefined,
        period_start: periodStart,
        period_end: periodEnd,
      });
      setPersonalReport(result);
      setClassReport(null);
    } catch (e: any) {
      alert(e.message || '加载报告失败');
    }
    setLoading(false);
  };

  const loadClassReport = async () => {
    if (!selectedClassId) return;
    setLoading(true);
    try {
      const result = await collaborationApi.getClassReport(selectedClassId, {
        period_start: periodStart,
        period_end: periodEnd,
      });
      setClassReport(result);
      setPersonalReport(null);
    } catch (e: any) {
      alert(e.message || '加载报告失败');
    }
    setLoading(false);
  };

  const handleExportPDF = () => { window.print(); };

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      {/* 顶栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: space.sm, marginBottom: space.xl }}>
        <IconChart size={28} color={colors['text-primary']} />
        <h1 style={{
          margin: 0, fontSize: typography['display-lg'].fontSize,
          fontWeight: typography['display-lg'].fontWeight,
          letterSpacing: typography['display-lg'].letterSpacing,
          color: colors['text-primary'],
        }}>报告预览</h1>
      </div>

      {/* 模式切换 + 查询条件 */}
      <div style={{ ...cardStyle, marginBottom: space.xl, background: colors['block-mint'] }}>
        {/* 模式切换 - pill tabs */}
        <div style={{ display: 'flex', gap: XS, marginBottom: space.md }}>
          {[
            { key: 'personal' as const, label: '个人学习报告' },
            { key: 'class' as const, label: '班级学期报告' },
          ].map(tab => (
            <button key={tab.key} onClick={() => setMode(tab.key)} style={chipStyle(mode === tab.key)}>
              {tab.label}
            </button>
          ))}
        </div>

        {/* 查询条件 */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: space.sm, alignItems: 'flex-end' }}>
          {mode === 'personal' && (
            <div style={{ flex: '1 0 160px', minWidth: 140 }}>
              <span style={labelStyle}>学生用户 ID</span>
              <input type="number" value={studentId}
                onChange={e => setStudentId(e.target.value)}
                style={inputStyle} placeholder="输入用户 ID" />
            </div>
          )}
          <div style={{ flex: '1 0 160px', minWidth: 140 }}>
            <span style={labelStyle}>班级（可选）</span>
            <select value={selectedClassId || ''}
              onChange={e => setSelectedClassId(e.target.value || null)} style={inputStyle}>
              <option value="">全部</option>
              {classes.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: '1 0 140px', minWidth: 120 }}>
            <span style={labelStyle}>开始日期</span>
            <input type="date" value={periodStart}
              onChange={e => setPeriodStart(e.target.value)} style={inputStyle} />
          </div>
          <div style={{ flex: '1 0 140px', minWidth: 120 }}>
            <span style={labelStyle}>结束日期</span>
            <input type="date" value={periodEnd}
              onChange={e => setPeriodEnd(e.target.value)} style={inputStyle} />
          </div>
          <div style={{ display: 'flex', gap: XS }}>
            <button onClick={mode === 'personal' ? loadPersonalReport : loadClassReport}
              disabled={loading} style={{ ...btnPrimary, opacity: loading ? 0.5 : 1 }}>
              {loading ? '生成中...' : '生成报告'}
            </button>
            {(personalReport || classReport) && (
              <button onClick={handleExportPDF} style={btnSmallSecondary}>
                <IconFile size={12} color={colors['text-secondary']} /> 导出 PDF
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ========== 个人报告 ========== */}
      {personalReport && (
        <div style={cardStyle}>
          {/* 报告头 */}
          <div style={{ marginBottom: space.xl }}>
            <h2 style={{
              margin: `0 0 ${XSS}px`, fontSize: typography.headline.fontSize,
              fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
            }}>{personalReport.nickname} 学习报告</h2>
            <p style={{ fontSize: typography['body-sm'].fontSize, color: colors['text-secondary'], margin: 0 }}>
              {personalReport.period_start} ~ {personalReport.period_end}
            </p>
          </div>

          {/* 概览卡片 */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: space.sm, marginBottom: space.xl }}>
            {[
              { label: '学习天数', value: personalReport.study_days, unit: '天', color: colors.success },
              { label: '总词汇量', value: personalReport.total_words, unit: '词', color: colors.info },
              { label: '训练次数', value: personalReport.total_training, unit: '次', color: colors.warning },
              { label: '考试次数', value: personalReport.total_exams, unit: '次', color: '#7c3aed' },
              { label: '综合正确率', value: personalReport.overall_accuracy + '%', unit: '', color: colors.success },
            ].map(item => (
              <div key={item.label} style={{
                ...cardStyle,
                flex: 1, minWidth: 120,
                display: 'flex', flexDirection: 'column', gap: XSS,
                textAlign: 'center',
              }}>
                <span style={{ fontSize: 24, fontWeight: 550, color: item.color, lineHeight: 1.1 }}>
                  {item.value}
                </span>
                <span style={{
                  fontSize: typography.caption.fontSize,
                  fontWeight: 500, textTransform: 'uppercase',
                  letterSpacing: typography.eyebrow.letterSpacing,
                  color: colors['text-tertiary'],
                }}>{item.label}</span>
              </div>
            ))}
          </div>

          {/* 各模块正确率 */}
          <div style={{ marginBottom: space.xl }}>
            <h3 style={{
              margin: `0 0 ${space.sm}px`, fontSize: typography['card-title'].fontSize,
              fontWeight: 600, color: colors['text-primary'],
            }}>各模块正确率</h3>
            {personalReport.module_breakdown.map(m => (
              <ModuleBar key={m.category} label={m.category} accuracy={m.accuracy} />
            ))}
          </div>

          {/* 薄弱知识点 */}
          {personalReport.weakness_points.length > 0 && (
            <div style={{ ...cardStyle, marginBottom: space.xl, background: colors['block-coral'] }}>
              <h3 style={{
                margin: `0 0 ${space.sm}px`, fontSize: typography['card-title'].fontSize,
                fontWeight: 600, color: colors['text-primary'],
              }}>薄弱知识点</h3>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: XS }}>
                {personalReport.weakness_points.map(w => (
                  <span key={w.knowledge_point} style={{
                    display: 'inline-flex', alignItems: 'center', gap: XSS,
                    padding: '4px 14px', borderRadius: radius.pill,
                    background: '#fef2f2', color: colors.danger, fontSize: 13,
                    border: '1px solid #fecaca',
                  }}>
                    {w.knowledge_point}
                    <span style={{ fontWeight: 600 }}>{w.count}次</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* AI 学习建议 */}
          <div style={{
            padding: space.md, borderRadius: radius.md,
            background: colors['block-lilac'],
          }}>
            <h3 style={{
              margin: `0 0 ${space.sm}px`, fontSize: typography['card-title'].fontSize,
              fontWeight: 600, color: colors['text-primary'],
            }}>AI 学习建议</h3>
            <ul style={{ margin: 0, paddingLeft: space.md, display: 'flex', flexDirection: 'column', gap: XS }}>
              {personalReport.improvement_suggestions.map((s, i) => (
                <li key={i} style={{ fontSize: typography.body.fontSize, color: '#6d28d9', lineHeight: 1.6 }}>{s}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* ========== 班级报告 ========== */}
      {classReport && (
        <div style={cardStyle}>
          {/* 报告头 */}
          <div style={{ marginBottom: space.xl }}>
            <h2 style={{
              margin: `0 0 ${XSS}px`, fontSize: typography.headline.fontSize,
              fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
            }}>{classReport.class_name} 学期报告</h2>
            <p style={{ fontSize: typography['body-sm'].fontSize, color: colors['text-secondary'], margin: 0 }}>
              {classReport.period_start} ~ {classReport.period_end} · {classReport.student_count} 名学生
            </p>
          </div>

          {/* 概览 */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: space.sm, marginBottom: space.xl }}>
            {[
              { label: '综合正确率', value: classReport.overall_accuracy + '%', color: colors.success },
              { label: '总训练次数', value: classReport.total_training, color: colors.info },
              { label: '总词汇量', value: classReport.total_words, color: colors.warning },
              { label: '平均学习天数', value: classReport.avg_study_days, color: green.strong },
            ].map(item => (
              <div key={item.label} style={{
                ...cardStyle,
                flex: 1, minWidth: 140,
                display: 'flex', flexDirection: 'column', gap: XSS,
                textAlign: 'center',
              }}>
                <span style={{ fontSize: 24, fontWeight: 550, color: item.color, lineHeight: 1.1 }}>{item.value}</span>
                <span style={{
                  fontSize: typography.caption.fontSize,
                  fontWeight: 500, textTransform: 'uppercase',
                  letterSpacing: typography.eyebrow.letterSpacing,
                  color: colors['text-tertiary'],
                }}>{item.label}</span>
              </div>
            ))}
          </div>

          {/* 高频错题 */}
          <div style={{ marginBottom: space.xl }}>
            <h3 style={{
              margin: `0 0 ${space.sm}px`, fontSize: typography['card-title'].fontSize,
              fontWeight: 600, color: colors['text-primary'],
            }}>高频错题 TOP{Math.min(classReport.top_mistakes.length, 5)}</h3>
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
                    <th style={{ padding: `10px ${XS}px` }}>知识点</th>
                    <th style={{ padding: `10px ${XS}px` }}>错误次数</th>
                  </tr>
                </thead>
                <tbody>
                  {classReport.top_mistakes.map(m => (
                    <tr key={m.knowledge_point} style={{ borderBottom: `1px solid ${colors['hairline-soft']}` }}>
                      <td style={{ padding: `10px ${XS}px`, color: colors['text-primary'] }}>{m.knowledge_point}</td>
                      <td style={{ padding: `10px ${XS}px` }}>
                        <span style={{ color: colors.danger, fontWeight: 600 }}>{m.count}</span> 次
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* 学生排名 */}
          <div>
            <h3 style={{
              margin: `0 0 ${space.sm}px`, fontSize: typography['card-title'].fontSize,
              fontWeight: 600, color: colors['text-primary'],
            }}>学生排名（TOP 10）</h3>
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
                    <th style={{ padding: `10px ${XS}px` }}>#</th>
                    <th style={{ padding: `10px ${XS}px` }}>学生</th>
                    <th style={{ padding: `10px ${XS}px` }}>正确率</th>
                    <th style={{ padding: `10px ${XS}px` }}>训练次数</th>
                  </tr>
                </thead>
                <tbody>
                  {classReport.student_ranking.slice(0, 10).map((s, i) => (
                    <tr key={s.student_id} style={{ borderBottom: `1px solid ${colors['hairline-soft']}` }}>
                      <td style={{ padding: `10px ${XS}px`, color: colors['text-tertiary'], fontWeight: 500 }}>{i + 1}</td>
                      <td style={{ padding: `10px ${XS}px`, fontWeight: 500, color: colors['text-primary'] }}>{s.name}</td>
                      <td style={{ padding: `10px ${XS}px` }}>
                        <span style={{ color: s.accuracy >= 70 ? colors.success : colors.warning, fontWeight: 500 }}>
                          {s.accuracy}%
                        </span>
                      </td>
                      <td style={{ padding: `10px ${XS}px`, color: colors['text-secondary'] }}>{s.total_quiz}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
