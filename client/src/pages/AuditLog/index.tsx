// 审计日志页 — 操作日志查询：按时间/操作人/操作类型筛选
import { useState, useEffect } from 'react';
import { collaborationApi, AuditLogData, AuditLogListData } from '../../api/collaboration';
import { teacherApi, ClassData } from '../../api/teacher';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary, chipStyle,
  inputStyle, labelStyle,
  IconClock, IconSearch, IconX,
} from '../../design-system';

const ACTION_TYPE_LABEL: Record<string, string> = {
  exam_grade: 'AI 批改',
  exam_review: '教师复核',
  student_remove: '移除学生',
  assistant_add: '添加助教',
  assistant_remove: '移除助教',
  class_update: '更新班级',
  exam_publish: '发布试卷',
  report_view: '查看报告',
  grading_task_assign: '分配批改任务',
  grading_submitted: '提交批改结果',
  final_review: '最终复核',
  role_update: '角色变更',
};

const ACTION_TYPE_OPTIONS = Object.entries(ACTION_TYPE_LABEL).map(([k, v]) => ({ value: k, label: v }));

const XS = 8;

function roleStyle(role: string): React.CSSProperties {
  const map: Record<string, { bg: string; color: string }> = {
    teacher: { bg: green.bg, color: green.strong },
    assistant: { bg: green.bg2, color: green.mid },
    admin: { bg: green.bg3, color: green.primary },
  };
  const s = map[role] || { bg: colors['surface-soft'], color: colors['text-secondary'] };
  return {
    display: 'inline-block', padding: '2px 12px', borderRadius: radius.pill,
    fontSize: 12, fontWeight: 500,
    background: s.bg, color: s.color,
  };
}

