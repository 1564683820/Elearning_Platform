// 学校管理页 — 管理员管理 + 学校级数据看板 + 多班级对比 + 兑换码管理
import { useState, useEffect } from 'react';
import { membershipApi, PlanInfo } from '../../api/membership';
import { collaborationApi, SchoolAdminData, SchoolDashboardData } from '../../api/collaboration';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary, chipStyle,
  inputStyle, labelStyle,
  IconBook, IconChart, IconUsers, IconShield, IconPlus, IconX, IconCheck,
  IconFile, IconRefresh,
} from '../../design-system';

const XS = 8;
const XSS = 4;

function statusBadgeStyle(status: string): React.CSSProperties {
  const map: Record<string, { bg: string; color: string }> = {
    active: { bg: colors['block-lime'], color: colors.success },
    used: { bg: colors['surface-soft'], color: colors['text-secondary'] },
    expired: { bg: colors['block-cream'], color: colors.warning },
    disabled: { bg: '#fef2f2', color: colors.danger },
  };
  const s = map[status] || { bg: colors['surface-soft'], color: colors['text-secondary'] };
  return {
    display: 'inline-block', padding: '2px 12px', borderRadius: radius.pill,
    fontSize: 12, fontWeight: 500, background: s.bg, color: s.color,
  };
}

function statusLabel(status: string): string {
  const map: Record<string, string> = { active: '待使用', used: '已使用', expired: '已过期', disabled: '已停用' };
  return map[status] || status;
}

const TABS = [
  { key: 'purchase' as const, label: '采购管理', icon: IconBook },
  { key: 'dashboard' as const, label: '数据看板', icon: IconChart },
  { key: 'admins' as const, label: '管理员管理', icon: IconShield },
];

