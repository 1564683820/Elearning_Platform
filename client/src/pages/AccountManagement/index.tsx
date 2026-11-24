// 账号管理 — 注册学生/教师账号，查看和管理所有用户，支持批量删除
// 含邀请码管理 Tab：查看/生成/刷新邀请码
import { useEffect, useState } from 'react';
import client from '../../api/client';
import {
  colors, radius, typography, space, cardStyle, btnPrimary, btnSecondary,
  inputStyle, labelStyle, btnSmall, btnSmallSecondary, btnDanger,
  IconPlus, IconX, IconSearch,
} from '../../design-system';

// ── 用户管理类型 ──
interface UserItem {
  id: number;
  account: string;
  username: string;
  nickname: string;
  role: string;
  membership: string;
  stage: number;
  email: string;
  created_at: string;
  membership_expire: string;
}
interface PageData {
  items: UserItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ── 邀请码管理类型 ──
interface InviteCodeItem {
  id: number;
  code: string;
  role: string;
  role_label: string;
  is_used: boolean;
  used_by: number | null;
  used_by_name: string;
  used_at: string;
  created_by: number;
  created_by_name: string;
  created_at: string;
}
interface InviteCodePage {
  items: InviteCodeItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ── 班级管理类型 ──
interface AdminClassItem {
  id: number;
  name: string;
  description: string;
  invite_code: string;
  created_by: number;
  created_by_name: string;
  stage: number;
  student_count: number;
  is_active: number;
  teachers: { teacher_id: number; teacher_name: string }[];
  created_at: string;
}
interface AdminClassPage {
  items: AdminClassItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

const ROLE_LABELS: Record<string, { label: string; color: string }> = {
  student: { label: '学生', color: '#3b82f6' },
  teacher: { label: '教师', color: '#2d7d46' },
  admin: { label: '管理者', color: '#dc2626' },
};
const STAGE_LABELS: Record<number, string> = {
  1: '小学', 2: '初中', 3: '高中', 4: '四六级',
};

// ── 公共样式 ──
const tabStyle = (active: boolean): React.CSSProperties => ({
  padding: '8px 24px', borderRadius: radius.pill, cursor: 'pointer',
  fontSize: 14, fontWeight: active ? 600 : 400,
  background: active ? colors.primary : colors.canvas,
  color: active ? '#fff' : colors['text-secondary'],
  border: `1px solid ${active ? colors.primary : colors.hairline}`,
  transition: 'all 0.15s',
});

export default function AccountManagement() {
  const [tab, setTab] = useState<'users' | 'invite-codes' | 'classes'>('users');

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.lg }}>
        <h1 style={{ ...typography.headline }}>账号管理</h1>
      </div>

