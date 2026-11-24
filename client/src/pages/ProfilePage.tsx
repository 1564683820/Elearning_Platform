// 个人信息页面 — 可编辑昵称/头像、显示账号、修改密码、权益额度、退出登录
import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  colors, green, radius, space, shadows,
  IconBack, IconPpt, IconGraduation, IconShield, IconEdit,
} from '../design-system';
import { membershipApi, MyQuotaInfo } from '../api/membership';
import { updateProfile, changePassword } from '../api/user';
import { clearTeacherChatDrafts } from '../shared/ChatAttachments';
import { clearTeacherPaperCreations } from '../shared/exams/paperCreationRecovery';

export default function ProfilePage() {
  const navigate = useNavigate();
  const [quota, setQuota] = useState<MyQuotaInfo | null>(null);
  const [nickname, setNickname] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [editingNickname, setEditingNickname] = useState(false);
  const [showAvatarInput, setShowAvatarInput] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const nickInputRef = useRef<HTMLInputElement>(null);

  // 修改密码
  const [showPwdForm, setShowPwdForm] = useState(false);
  const [oldPwd, setOldPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [savingPwd, setSavingPwd] = useState(false);
  const [pwdMsg, setPwdMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 从 localStorage 读取用户信息
  const user = (() => {
    try {
      const raw = localStorage.getItem('user');
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  })();

  // 初始化：昵称默认为账号（username）
  useEffect(() => {
    if (user) {
      setNickname(user.nickname || user.username || '');
      setAvatarUrl(user.avatar_url || '');
    }
  }, [user]);

  const fetchQuota = useCallback(async () => {
    try {
      const data = await membershipApi.getMyQuota();
      setQuota(data);
    } catch {
      // 静默失败
    }
  }, []);

  useEffect(() => {
    if (user) fetchQuota();
  }, [user, fetchQuota]);

  // 编辑昵称时自动聚焦
  useEffect(() => {
    if (editingNickname && nickInputRef.current) {
      nickInputRef.current.focus();
      nickInputRef.current.select();
    }
  }, [editingNickname]);

  const handleSaveNickname = async () => {
    const trimmed = nickname.trim();
    if (!trimmed || trimmed === (user?.nickname || user?.username)) {
      setEditingNickname(false);
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateProfile({ nickname: trimmed });
      // 更新 localStorage
      const stored = JSON.parse(localStorage.getItem('user') || '{}');
      stored.nickname = updated.nickname;
      localStorage.setItem('user', JSON.stringify(stored));
      setNickname(updated.nickname || trimmed);
      setEditingNickname(false);
      setMessage({ type: 'success', text: '昵称已更新' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message || '保存失败' });
    } finally {
      setSaving(false);
    }
  };

  // 头像 URL 保存
  const handleSaveAvatar = async () => {
    const trimmed = avatarUrl.trim();
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateProfile({ avatar_url: trimmed || null });
      const stored = JSON.parse(localStorage.getItem('user') || '{}');
      stored.avatar_url = updated.avatar_url;
      localStorage.setItem('user', JSON.stringify(stored));
      setAvatarUrl(updated.avatar_url || '');
      setShowAvatarInput(false);
      setMessage({ type: 'success', text: '头像已更新' });
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message || '保存失败' });
    } finally {
      setSaving(false);
    }
  };

  const displayName = nickname || user?.username || '用户';
  const avatarChar = displayName[0].toUpperCase();

  const ppt = quota?.quotas?.ai_ppt;
  const exam = quota?.quotas?.ai_exam;

  function quotaBadge(unlimited: boolean, remaining: number): string {
    if (unlimited) return '无限';
    if (remaining <= 0) return '已用完';
    return `剩 ${remaining} 次`;
  }

  function quotaColor(unlimited: boolean, remaining: number): string {
    if (unlimited) return green.strong;
    if (remaining <= 0) return colors.danger;
    if (remaining <= 5) return colors.warning;
    return green.strong;
  }

  const handleLogout = () => {
    clearTeacherChatDrafts();
    clearTeacherPaperCreations();
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const handleChangePassword = async () => {
    const trimmed = newPwd.trim();
    if (!oldPwd || !newPwd) {
      setPwdMsg({ type: 'error', text: '请填写旧密码和新密码' });
      return;
    }
    if (trimmed.length < 6) {
      setPwdMsg({ type: 'error', text: '新密码至少 6 位' });
      return;
    }
    if (trimmed !== confirmPwd) {
      setPwdMsg({ type: 'error', text: '两次输入的新密码不一致' });
      return;
    }
    setSavingPwd(true);
    setPwdMsg(null);
    try {
      await changePassword(oldPwd, trimmed);
      setPwdMsg({ type: 'success', text: '密码已更新，下次登录请使用新密码' });
      setOldPwd('');
      setNewPwd('');
      setConfirmPwd('');
      setTimeout(() => setShowPwdForm(false), 2000);
    } catch (e: any) {
      setPwdMsg({ type: 'error', text: e.message || '修改密码失败' });
    } finally {
      setSavingPwd(false);
    }
  };

  return (
    <div style={{ maxWidth: 600, margin: '0 auto', paddingBottom: 48 }}>
      {/* 顶部标题栏 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        marginBottom: space.xl,
      }}>
        <button
          onClick={() => navigate(-1)}
          style={{
            width: 36, height: 36, borderRadius: '50%',
            border: `1px solid ${colors.hairline}`,
            background: colors.canvas,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', transition: 'background 0.15s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = colors['surface-soft']; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = colors.canvas; }}
        >
          <IconBack size={18} color={colors['text-primary']} />
        </button>
        <h1 style={{
          fontSize: 22, fontWeight: 600, color: colors['text-primary'],
          margin: 0,
        }}>
          个人信息
        </h1>
      </div>

      {/* 提示消息 */}
      {message && (
        <div style={{
          padding: '10px 16px', borderRadius: radius.md, marginBottom: space.md,
          fontSize: 13, fontWeight: 500,
          background: message.type === 'success' ? green.bg : '#fef2f2',
          color: message.type === 'success' ? green.strong : colors.danger,
        }}>
          {message.text}
        </div>
      )}

      {/* 用户信息卡片 */}
      <div style={{
        background: colors.canvas,
        borderRadius: radius.xl,
        boxShadow: shadows.soft,
        border: `1px solid ${colors.hairline}`,
        overflow: 'hidden',
        marginBottom: space.lg,
      }}>
        {/* 头像区 */}
        <div style={{
          display: 'flex', alignItems: 'flex-end',
          padding: `${space.xl}px ${space.xl}px 0`,
          marginBottom: space.lg,
        }}>
          {/* 头像（可点击更换） */}
          <div
            style={{ position: 'relative', cursor: 'pointer' }}
            onClick={() => setShowAvatarInput(!showAvatarInput)}
            onMouseEnter={(e) => {
              const overlay = e.currentTarget.querySelector('.avatar-overlay') as HTMLElement;
              if (overlay) overlay.style.opacity = '1';
            }}
            onMouseLeave={(e) => {
              const overlay = e.currentTarget.querySelector('.avatar-overlay') as HTMLElement;
              if (overlay) overlay.style.opacity = '0';
            }}
          >
            {avatarUrl ? (
              <img
                src={avatarUrl}
                alt="头像"
                style={{
                  width: 80, height: 80, borderRadius: '50%',
                  objectFit: 'cover',
                  border: `4px solid ${colors.canvas}`,
                  boxShadow: shadows.elevated,
                }}
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = 'none';
                }}
              />
            ) : null}
            <div
              style={{
                width: 80, height: 80, borderRadius: '50%',
                background: `linear-gradient(135deg, #667eea, #764ba2)`,
                color: '#fff',
                display: avatarUrl ? 'none' : 'flex',
                alignItems: 'center', justifyContent: 'center',
                fontSize: 32, fontWeight: 700,
                border: `4px solid ${colors.canvas}`,
                boxShadow: shadows.elevated,
                flexShrink: 0,
              }}
            >
              {avatarChar}
            </div>
            {/* 悬浮遮罩 */}
            <div className="avatar-overlay" style={{
              position: 'absolute', inset: 0, borderRadius: '50%',
              background: 'rgba(0,0,0,0.35)', opacity: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', fontSize: 11, fontWeight: 500,
              transition: 'opacity 0.15s', pointerEvents: 'none',
            }}>
              更换
            </div>
          </div>

          <div style={{ marginLeft: space.md, paddingBottom: 4, flex: 1 }}>
            {/* 昵称（可点击编辑） */}
            <div style={{ fontSize: 20, fontWeight: 600, color: colors['text-primary'], marginBottom: 4 }}>
              {displayName}
            </div>
            <div style={{ fontSize: 13, color: colors['text-secondary'], display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>账号：{user?.account || user?.username || '—'}</span>
              <span style={{
                display: 'inline-block', padding: '1px 10px',
                borderRadius: radius.pill, fontSize: 11,
                background: green.bg, color: green.strong, fontWeight: 500,
              }}>
                {user?.role === 'teacher' ? '教师' : user?.role === 'admin' ? '管理员' : '用户'}
              </span>
            </div>
          </div>
        </div>

        {/* 头像 URL 输入 */}
        {showAvatarInput && (
          <div style={{
            padding: `0 ${space.xl}px ${space.md}px`,
            marginLeft: 92, // 对齐头像右侧
          }}>
            <div style={{
              display: 'flex', gap: 8,
              padding: '10px 14px', background: colors['surface-soft'],
              borderRadius: radius.md, alignItems: 'center',
            }}>
              <input
                value={avatarUrl}
                onChange={(e) => setAvatarUrl(e.target.value)}
                placeholder="输入头像图片 URL..."
                style={{
                  flex: 1, border: 'none', background: 'transparent',
                  fontSize: 13, color: colors['text-primary'],
                  outline: 'none',
                }}
              />
              <button
                onClick={handleSaveAvatar}
                disabled={saving}
                style={{
                  padding: '4px 16px', background: colors.primary, color: '#fff',
                  border: 'none', borderRadius: radius.pill, fontSize: 12,
                  cursor: 'pointer', whiteSpace: 'nowrap', fontWeight: 500,
                  opacity: saving ? 0.6 : 1,
                }}
              >
                {saving ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        )}

        {/* 详细字段 */}
        <div style={{ padding: `0 ${space.xl}px ${space.xl}px` }}>
          {/* 昵称行（可编辑） */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '14px 0', borderTop: `1px solid ${colors.hairline}`,
            gap: 12,
          }}>
            <span style={{ fontSize: 14, color: colors['text-secondary'], whiteSpace: 'nowrap' }}>
              昵称
            </span>
            {editingNickname ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flex: 1, justifyContent: 'flex-end' }}>
                <input
                  ref={nickInputRef}
                  value={nickname}
                  onChange={(e) => setNickname(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSaveNickname();
                    if (e.key === 'Escape') {
                      setNickname(user?.nickname || user?.username || '');
                      setEditingNickname(false);
                    }
                  }}
                  style={{
                    flex: 1, maxWidth: 200,
                    padding: '6px 10px', border: `1px solid ${colors.hairline}`,
                    borderRadius: radius.md, fontSize: 14,
                    color: colors['text-primary'], background: colors.canvas,
                    outline: 'none',
                  }}
                />
                <button
                  onClick={handleSaveNickname}
                  disabled={saving}
                  style={{
                    padding: '4px 14px', background: colors.primary, color: '#fff',
                    border: 'none', borderRadius: radius.pill, fontSize: 12,
                    cursor: 'pointer', fontWeight: 500,
                    opacity: saving ? 0.6 : 1,
                  }}
                >
                  {saving ? '…' : '保存'}
                </button>
              </div>
            ) : (
              <div
                onClick={() => setEditingNickname(true)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
                  fontSize: 14, fontWeight: 500, color: colors['text-primary'],
                }}
              >
                <span>{nickname || user?.username || '未设置'}</span>
                <IconEdit size={13} color={colors['text-tertiary']} />
              </div>
            )}
          </div>

          {/* 账号行（只读） */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '14px 0', borderTop: `1px solid ${colors.hairline}`,
          }}>
            <span style={{ fontSize: 14, color: colors['text-secondary'] }}>账号</span>
            <span style={{
              fontSize: 14, fontWeight: 500, color: colors['text-primary'],
            }}>
              {user?.account || user?.username || '—'}
            </span>
          </div>
          {user?.email && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '14px 0', borderTop: `1px solid ${colors.hairline}`,
            }}>
              <span style={{ fontSize: 14, color: colors['text-secondary'] }}>邮箱</span>
              <span style={{
                fontSize: 14, fontWeight: 500, color: colors['text-primary'],
              }}>
                {user?.email || '—'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* 权益额度卡片 */}
      <div style={{
        background: colors.canvas,
        borderRadius: radius.xl,
        boxShadow: shadows.soft,
        border: `1px solid ${colors.hairline}`,
        overflow: 'hidden',
        marginBottom: space.lg,
      }}>
        <div style={{
          padding: `${space.md}px ${space.xl}px`,
          borderBottom: `1px solid ${colors.hairline}`,
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <IconShield size={18} color={green.strong} />
          <span style={{ fontSize: 15, fontWeight: 600, color: colors['text-primary'] }}>
            我的权益
          </span>
        </div>

        <div style={{ padding: space.xl }}>
          {/* 会员等级 */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10,
            background: green.bg, borderRadius: radius.md,
            padding: '14px 16px', marginBottom: 16,
          }}>
            <IconShield size={22} color={green.strong} />
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: green.strong }}>
                {quota?.membership_name || '加载中…'}
                {quota?.is_expired && (
                  <span style={{ color: colors.danger, marginLeft: 8, fontSize: 12 }}>(已过期)</span>
                )}
              </div>
              {quota && (
                <div style={{ fontSize: 12, color: green.mid, marginTop: 2 }}>
                  {user?.role === 'admin'
                    ? '管理权限 · 无限制使用'
                    : quota.is_expired
                      ? '已降级为免费版'
                      : '当前权益包'}
                </div>
              )}
            </div>
          </div>

          {/* 功能剩余次数 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {/* PPT */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '12px 14px', background: colors['surface-soft'],
              borderRadius: radius.md,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <IconPpt size={18} color={ppt ? quotaColor(ppt.unlimited, ppt.remaining) : colors['text-tertiary']} />
                <span style={{ fontSize: 14, color: colors['text-primary'], fontWeight: 500 }}>PPT 生成</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {ppt && ppt.limit < 999999 && (
                  <span style={{ fontSize: 11, color: colors['text-tertiary'] }}>
                    / {ppt.limit} 次
                  </span>
                )}
                <span style={{
                  fontSize: 14, fontWeight: 700,
                  color: ppt ? quotaColor(ppt.unlimited, ppt.remaining) : colors['text-tertiary'],
                }}>
                  {ppt ? quotaBadge(ppt.unlimited, ppt.remaining) : '—'}
                </span>
              </div>
            </div>

            {/* 试卷 */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '12px 14px', background: colors['surface-soft'],
              borderRadius: radius.md,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <IconGraduation size={18} color={exam ? quotaColor(exam.unlimited, exam.remaining) : colors['text-tertiary']} />
                <span style={{ fontSize: 14, color: colors['text-primary'], fontWeight: 500 }}>试卷生成</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {exam && exam.limit < 999999 && (
                  <span style={{ fontSize: 11, color: colors['text-tertiary'] }}>
                    / {exam.limit} 次
                  </span>
                )}
                <span style={{
                  fontSize: 14, fontWeight: 700,
                  color: exam ? quotaColor(exam.unlimited, exam.remaining) : colors['text-tertiary'],
                }}>
                  {exam ? quotaBadge(exam.unlimited, exam.remaining) : '—'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 修改密码卡片 */}
      <div style={{
        background: colors.canvas,
        borderRadius: radius.xl,
        boxShadow: shadows.soft,
        border: `1px solid ${colors.hairline}`,
        overflow: 'hidden',
        marginBottom: space.lg,
      }}>
        <div
          onClick={() => setShowPwdForm(!showPwdForm)}
          style={{
            padding: `${space.md}px ${space.xl}px`,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            cursor: 'pointer',
          }}
        >
          <span style={{ fontSize: 15, fontWeight: 600, color: colors['text-primary'] }}>
            修改密码
          </span>
          <span style={{
            fontSize: 13, color: colors['text-tertiary'],
            transition: 'transform 0.2s',
            transform: showPwdForm ? 'rotate(180deg)' : 'rotate(0deg)',
          }}>
            ▼
          </span>
        </div>

        {showPwdForm && (
          <div style={{ padding: `0 ${space.xl}px ${space.xl}px` }}>
            {pwdMsg && (
              <div style={{
                padding: '8px 12px', borderRadius: radius.md, marginBottom: space.md,
                fontSize: 13, fontWeight: 500,
                background: pwdMsg.type === 'success' ? green.bg : '#fef2f2',
                color: pwdMsg.type === 'success' ? green.strong : colors.danger,
              }}>
                {pwdMsg.text}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <input
                type="password"
                value={oldPwd}
                onChange={(e) => setOldPwd(e.target.value)}
                placeholder="请输入旧密码"
                style={{
                  padding: '10px 14px', border: `1px solid ${colors.hairline}`,
                  borderRadius: radius.md, fontSize: 14,
                  color: colors['text-primary'], background: colors['surface-soft'],
                  outline: 'none',
                }}
              />
              <input
                type="password"
                value={newPwd}
                onChange={(e) => setNewPwd(e.target.value)}
                placeholder="请输入新密码（至少 6 位）"
                style={{
                  padding: '10px 14px', border: `1px solid ${colors.hairline}`,
                  borderRadius: radius.md, fontSize: 14,
                  color: colors['text-primary'], background: colors['surface-soft'],
                  outline: 'none',
                }}
              />
              <input
                type="password"
                value={confirmPwd}
                onChange={(e) => setConfirmPwd(e.target.value)}
                placeholder="再次输入新密码"
                style={{
                  padding: '10px 14px', border: `1px solid ${colors.hairline}`,
                  borderRadius: radius.md, fontSize: 14,
                  color: colors['text-primary'], background: colors['surface-soft'],
                  outline: 'none',
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleChangePassword();
                }}
              />
              <button
                onClick={handleChangePassword}
                disabled={savingPwd}
                style={{
                  padding: '10px 0', background: colors.primary, color: '#fff',
                  border: 'none', borderRadius: radius.md, fontSize: 14,
                  cursor: 'pointer', fontWeight: 600,
                  opacity: savingPwd ? 0.6 : 1,
                  transition: 'opacity 0.15s',
                }}
              >
                {savingPwd ? '修改中…' : '确认修改'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 退出登录 */}
      <button
        onClick={handleLogout}
        style={{
          width: '100%', padding: '14px 0',
          background: colors.canvas, border: `1px solid ${colors.danger}30`,
          borderRadius: radius.xl, color: colors.danger, fontSize: 15,
          cursor: 'pointer', fontWeight: 500,
          transition: 'background 0.15s',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = '#fef2f2'; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = colors.canvas; }}
      >
        退出登录
      </button>
    </div>
  );
}