export default function AuditLog() {
  const [classes, setClasses] = useState<ClassData[]>([]);
  const [filterClassId, setFilterClassId] = useState<string>('');
  const [filterAction, setFilterAction] = useState<string>('');
  const [filterStartDate, setFilterStartDate] = useState('');
  const [filterEndDate, setFilterEndDate] = useState('');

  const [data, setData] = useState<AuditLogListData | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    teacherApi.listClasses().then(setClasses).catch(() => {});
  }, []);

  useEffect(() => { loadData(); }, [page]);

  const loadData = async () => {
    setLoading(true);
    try {
      const result = await collaborationApi.queryAuditLogs({
        class_id: filterClassId || undefined,
        action_type: filterAction || undefined,
        start_date: filterStartDate || undefined,
        end_date: filterEndDate || undefined,
        page, page_size: 20,
      });
      setData(result);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const handleSearch = () => { setPage(1); loadData(); };

  const resetFilters = () => {
    setFilterClassId('');
    setFilterAction('');
    setFilterStartDate('');
    setFilterEndDate('');
    setPage(1);
  };

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      {/* 顶栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: space.sm, marginBottom: space.xl }}>
        <IconClock size={28} color={colors['text-primary']} />
        <h1 style={{
          margin: 0, fontSize: typography['display-lg'].fontSize,
          fontWeight: typography['display-lg'].fontWeight,
          letterSpacing: typography['display-lg'].letterSpacing,
          color: colors['text-primary'],
        }}>审计日志</h1>
      </div>

      {/* 筛选栏 - cream color block */}
      <div style={{
        ...cardStyle, marginBottom: space.xl,
        background: colors['block-cream'],
      }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: space.sm, alignItems: 'flex-end' }}>
          <div style={{ flex: '1 0 160px', minWidth: 140 }}>
            <span style={labelStyle}>班级</span>
            <select value={filterClassId} onChange={e => setFilterClassId(e.target.value)} style={inputStyle}>
              <option value="">全部班级</option>
              {classes.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: '1 0 160px', minWidth: 140 }}>
            <span style={labelStyle}>操作类型</span>
            <select value={filterAction} onChange={e => setFilterAction(e.target.value)} style={inputStyle}>
              <option value="">全部操作</option>
              {ACTION_TYPE_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: '1 0 140px', minWidth: 120 }}>
            <span style={labelStyle}>开始日期</span>
            <input type="date" value={filterStartDate}
              onChange={e => setFilterStartDate(e.target.value)} style={inputStyle} />
          </div>
          <div style={{ flex: '1 0 140px', minWidth: 120 }}>
            <span style={labelStyle}>结束日期</span>
            <input type="date" value={filterEndDate}
              onChange={e => setFilterEndDate(e.target.value)} style={inputStyle} />
          </div>
          <div style={{ display: 'flex', gap: XS }}>
            <button onClick={handleSearch} style={btnPrimary}>
              <IconSearch size={14} color="#fff" /> 查询
            </button>
            <button onClick={resetFilters} style={btnSmallSecondary}>
              <IconX size={12} color={colors['text-secondary']} /> 重置
            </button>
          </div>
        </div>
      </div>

      {/* 日志列表 */}
      <div style={cardStyle}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: colors['text-tertiary'] }}>加载中...</div>
        ) : !data || data.items.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: colors['text-tertiary'] }}>
            暂无日志记录
          </div>
        ) : (
          <>
            {/* 统计条 */}
            <div style={{
              marginBottom: space.md,
              fontSize: typography['body-sm'].fontSize,
              color: colors['text-secondary'],
            }}>
              共 {data.total} 条记录
            </div>

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
                    <th style={{ padding: `10px ${XS}px` }}>时间</th>
                    <th style={{ padding: `10px ${XS}px` }}>操作人</th>
                    <th style={{ padding: `10px ${XS}px` }}>角色</th>
                    <th style={{ padding: `10px ${XS}px` }}>操作类型</th>
                    <th style={{ padding: `10px ${XS}px` }}>详情</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map(log => (
                    <tr key={log.id} style={{ borderBottom: `1px solid ${colors['hairline-soft']}` }}>
                      <td style={{ padding: `10px ${XS}px`, color: colors['text-tertiary'], fontSize: 12, whiteSpace: 'nowrap' }}>
                        {new Date(log.created_at).toLocaleString()}
                      </td>
                      <td style={{ padding: `10px ${XS}px`, fontWeight: 500, color: colors['text-primary'] }}>
                        {log.operator_id}
                      </td>
                      <td style={{ padding: `10px ${XS}px` }}>
                        <span style={roleStyle(log.operator_role)}>
                          {log.operator_role === 'teacher' ? '教师' :
                           log.operator_role === 'assistant' ? '助教' : log.operator_role}
                        </span>
                      </td>
                      <td style={{ padding: `10px ${XS}px`, color: colors['text-primary'] }}>
                        {ACTION_TYPE_LABEL[log.action_type] || log.action_type}
                      </td>
                      <td style={{ padding: `10px ${XS}px` }}>
                        {log.detail ? (
                          <details>
                            <summary style={{
                              fontSize: 12, color: colors.info, cursor: 'pointer',
                              fontWeight: 500,
                            }}>查看详情</summary>
                            <pre style={{
                              fontSize: 11, marginTop: XS, padding: XS,
                              background: colors['surface-soft'], borderRadius: radius.sm,
                              maxWidth: 320, overflow: 'auto', color: colors['text-secondary'],
                            }}>
                              {JSON.stringify(log.detail, null, 2)}
                            </pre>
                          </details>
                        ) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* 分页 */}
            {data.total > 20 && (
              <div style={{
                display: 'flex', justifyContent: 'center', alignItems: 'center',
                padding: space.md, gap: space.md,
              }}>
                <button onClick={() => setPage(p => p - 1)} disabled={page <= 1}
                  style={{ ...btnSmallSecondary, opacity: page <= 1 ? 0.3 : 1 }}>
                  上一页
                </button>
                <span style={{ fontSize: 13, color: colors['text-secondary'] }}>
                  第 {page} 页 / 共 {totalPages} 页（{data.total} 条）
                </span>
                <button onClick={() => setPage(p => p + 1)} disabled={page >= totalPages}
                  style={{ ...btnSmallSecondary, opacity: page >= totalPages ? 0.3 : 1 }}>
                  下一页
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