      {/* Tab 切换 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: space.lg, flexWrap: 'wrap' }}>
        <div style={tabStyle(tab === 'users')} onClick={() => setTab('users')}>用户管理</div>
        <div style={tabStyle(tab === 'invite-codes')} onClick={() => setTab('invite-codes')}>邀请码管理</div>
        <div style={tabStyle(tab === 'classes')} onClick={() => setTab('classes')}>班级管理</div>
      </div>

      {tab === 'users' ? <UserManagement /> : tab === 'invite-codes' ? <InviteCodeManagement /> : <ClassManagement />}
    </div>
  );
}

// ══════════════════════════════════════════════════
// 用户管理子组件
// ══════════════════════════════════════════════════
function UserManagement() {
  const [data, setData] = useState<PageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [roleFilter, setRoleFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ username: '', password: '', nickname: '', role: 'student', stage: 1 });
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const fetchUsers = () => {
    setLoading(true);
    const params: any = { page, page_size: 20 };
    if (roleFilter) params.role = roleFilter;
    if (search) params.search = search;
    client.get('/admin/users', { params })
      .then((res) => setData(res.data.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchUsers(); }, [page, roleFilter]);

  const handleSearch = () => { setPage(1); fetchUsers(); };

  const handleCreate = async () => {
    if (!createForm.username || !createForm.password) {
      setCreateError('用户名和密码不能为空');
      return;
    }
    setCreateLoading(true);
    setCreateError('');
    try {
      await client.post('/admin/users', createForm);
      setShowCreate(false);
      setCreateForm({ username: '', password: '', nickname: '', role: 'student', stage: 1 });
      setSelectedIds(new Set());
      fetchUsers();
    } catch (err: any) {
      setCreateError(err.message || '创建失败');
    } finally {
      setCreateLoading(false);
    }
  };

  const handleBatchDelete = async () => {
    setDeleteLoading(true);
    try {
      await client.delete('/admin/users/batch', { data: { user_ids: Array.from(selectedIds) } });
      setShowDeleteConfirm(false);
      setSelectedIds(new Set());
      fetchUsers();
    } catch (err: any) {
      alert(err.message || '删除失败');
    } finally {
      setDeleteLoading(false);
    }
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (!data?.items) return;
    if (selectedIds.size === data.items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(data.items.map((u) => u.id)));
    }
  };

  useEffect(() => { setSelectedIds(new Set()); }, [page, roleFilter]);

  return (
    <div>
      {/* 筛选栏 */}
      <div style={{ display: 'flex', gap: space.sm, marginBottom: space.lg, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {['', 'student', 'teacher', 'admin'].map((r) => (
            <div
              key={r}
              onClick={() => { setRoleFilter(r); setPage(1); }}
              style={{
                padding: '6px 16px', borderRadius: radius.pill, cursor: 'pointer',
                fontSize: 13, fontWeight: roleFilter === r ? 500 : 400,
                background: roleFilter === r ? colors.primary : colors.canvas,
                color: roleFilter === r ? '#fff' : colors['text-secondary'],
                border: `1px solid ${roleFilter === r ? colors.primary : colors.hairline}`,
                transition: 'all 0.15s',
              }}
            >
              {r ? (ROLE_LABELS[r]?.label || r) : '全部'}
            </div>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            placeholder="搜索用户名/昵称..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            style={{ ...inputStyle, width: 200, marginBottom: 0 }}
          />
          <button style={btnSmallSecondary} onClick={handleSearch}>
            <IconSearch size={14} /> 搜索
          </button>
          <button style={btnPrimary} onClick={() => setShowCreate(true)}>
            <IconPlus size={14} color="#fff" /> 新建账号
          </button>
          {selectedIds.size > 0 && (
            <button
              style={{ ...btnSmall, background: colors.danger, color: '#fff', border: 'none' }}
              onClick={() => setShowDeleteConfirm(true)}
            >
              删除 {selectedIds.size} 项
            </button>
          )}
        </div>
      </div>

      {/* 用户列表 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: colors['text-secondary'] }}>加载中...</div>
      ) : (
        <div style={cardStyle}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${colors.hairline}`, color: colors['text-secondary'], fontSize: 12 }}>
                <th style={{ padding: '10px 12px', textAlign: 'left', width: 40 }}>
                  <input type="checkbox" checked={data?.items ? selectedIds.size === data.items.length : false}
                    onChange={toggleSelectAll}
                    style={{ cursor: 'pointer', accentColor: colors.primary }} />
                </th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>登录账号</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>用户名</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>昵称</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>角色</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>会员</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>学段</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((u) => {
                const roleInfo = ROLE_LABELS[u.role] || { label: u.role, color: '#888' };
                return (
                  <tr key={u.id} style={{ borderBottom: `1px solid ${colors['hairline-soft']}` }}>
                    <td style={{ padding: '10px 12px' }}>
                      <input type="checkbox" checked={selectedIds.has(u.id)}
                        onChange={() => toggleSelect(u.id)}
                        style={{ cursor: 'pointer', accentColor: colors.primary }} />
                    </td>
                    <td style={{ padding: '10px 12px', color: colors['text-secondary'] }}>{u.account || '-'}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 500 }}>{u.username}</td>
                    <td style={{ padding: '10px 12px' }}>{u.nickname}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{
                        padding: '2px 10px', borderRadius: radius.pill, fontSize: 12,
                        background: `${roleInfo.color}15`, color: roleInfo.color, fontWeight: 500,
                      }}>
                        {roleInfo.label}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{
                        padding: '2px 10px', borderRadius: radius.pill, fontSize: 12,
                        background: u.membership !== 'free' ? '#e6f7e6' : '#f5f5f5',
                        color: u.membership !== 'free' ? '#2d7d46' : '#888', fontWeight: 500,
                      }}>
                        {u.membership === 'free' ? '免费' : u.membership}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px', color: colors['text-secondary'] }}>{STAGE_LABELS[u.stage] || u.stage}</td>
                    <td style={{ padding: '10px 12px', color: colors['text-secondary'], fontSize: 13 }}>
                      {u.created_at ? new Date(u.created_at).toLocaleDateString('zh-CN') : '-'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {(!data?.items || data.items.length === 0) && (
            <div style={{ textAlign: 'center', padding: 40, color: colors['text-secondary'] }}>暂无用户数据</div>
          )}
          {data && data.total_pages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, padding: '16px 0 0' }}>
              {Array.from({ length: data.total_pages }, (_, i) => i + 1).map((p) => (
                <div key={p} onClick={() => setPage(p)}
                  style={{
                    width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    borderRadius: radius.md, cursor: 'pointer', fontSize: 13,
                    background: p === page ? colors.primary : 'transparent',
                    color: p === page ? '#fff' : colors['text-secondary'],
                    fontWeight: p === page ? 600 : 400,
                  }}>
                  {p}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 新建账号弹窗 */}
      {showCreate && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{ background: '#fff', borderRadius: radius.lg, padding: space.xl, width: 420, boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.lg }}>
              <h2 style={{ ...typography['card-title'], margin: 0 }}>新建账号</h2>
              <div onClick={() => setShowCreate(false)} style={{ cursor: 'pointer', padding: 4 }}>
                <IconX size={20} color="#888" />
              </div>
            </div>
            <label style={labelStyle}>用户名 *</label>
            <input style={inputStyle} placeholder="用户名" value={createForm.username}
              onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })} />
            <label style={labelStyle}>密码 *</label>
            <input style={inputStyle} type="password" placeholder="密码" value={createForm.password}
              onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })} />
            <label style={labelStyle}>昵称</label>
            <input style={inputStyle} placeholder="昵称（可选）" value={createForm.nickname}
              onChange={(e) => setCreateForm({ ...createForm, nickname: e.target.value })} />
            <label style={labelStyle}>角色</label>
            <div style={{ display: 'flex', gap: 8, marginBottom: space.md }}>
              {[
                { value: 'student', label: '学生' },
                { value: 'teacher', label: '教师' },
              ].map((r) => (
                <div key={r.value} onClick={() => setCreateForm({ ...createForm, role: r.value })}
                  style={{
                    flex: 1, textAlign: 'center', padding: '8px 0', borderRadius: radius.md, cursor: 'pointer',
                    background: createForm.role === r.value ? colors.primary : colors['surface-soft'],
                    color: createForm.role === r.value ? '#fff' : colors['text-secondary'],
                    fontWeight: createForm.role === r.value ? 600 : 400,
                    border: `1px solid ${createForm.role === r.value ? colors.primary : colors.hairline}`,
                  }}>
                  {r.label}
                </div>
              ))}
            </div>
            {createError && <p style={{ color: colors.danger, fontSize: 13, marginBottom: 12 }}>{createError}</p>}
            <button style={{ ...btnPrimary, width: '100%' }} onClick={handleCreate} disabled={createLoading}>
              {createLoading ? '创建中...' : '创建账号'}
            </button>
          </div>
        </div>
      )}

      {/* 批量删除确认弹窗 */}
      {showDeleteConfirm && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{ background: '#fff', borderRadius: radius.lg, padding: space.xl, width: 400, boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
            <h2 style={{ ...typography['card-title'], margin: '0 0 8px' }}>确认批量删除</h2>
            <p style={{ color: colors['text-secondary'], fontSize: 14, margin: '0 0 20px', lineHeight: 1.6 }}>
              确定要删除选中的 <strong style={{ color: colors.danger }}>{selectedIds.size}</strong> 个用户吗？此操作不可撤销。
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button style={btnSecondary} onClick={() => setShowDeleteConfirm(false)} disabled={deleteLoading}>取消</button>
              <button style={{ ...btnDanger, width: 'auto' }} onClick={handleBatchDelete} disabled={deleteLoading}>
                {deleteLoading ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════
// 邀请码管理子组件
// ══════════════════════════════════════════════════
function InviteCodeManagement() {
  const [data, setData] = useState<InviteCodePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [roleFilter, setRoleFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState('');
  const [createCount, setCreateCount] = useState(1);
  const [createRole, setCreateRole] = useState('student');
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const fetchInviteCodes = () => {
    setLoading(true);
    const params: any = { page, page_size: 20 };
    if (roleFilter) params.role = roleFilter;
    client.get('/admin/invite-codes', { params })
      .then((res) => setData(res.data.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchInviteCodes(); }, [page, roleFilter]);

  const handleCreate = async () => {
    setCreateLoading(true);
    setCreateError('');
    try {
      await client.post('/admin/invite-codes', { count: createCount, role: createRole });
      setShowCreate(false);
      setCreateCount(1);
      setCreateRole('student');
      setPage(1);
      fetchInviteCodes();
    } catch (err: any) {
      setCreateError(err.message || '生成失败');
    } finally {
      setCreateLoading(false);
    }
  };

  const handleRefresh = async (id: number) => {
    try {
      await client.post(`/admin/invite-codes/${id}/refresh`);
      fetchInviteCodes();
    } catch (err: any) {
      alert(err.message || '刷新失败');
    }
  };

  const handleBatchDelete = async () => {
    setDeleteLoading(true);
    try {
      await client.post('/admin/invite-codes/batch-delete', { ids: Array.from(selectedIds) });
      setShowDeleteConfirm(false);
      setSelectedIds(new Set());
      fetchInviteCodes();
    } catch (err: any) {
      alert(err.message || '删除失败');
    } finally {
      setDeleteLoading(false);
    }
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (!data?.items) return;
    if (selectedIds.size === data.items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(data.items.map((ic) => ic.id)));
    }
  };

  useEffect(() => { setSelectedIds(new Set()); }, [page, roleFilter]);

  const handleCopy = (code: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(code).then(() => {
        alert('邀请码已复制：' + code);
      });
    } else {
      const ta = document.createElement('textarea');
      ta.value = code;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      alert('邀请码已复制：' + code);
    }
  };

  const ROLE_TAG_COLORS: Record<string, { bg: string; color: string }> = {
    student: { bg: '#e6f0ff', color: '#3b82f6' },
    teacher: { bg: '#e6f7e6', color: '#2d7d46' },
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.lg }}>
        <p style={{ color: colors['text-secondary'], fontSize: 13, margin: 0 }}>
          邀请码区分学生和教师角色，注册时验证角色匹配，使用后自动清除。支持批量删除。
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          {selectedIds.size > 0 && (
            <button
              style={{ ...btnSmall, background: colors.danger, color: '#fff', border: 'none' }}
              onClick={() => setShowDeleteConfirm(true)}
            >
              删除 {selectedIds.size} 项
            </button>
          )}
          <button style={btnPrimary} onClick={() => { setShowCreate(true); setCreateCount(1); setCreateRole('student'); }}>
            <IconPlus size={14} color="#fff" /> 生成邀请码
          </button>
        </div>
      </div>

      {/* 角色筛选 */}
      <div style={{ display: 'flex', gap: 6, marginBottom: space.md }}>
        {['', 'student', 'teacher'].map((r) => {
          const label = r ? (r === 'student' ? '学生邀请码' : '教师邀请码') : '全部';
          return (
            <div
              key={r}
              onClick={() => { setRoleFilter(r); setPage(1); }}
              style={{
                padding: '6px 16px', borderRadius: radius.pill, cursor: 'pointer',
                fontSize: 13, fontWeight: roleFilter === r ? 500 : 400,
                background: roleFilter === r ? colors.primary : colors.canvas,
                color: roleFilter === r ? '#fff' : colors['text-secondary'],
                border: `1px solid ${roleFilter === r ? colors.primary : colors.hairline}`,
                transition: 'all 0.15s',
              }}
            >
              {label}
            </div>
          );
        })}
      </div>

      {/* 邀请码列表 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: colors['text-secondary'] }}>加载中...</div>
      ) : (
        <div style={cardStyle}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${colors.hairline}`, color: colors['text-secondary'], fontSize: 12 }}>
                <th style={{ padding: '10px 12px', textAlign: 'left', width: 40 }}>
                  <input type="checkbox" checked={data?.items ? selectedIds.size === data.items.length : false}
                    onChange={toggleSelectAll}
                    style={{ cursor: 'pointer', accentColor: colors.primary }} />
                </th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>邀请码</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>角色</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>状态</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>使用者</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>使用时间</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>创建人</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>创建时间</th>
                <th style={{ padding: '10px 12px', textAlign: 'center' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((ic) => {
                const tagColor = ROLE_TAG_COLORS[ic.role] || { bg: '#f5f5f5', color: '#888' };
                return (
                  <tr key={ic.id} style={{ borderBottom: `1px solid ${colors['hairline-soft']}` }}>
                    <td style={{ padding: '10px 12px' }}>
                      <input type="checkbox" checked={selectedIds.has(ic.id)}
                        onChange={() => toggleSelect(ic.id)}
                        style={{ cursor: 'pointer', accentColor: colors.primary }} />
                    </td>
                    <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontWeight: 600, fontSize: 15, letterSpacing: '2px' }}>
                      {ic.is_used ? <span style={{ color: colors['text-tertiary'] }}>--已使用--</span> : ic.code}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{
                        padding: '2px 10px', borderRadius: radius.pill, fontSize: 12,
                        background: tagColor.bg, color: tagColor.color, fontWeight: 500,
                      }}>
                        {ic.role_label}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{
                        padding: '2px 10px', borderRadius: radius.pill, fontSize: 12,
                        background: ic.is_used ? '#fef2f2' : '#e6f7e6',
                        color: ic.is_used ? '#ef4444' : '#2d7d46',
                        fontWeight: 500,
                      }}>
                        {ic.is_used ? '已使用' : '未使用'}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px', color: colors['text-secondary'] }}>
                      {ic.used_by_name || '-'}
                    </td>
                    <td style={{ padding: '10px 12px', color: colors['text-secondary'], fontSize: 13 }}>
                      {ic.used_at ? new Date(ic.used_at).toLocaleDateString('zh-CN') : '-'}
                    </td>
                    <td style={{ padding: '10px 12px', color: colors['text-secondary'] }}>
                      {ic.created_by_name}
                    </td>
                    <td style={{ padding: '10px 12px', color: colors['text-secondary'], fontSize: 13 }}>
                      {ic.created_at ? new Date(ic.created_at).toLocaleDateString('zh-CN') : '-'}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
                        <button style={btnSmallSecondary} onClick={() => handleCopy(ic.code)}>复制</button>
                        {!ic.is_used && (
                          <button style={btnSmallSecondary} onClick={() => handleRefresh(ic.id)}>刷新</button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {(!data?.items || data.items.length === 0) && (
            <div style={{ textAlign: 'center', padding: 40, color: colors['text-secondary'] }}>
              暂无邀请码数据，点击右上角「生成邀请码」创建
            </div>
          )}

          {data && data.total_pages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, padding: '16px 0 0' }}>
              {Array.from({ length: data.total_pages }, (_, i) => i + 1).map((p) => (
                <div key={p} onClick={() => setPage(p)}
                  style={{
                    width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    borderRadius: radius.md, cursor: 'pointer', fontSize: 13,
                    background: p === page ? colors.primary : 'transparent',
                    color: p === page ? '#fff' : colors['text-secondary'],
                    fontWeight: p === page ? 600 : 400,
                  }}>
                  {p}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 生成邀请码弹窗 */}
      {showCreate && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{ background: '#fff', borderRadius: radius.lg, padding: space.xl, width: 420, boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.lg }}>
              <h2 style={{ ...typography['card-title'], margin: 0 }}>生成邀请码</h2>
              <div onClick={() => setShowCreate(false)} style={{ cursor: 'pointer', padding: 4 }}>
                <IconX size={20} color="#888" />
              </div>
            </div>

            <p style={{ color: colors['text-secondary'], fontSize: 14, marginBottom: space.lg, lineHeight: 1.6 }}>
              选择角色生成对应类型的邀请码，注册时系统会自动验证角色匹配。
            </p>

            <label style={labelStyle}>角色类型</label>
            <div style={{ display: 'flex', gap: 8, marginBottom: space.md }}>
              {[
                { value: 'student', label: '学生', icon: '🎓', color: '#3b82f6' },
                { value: 'teacher', label: '教师', icon: '👨‍🏫', color: '#2d7d46' },
              ].map((r) => (
                <div key={r.value} onClick={() => setCreateRole(r.value)}
                  style={{
                    flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                    padding: '10px 0', borderRadius: radius.md, cursor: 'pointer',
                    background: createRole === r.value ? `${r.color}15` : colors['surface-soft'],
                    color: createRole === r.value ? r.color : colors['text-secondary'],
                    fontWeight: createRole === r.value ? 600 : 400,
                    border: `2px solid ${createRole === r.value ? r.color : colors.hairline}`,
                    transition: 'all 0.15s',
                    fontSize: 14,
                  }}>
                  <span style={{ fontSize: 18 }}>{r.icon}</span>
                  {r.label}
                </div>
              ))}
            </div>

            <label style={labelStyle}>生成数量</label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: space.md }}>
              <button
                onClick={() => setCreateCount(Math.max(1, createCount - 1))}
                style={{
                  width: 36, height: 36, borderRadius: radius.md,
                  border: `1px solid ${colors.hairline}`, background: colors['surface-soft'],
                  cursor: 'pointer', fontSize: 18, fontWeight: 600,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: colors['text-primary'],
                }}
              >−</button>
              <input
                type="number"
                min={1}
                max={50}
                value={createCount}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (!isNaN(v)) setCreateCount(Math.max(1, Math.min(50, v)));
                }}
                style={{
                  ...inputStyle, width: 80, textAlign: 'center', marginBottom: 0,
                  fontSize: 16, fontWeight: 600,
                }}
              />
              <button
                onClick={() => setCreateCount(Math.min(50, createCount + 1))}
                style={{
                  width: 36, height: 36, borderRadius: radius.md,
                  border: `1px solid ${colors.hairline}`, background: colors['surface-soft'],
                  cursor: 'pointer', fontSize: 18, fontWeight: 600,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: colors['text-primary'],
                }}
              >+</button>
              <span style={{ color: colors['text-secondary'], fontSize: 13, marginLeft: 4 }}>个</span>
            </div>

            <div style={{ marginBottom: space.md, padding: '10px 14px', background: '#f0f9ff', borderRadius: radius.md, fontSize: 13, color: '#3b82f6' }}>
              即将生成 <strong>{createCount}</strong> 个
              <strong>{createRole === 'student' ? '学生' : '教师'}</strong>邀请码
            </div>

            {createError && <p style={{ color: colors.danger, fontSize: 13, marginBottom: 12 }}>{createError}</p>}

            <button style={{ ...btnPrimary, width: '100%' }} onClick={handleCreate} disabled={createLoading}>
              {createLoading ? `生成中...` : `批量生成 ${createCount} 个${createRole === 'student' ? '学生' : '教师'}邀请码`}
            </button>
          </div>
        </div>
      )}

      {/* 批量删除确认弹窗 */}
      {showDeleteConfirm && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{ background: '#fff', borderRadius: radius.lg, padding: space.xl, width: 420, boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
            <h2 style={{ ...typography['card-title'], margin: '0 0 8px' }}>确认批量删除</h2>
            <p style={{ color: colors['text-secondary'], fontSize: 14, margin: '0 0 20px', lineHeight: 1.6 }}>
              确定要删除选中的 <strong style={{ color: colors.danger }}>{selectedIds.size}</strong> 个邀请码吗？
              删除后该邀请码将自动失效，不可恢复。
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button style={btnSecondary} onClick={() => setShowDeleteConfirm(false)} disabled={deleteLoading}>取消</button>
              <button style={{ ...btnDanger, width: 'auto' }} onClick={handleBatchDelete} disabled={deleteLoading}>
                {deleteLoading ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════
// 班级管理子组件
// ══════════════════════════════════════════════════
function ClassManagement() {
  const [data, setData] = useState<AdminClassPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [teacherId, setTeacherId] = useState<string>('');
  const [search, setSearch] = useState('');
  const [teachers, setTeachers] = useState<{ id: number; name: string }[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<AdminClassItem | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // 加载教师列表（用于筛选下拉）
  const fetchTeachers = () => {
    client.get('/admin/users', { params: { page_size: 200, role: 'teacher' } })
      .then((res) => {
        const list = res.data.data?.items || [];
        setTeachers(list.map((u: any) => ({ id: u.id, name: u.nickname || u.username })));
      })
      .catch(() => {});
  };

  const fetchClasses = () => {
    setLoading(true);
    const params: any = { page, page_size: 20 };
    if (teacherId !== '') params.teacher_id = teacherId;
    if (search) params.search = search;
    client.get('/admin/classes', { params })
      .then((res) => setData(res.data.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchClasses(); }, [page, teacherId]);
  useEffect(() => { fetchTeachers(); }, []);

  const handleSearch = () => { setPage(1); fetchClasses(); };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      await client.delete(`/admin/classes/${deleteTarget.id}`);
      setDeleteTarget(null);
      fetchClasses();
    } catch (err: any) {
      alert(err.message || '删除失败');
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <div>
      {/* 筛选栏 */}
      <div style={{ display: 'flex', gap: space.sm, marginBottom: space.lg, alignItems: 'center', flexWrap: 'wrap' }}>
        <select
          value={teacherId}
          onChange={(e) => { setTeacherId(e.target.value || ''); setPage(1); }}
          style={{ ...inputStyle, width: 180, marginBottom: 0 }}
        >
          <option value="">全部教师</option>
          {teachers.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
        <input
          placeholder="搜索班级名称..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          style={{ ...inputStyle, width: 200, marginBottom: 0 }}
        />
        <button style={btnSmallSecondary} onClick={handleSearch}>
          <IconSearch size={14} /> 搜索
        </button>
        <div style={{ flex: 1 }} />
        <span style={{ color: colors['text-secondary'], fontSize: 13 }}>
          共 {data?.total ?? 0} 个班级
        </span>
      </div>

      {/* 班级列表 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: colors['text-secondary'] }}>加载中...</div>
      ) : (
        <div style={cardStyle}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${colors.hairline}`, color: colors['text-secondary'], fontSize: 12 }}>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>ID</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>班级名称</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>教师</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>学生数</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>邀请码</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>创建人</th>
                <th style={{ padding: '10px 12px', textAlign: 'left' }}>创建时间</th>
                <th style={{ padding: '10px 12px', textAlign: 'center' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((cls) => (
                <tr key={cls.id} style={{ borderBottom: `1px solid ${colors['hairline-soft']}` }}>
                  <td style={{ padding: '10px 12px', color: colors['text-secondary'] }}>{cls.id}</td>
                  <td style={{ padding: '10px 12px', fontWeight: 500 }}>{cls.name}</td>
                  <td style={{ padding: '10px 12px' }}>
                    {cls.teachers.length > 0
                      ? cls.teachers.map((t) => t.teacher_name).join('、')
                      : <span style={{ color: colors['text-tertiary'] }}>无</span>}
                  </td>
                  <td style={{ padding: '10px 12px', color: colors['text-secondary'] }}>{cls.student_count}</td>
                  <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 13, letterSpacing: '1px' }}>
                    {cls.invite_code}
                  </td>
                  <td style={{ padding: '10px 12px', color: colors['text-secondary'] }}>
                    {cls.created_by_name || cls.created_by}
                  </td>
                  <td style={{ padding: '10px 12px', color: colors['text-secondary'], fontSize: 13 }}>
                    {cls.created_at ? new Date(cls.created_at).toLocaleDateString('zh-CN') : '-'}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                    <button
                      style={{ ...btnSmall, background: colors.danger, color: '#fff', border: 'none' }}
                      onClick={() => setDeleteTarget(cls)}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(!data?.items || data.items.length === 0) && (
            <div style={{ textAlign: 'center', padding: 40, color: colors['text-secondary'] }}>暂无班级数据</div>
          )}
          {data && data.total_pages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, padding: '16px 0 0' }}>
              {Array.from({ length: data.total_pages }, (_, i) => i + 1).map((p) => (
                <div key={p} onClick={() => setPage(p)}
                  style={{
                    width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    borderRadius: radius.md, cursor: 'pointer', fontSize: 13,
                    background: p === page ? colors.primary : 'transparent',
                    color: p === page ? '#fff' : colors['text-secondary'],
                    fontWeight: p === page ? 600 : 400,
                  }}>
                  {p}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 删除确认弹窗 */}
      {deleteTarget && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{ background: '#fff', borderRadius: radius.lg, padding: space.xl, width: 420, boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
            <h2 style={{ ...typography['card-title'], margin: '0 0 8px' }}>确认删除班级</h2>
            <p style={{ color: colors['text-secondary'], fontSize: 14, margin: '0 0 12px', lineHeight: 1.6 }}>
              确定要删除班级 <strong style={{ color: colors.danger }}>{deleteTarget.name}</strong> 吗？
            </p>
            <div style={{ padding: '12px 16px', background: '#fff8e1', borderRadius: radius.md, marginBottom: space.lg, fontSize: 13, color: '#e65100', lineHeight: 1.6 }}>
              此操作将同时删除该班级的{deleteTarget.student_count}名学生关联记录，不可撤销。
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button style={btnSecondary} onClick={() => setDeleteTarget(null)} disabled={deleteLoading}>取消</button>
              <button style={{ ...btnDanger, width: 'auto' }} onClick={handleDelete} disabled={deleteLoading}>
                {deleteLoading ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