export default function SchoolAdmin() {
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'purchase' | 'dashboard' | 'admins'>('purchase');

  const [dashboard, setDashboard] = useState<SchoolDashboardData | null>(null);

  const [admins, setAdmins] = useState<SchoolAdminData[]>([]);
  const [showCreateAdmin, setShowCreateAdmin] = useState(false);
  const [adminForm, setAdminForm] = useState({ user_id: '', school_name: '', contact_phone: '' });
  const [creatingAdmin, setCreatingAdmin] = useState(false);

  const [codeForm, setCodeForm] = useState({
    plan: 'vip_teacher', duration_months: 1, count: 10, expire_days: 365, remark: '',
  });
  const [generating, setGenerating] = useState(false);
  const [generatedCodes, setGeneratedCodes] = useState<any[] | null>(null);
  const [codes, setCodes] = useState<any[]>([]);
  const [codesTotal, setCodesTotal] = useState(0);
  const [codePage, setCodePage] = useState(1);
  const [codeStatusFilter, setCodeStatusFilter] = useState<string>('');

  useEffect(() => {
    membershipApi.getPlans().then(setPlans).finally(() => setLoading(false));
    loadCodes();
    loadDashboard();
    loadAdmins();
  }, []);

  useEffect(() => { loadCodes(); }, [codePage, codeStatusFilter]);

  const loadCodes = () => {
    membershipApi.listRedeemCodes({ page: codePage, page_size: 10, status: codeStatusFilter || undefined })
      .then(res => { setCodes(res.items); setCodesTotal(res.total); });
  };

  const loadDashboard = async () => {
    try { const d = await collaborationApi.getSchoolDashboard(); setDashboard(d); } catch { /* 容错 */ }
  };

  const loadAdmins = async () => {
    try { const a = await collaborationApi.listSchoolAdmins(); setAdmins(a); } catch { /* 容错 */ }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await membershipApi.batchGenerateCodes(codeForm);
      setGeneratedCodes(res.codes);
      loadCodes();
    } catch (e: any) { alert(e.message || '生成失败'); }
    setGenerating(false);
  };

  const handleCreateAdmin = async () => {
    if (!adminForm.user_id || !adminForm.school_name) return;
    setCreatingAdmin(true);
    try {
      await collaborationApi.createSchoolAdmin({
        user_id: adminForm.user_id,
        school_name: adminForm.school_name,
        contact_phone: adminForm.contact_phone || undefined,
      });
      setShowCreateAdmin(false);
      setAdminForm({ user_id: '', school_name: '', contact_phone: '' });
      loadAdmins();
    } catch (e: any) { alert(e.message || '创建失败'); }
    setCreatingAdmin(false);
  };

  const handleToggleAdmin = async (userId: number) => {
    try { await collaborationApi.toggleSchoolAdmin(userId); loadAdmins(); } catch (e: any) { alert(e.message || '操作失败'); }
  };

  const copyAllCodes = () => {
    if (!generatedCodes) return;
    const text = generatedCodes.map(c => c.code).join('\n');
    navigator.clipboard.writeText(text).then(() => alert('已复制所有兑换码到剪贴板'));
  };

  const exportCodes = () => {
    if (!generatedCodes) return;
    const csv = '兑换码,套餐,时长(月)\n' + generatedCodes.map(c => c.code + ',' + c.plan + ',' + c.duration_months).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url;
    a.download = '兑换码_' + Date.now() + '.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) return <div style={{ padding: 60, textAlign: 'center', color: colors['text-tertiary'] }}>加载中...</div>;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      {/* 顶栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: space.sm, marginBottom: space.xl }}>
        <IconBook size={28} color={colors['text-primary']} />
        <h1 style={{
          margin: 0, fontSize: typography['display-lg'].fontSize,
          fontWeight: typography['display-lg'].fontWeight,
          letterSpacing: typography['display-lg'].letterSpacing,
          color: colors['text-primary'],
        }}>学校管理</h1>
      </div>

      {/* Tab pill 切换 */}
      <div style={{ display: 'flex', gap: XS, marginBottom: space.xl }}>
        {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.key;
          return (
            <button key={t.key} onClick={() => setTab(t.key)} style={{
              display: 'flex', alignItems: 'center', gap: XS,
              padding: '8px 20px', borderRadius: radius.pill,
              border: `1px solid ${active ? colors.primary : colors.hairline}`,
              background: active ? colors.primary : colors.canvas,
              color: active ? colors['on-primary'] : colors['text-secondary'],
              cursor: 'pointer', fontSize: 14, fontWeight: active ? 500 : 400,
              transition: 'all 0.15s',
            }}>
              <Icon size={14} color={active ? '#fff' : colors['text-secondary']} />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* ========== Tab 1: 采购管理 ========== */}
      {tab === 'purchase' && (
        <>
          {/* 套餐定价 */}
          <div style={{ marginBottom: space.xl }}>
            <h3 style={{
              margin: `0 0 ${space.md}px`, fontSize: typography.headline.fontSize,
              fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
            }}>套餐定价</h3>
            <div style={{ display: 'grid', gap: space.sm, gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
              {plans.map(p => (
                <div key={p.id} style={{
                  ...cardStyle,
                  display: 'flex', flexDirection: 'column',
                  background: colors['block-lilac'],
                }}>
                  <h4 style={{ margin: `0 0 ${space.sm}px`, fontSize: typography['card-title'].fontSize, fontWeight: 600, color: colors['text-primary'] }}>
                    {p.name}
                  </h4>
                  <div style={{ marginBottom: XS }}>
                    <span style={{ fontSize: 28, fontWeight: 600, color: colors['text-primary'] }}>¥{p.monthly_price}</span>
                    <span style={{ fontSize: 14, color: colors['text-secondary'] }}>/月</span>
                  </div>
                  <p style={{ margin: `0 0 ${XSS}px`, fontSize: typography['body-sm'].fontSize, color: colors['text-secondary'] }}>
                    年付 ¥{p.yearly_price}
                  </p>
                  <p style={{ fontSize: typography['body-sm'].fontSize, color: colors['text-secondary'], margin: `0 0 ${space.sm}px` }}>
                    {p.description}
                  </p>
                  <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: XSS }}>
                    {p.features.map(f => (
                      <div key={f} style={{ display: 'flex', alignItems: 'center', gap: XSS, fontSize: typography['body-sm'].fontSize, color: colors.success }}>
                        <IconCheck size={12} color={colors.success} /> {f}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 批量生成兑换码 */}
          <div style={{ ...cardStyle, marginBottom: space.xl, background: colors['block-cream'] }}>
            <h3 style={{
              margin: `0 0 ${space.md}px`, fontSize: typography.headline.fontSize,
              fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
            }}>批量生成兑换码</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: space.sm, alignItems: 'flex-end' }}>
              <div style={{ flex: '1 0 140px', minWidth: 120 }}>
                <span style={labelStyle}>套餐</span>
                <select value={codeForm.plan} onChange={e => setCodeForm(f => ({ ...f, plan: e.target.value }))} style={inputStyle}>
                  {plans.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div style={{ flex: '1 0 100px', minWidth: 80 }}>
                <span style={labelStyle}>时长(月)</span>
                <select value={codeForm.duration_months} onChange={e => setCodeForm(f => ({ ...f, duration_months: Number(e.target.value) }))} style={inputStyle}>
                  {[1, 3, 6, 12].map(m => <option key={m} value={m}>{m} 个月</option>)}
                </select>
              </div>
              <div style={{ flex: '1 0 100px', minWidth: 80 }}>
                <span style={labelStyle}>数量</span>
                <input type="number" min={1} max={1000} value={codeForm.count}
                  onChange={e => setCodeForm(f => ({ ...f, count: Number(e.target.value) }))} style={inputStyle} />
              </div>
              <div style={{ flex: '1 0 100px', minWidth: 80 }}>
                <span style={labelStyle}>过期天数</span>
                <input type="number" min={1} value={codeForm.expire_days || ''}
                  onChange={e => setCodeForm(f => ({ ...f, expire_days: e.target.value ? Number(e.target.value) : 0 }))} style={inputStyle} />
              </div>
              <button onClick={handleGenerate} disabled={generating} style={{ ...btnPrimary, opacity: generating ? 0.5 : 1 }}>
                {generating ? '生成中...' : '生成兑换码'}
              </button>
            </div>

            {/* 生成的兑换码 */}
            {generatedCodes && (
              <div style={{ marginTop: space.md, padding: space.md, background: colors.canvas, borderRadius: radius.md }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.sm }}>
                  <span style={{ fontSize: typography['body-sm'].fontSize, fontWeight: 500, color: colors['text-primary'] }}>
                    已生成 {generatedCodes.length} 个兑换码
                  </span>
                  <div style={{ display: 'flex', gap: XS }}>
                    <button onClick={copyAllCodes} style={btnSmallSecondary}>
                      <IconFile size={12} color={colors['text-secondary']} /> 复制全部
                    </button>
                    <button onClick={exportCodes} style={btnSmallSecondary}>
                      <IconRefresh size={12} color={colors['text-secondary']} /> 导出 CSV
                    </button>
                  </div>
                </div>
                <div style={{ maxHeight: 192, overflowY: 'auto', fontSize: typography['body-sm'].fontSize }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ color: colors['text-secondary'], fontSize: typography.caption.fontSize, textTransform: 'uppercase', letterSpacing: typography.eyebrow.letterSpacing }}>
                        <th style={{ textAlign: 'left', padding: `4px ${XSS}px` }}>兑换码</th>
                        <th style={{ textAlign: 'left', padding: `4px ${XSS}px` }}>套餐</th>
                        <th style={{ textAlign: 'left', padding: `4px ${XSS}px` }}>时长</th>
                      </tr>
                    </thead>
                    <tbody>
                      {generatedCodes.map(c => (
                        <tr key={c.code} style={{ borderTop: `1px solid ${colors['hairline-soft']}` }}>
                          <td style={{ padding: `6px ${XSS}px`, fontFamily: 'monospace', fontSize: 12 }}>{c.code}</td>
                          <td style={{ padding: `6px ${XSS}px` }}>{c.plan}</td>
                          <td style={{ padding: `6px ${XSS}px`, color: colors['text-secondary'] }}>{c.duration_months} 月</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          {/* 兑换码记录 */}
          <div style={cardStyle}>
            <h3 style={{
              margin: `0 0 ${space.md}px`, fontSize: typography.headline.fontSize,
              fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
            }}>兑换码记录</h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: typography['body-sm'].fontSize }}>
                <thead>
                  <tr style={{
                    borderBottom: `1px solid ${colors.hairline}`, color: colors['text-secondary'],
                    fontSize: typography.caption.fontSize, fontWeight: 500,
                    textTransform: 'uppercase', letterSpacing: typography.eyebrow.letterSpacing,
                    textAlign: 'left',
                  }}>
                    <th style={{ padding: `10px ${XS}px` }}>兑换码</th>
                    <th style={{ padding: `10px ${XS}px` }}>套餐</th>
                    <th style={{ padding: `10px ${XS}px` }}>状态</th>
                    <th style={{ padding: `10px ${XS}px` }}>使用者</th>
                    <th style={{ padding: `10px ${XS}px` }}>使用时间</th>
                    <th style={{ padding: `10px ${XS}px` }}>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {codes.map(c => (
                    <tr key={c.id} style={{ borderBottom: `1px solid ${colors['hairline-soft']}` }}>
                      <td style={{ padding: `10px ${XS}px`, fontFamily: 'monospace', fontSize: 12, color: colors['text-primary'] }}>{c.code}</td>
                      <td style={{ padding: `10px ${XS}px`, color: colors['text-primary'] }}>{c.plan}</td>
                      <td style={{ padding: `10px ${XS}px` }}><span style={statusBadgeStyle(c.status)}>{statusLabel(c.status)}</span></td>
                      <td style={{ padding: `10px ${XS}px`, color: colors['text-secondary'] }}>{c.used_by || '-'}</td>
                      <td style={{ padding: `10px ${XS}px`, color: colors['text-secondary'] }}>{c.used_at ? new Date(c.used_at).toLocaleDateString() : '-'}</td>
                      <td style={{ padding: `10px ${XS}px`, color: colors['text-secondary'] }}>{c.created_at ? new Date(c.created_at).toLocaleDateString() : '-'}</td>
                    </tr>
                  ))}
                  {codes.length === 0 && (
                    <tr><td colSpan={6} style={{ padding: 40, textAlign: 'center', color: colors['text-tertiary'] }}>暂无记录</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ========== Tab 2: 数据看板 ========== */}
      {tab === 'dashboard' && (
        <div style={cardStyle}>
          {dashboard ? (
            <>
              <h3 style={{
                margin: `0 0 ${space.md}px`, fontSize: typography.headline.fontSize,
                fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
              }}>{dashboard.school_name} 数据概览</h3>
              <div style={{ display: 'flex', gap: space.sm, flexWrap: 'wrap', marginBottom: space.xl }}>
                <div style={{ ...cardStyle, flex: 1, minWidth: 140, textAlign: 'center', background: green.bg }}>
                  <div style={{ fontSize: 28, fontWeight: 600, color: green.mid, lineHeight: 1.1 }}>{dashboard.total_classes}</div>
                  <span style={{ fontSize: typography.caption.fontSize, fontWeight: 500, textTransform: 'uppercase', letterSpacing: typography.eyebrow.letterSpacing, color: colors['text-tertiary'] }}>班级总数</span>
                </div>
                <div style={{ ...cardStyle, flex: 1, minWidth: 140, textAlign: 'center', background: colors['block-lime'] }}>
                  <div style={{ fontSize: 28, fontWeight: 600, color: colors.success, lineHeight: 1.1 }}>{dashboard.total_students}</div>
                  <span style={{ fontSize: typography.caption.fontSize, fontWeight: 500, textTransform: 'uppercase', letterSpacing: typography.eyebrow.letterSpacing, color: colors['text-tertiary'] }}>学生总数</span>
                </div>
                <div style={{ ...cardStyle, flex: 1, minWidth: 140, textAlign: 'center', background: colors['block-lilac'] }}>
                  <div style={{ fontSize: 28, fontWeight: 600, color: green.mid, lineHeight: 1.1 }}>{dashboard.total_teachers}</div>
                  <span style={{ fontSize: typography.caption.fontSize, fontWeight: 500, textTransform: 'uppercase', letterSpacing: typography.eyebrow.letterSpacing, color: colors['text-tertiary'] }}>教师总数</span>
                </div>
                <div style={{ ...cardStyle, flex: 1, minWidth: 140, textAlign: 'center', background: colors['block-cream'] }}>
                  <div style={{ fontSize: 28, fontWeight: 600, color: colors.warning, lineHeight: 1.1 }}>{dashboard.total_exams}</div>
                  <span style={{ fontSize: typography.caption.fontSize, fontWeight: 500, textTransform: 'uppercase', letterSpacing: typography.eyebrow.letterSpacing, color: colors['text-tertiary'] }}>考试总数</span>
                </div>
              </div>

              <h4 style={{ margin: `0 0 ${space.sm}px`, fontSize: typography['card-title'].fontSize, fontWeight: 600, color: colors['text-primary'] }}>班级统计</h4>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: typography['body-sm'].fontSize }}>
                  <thead>
                    <tr style={{
                      borderBottom: `1px solid ${colors.hairline}`, color: colors['text-secondary'],
                      fontSize: typography.caption.fontSize, fontWeight: 500,
                      textTransform: 'uppercase', letterSpacing: typography.eyebrow.letterSpacing,
                      textAlign: 'left',
                    }}>
                      <th style={{ padding: `10px ${XS}px` }}>班级</th><th style={{ padding: `10px ${XS}px` }}>学生数</th><th style={{ padding: `10px ${XS}px` }}>学习阶段</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.class_stats.map(cs => (
                      <tr key={cs.class_id} style={{ borderBottom: `1px solid ${colors['hairline-soft']}` }}>
                        <td style={{ padding: `10px ${XS}px`, fontWeight: 500, color: colors['text-primary'] }}>{cs.class_name}</td>
                        <td style={{ padding: `10px ${XS}px`, color: colors['text-secondary'] }}>{cs.student_count}</td>
                        <td style={{ padding: `10px ${XS}px`, color: colors['text-secondary'] }}>阶段 {cs.stage}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div style={{ textAlign: 'center', color: colors['text-tertiary'], padding: 40 }}>暂无数据</div>
          )}
        </div>
      )}

      {/* ========== Tab 3: 管理员管理 ========== */}
      {tab === 'admins' && (
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.md }}>
            <h3 style={{
              margin: 0, fontSize: typography.headline.fontSize,
              fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
            }}>学校管理员</h3>
            <button onClick={() => setShowCreateAdmin(!showCreateAdmin)} style={btnPrimary}>
              <IconPlus size={14} color="#fff" /> {showCreateAdmin ? '取消' : '添加管理员'}
            </button>
          </div>

          {showCreateAdmin && (
            <div style={{
              ...cardStyle, marginBottom: space.md, background: colors['block-lime'],
            }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: space.sm, alignItems: 'flex-end' }}>
                <div style={{ flex: '1 0 140px', minWidth: 120 }}>
                  <span style={labelStyle}>用户 ID</span>
                  <input type="number" value={adminForm.user_id}
                    onChange={e => setAdminForm(f => ({ ...f, user_id: e.target.value }))} style={inputStyle} />
                </div>
                <div style={{ flex: '1 0 160px', minWidth: 140 }}>
                  <span style={labelStyle}>学校名称</span>
                  <input value={adminForm.school_name}
                    onChange={e => setAdminForm(f => ({ ...f, school_name: e.target.value }))} style={inputStyle} />
                </div>
                <div style={{ flex: '1 0 140px', minWidth: 120 }}>
                  <span style={labelStyle}>联系电话</span>
                  <input value={adminForm.contact_phone}
                    onChange={e => setAdminForm(f => ({ ...f, contact_phone: e.target.value }))} style={inputStyle} />
                </div>
                <button onClick={handleCreateAdmin} disabled={creatingAdmin} style={{ ...btnPrimary, opacity: creatingAdmin ? 0.5 : 1 }}>
                  {creatingAdmin ? '创建中...' : '确认创建'}
                </button>
              </div>
            </div>
          )}

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: typography['body-sm'].fontSize }}>
              <thead>
                <tr style={{
                  borderBottom: `1px solid ${colors.hairline}`, color: colors['text-secondary'],
                  fontSize: typography.caption.fontSize, fontWeight: 500,
                  textTransform: 'uppercase', letterSpacing: typography.eyebrow.letterSpacing,
                  textAlign: 'left',
                }}>
                  <th style={{ padding: `10px ${XS}px` }}>用户 ID</th><th style={{ padding: `10px ${XS}px` }}>学校</th>
                  <th style={{ padding: `10px ${XS}px` }}>联系电话</th><th style={{ padding: `10px ${XS}px` }}>状态</th>
                  <th style={{ padding: `10px ${XS}px` }}>创建时间</th><th style={{ padding: `10px ${XS}px` }} />
                </tr>
              </thead>
              <tbody>
                {admins.map(a => (
                  <tr key={a.id} style={{ borderBottom: `1px solid ${colors['hairline-soft']}` }}>
                    <td style={{ padding: `10px ${XS}px`, color: colors['text-primary'] }}>{a.user_id}</td>
                    <td style={{ padding: `10px ${XS}px`, fontWeight: 500, color: colors['text-primary'] }}>{a.school_name}</td>
                    <td style={{ padding: `10px ${XS}px`, color: colors['text-secondary'] }}>{a.contact_phone || '-'}</td>
                    <td style={{ padding: `10px ${XS}px` }}>
                      <span style={statusBadgeStyle(a.is_active ? 'active' : 'disabled')}>
                        {a.is_active ? '启用' : '禁用'}
                      </span>
                    </td>
                    <td style={{ padding: `10px ${XS}px`, color: colors['text-secondary'] }}>
                      {new Date(a.created_at).toLocaleDateString()}
                    </td>
                    <td style={{ padding: `10px ${XS}px` }}>
                      <button onClick={() => handleToggleAdmin(a.user_id)} style={{
                        ...btnSmallSecondary, fontSize: 12,
                        color: a.is_active ? colors.warning : colors.success,
                        borderColor: (a.is_active ? colors.warning : colors.success) + '40',
                      }}>
                        {a.is_active ? '禁用' : '启用'}
                      </button>
                    </td>
                  </tr>
                ))}
                {admins.length === 0 && (
                  <tr><td colSpan={6} style={{ padding: 40, textAlign: 'center', color: colors['text-tertiary'] }}>暂无管理员</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
