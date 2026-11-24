// 教师端布局 — 可折叠侧边栏 + 用户信息 + 产品介绍 + 内容区
import { useState, useMemo, useEffect, useRef } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  colors, green, radius, space,
  IconUsers, IconDocument, IconPpt, IconGraduation, IconBulb,
  IconEdit, IconBook,
} from '../design-system';

/* ─── 导航项 ────────────────────────── */
const navItems = [
  { path: '/teaching',     label: '教学',     icon: IconBulb },
  { path: '/classes',      label: '班级',     icon: IconUsers },
  { path: '/teaching-tasks', label: '教学任务', icon: IconBook },
  { path: '/documents',    label: '文档',     icon: IconDocument },
  { path: '/ppt',          label: 'PPT',      icon: IconPpt },
  { path: '/exams',        label: '试卷',     icon: IconGraduation },
];



/* ─── 主布局 ──────────────────────────── */
export default function Layout() {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);

  // 路由变化时滚动主内容区到顶部，防止上一页面滚动位置残留
  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior });
  }, [location.pathname]);

  const user = useMemo(() => {
    try {
      const raw = localStorage.getItem('user');
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }, []);

  const token = localStorage.getItem('token');
  const isLoggedIn = !!token && !!user;

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#f5f5f5' }}>
      {/* ═══ 侧边栏 ═══ */}
      <aside
        onMouseEnter={() => setExpanded(true)}
        onMouseLeave={() => setExpanded(false)}
        style={{
          width: expanded ? 220 : 80,
          transition: 'width 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
          background: expanded ? '#1a2e1a' : '#1c1c1c',
          color: '#fff',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* ── 用户信息区 ── */}
        <div
          onClick={() => {
            if (isLoggedIn) navigate('/profile');
            else navigate('/login');
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: expanded ? `${space.lg}px ${space.md}px` : '16px 12px',
            borderBottom: '1px solid rgba(255,255,255,0.08)',
            cursor: 'pointer',
            minHeight: 60,
            transition: 'padding 0.25s',
            position: 'relative',
            flexShrink: 0,
          }}
        >
          {/* 头像 */}
          <div style={{
            width: 36, height: 36, borderRadius: '50%',
            background: user ? colors.primary : 'rgba(255,255,255,0.15)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, fontWeight: 600, color: '#fff',
            flexShrink: 0,
            transition: 'transform 0.15s',
          }}
            onMouseEnter={(e) => { e.currentTarget.style.transform = 'scale(1.05)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
          >
            {isLoggedIn
              ? (user?.nickname?.[0] || user?.username?.[0] || 'U')
              : '?'}
          </div>

          {/* 信息 — 展开时显示 */}
          <div style={{
            opacity: expanded ? 1 : 0,
            transition: 'opacity 0.15s 0.05s',
            overflow: 'hidden',
            whiteSpace: 'nowrap',
            flex: 1,
          }}>
            {isLoggedIn ? (
              <>
                <div style={{
                  fontSize: 14, fontWeight: 600, color: '#fff', lineHeight: 1.3,
                }}>
                  {user?.nickname || user?.username || '用户'}
                </div>
                <div style={{
                  fontSize: 11, color: green.soft, lineHeight: 1.3, marginTop: 1,
                }}>
                  {user?.role === 'teacher' ? '教师' : user?.role === 'admin' ? '管理员' : '用户'}
                </div>
              </>
            ) : (
              <>
                <div style={{
                  fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.7)',
                  lineHeight: 1.3,
                }}>
                  未登录
                </div>
                <div style={{
                  fontSize: 11, color: 'rgba(255,255,255,0.35)',
                  lineHeight: 1.3, marginTop: 1,
                }}>
                  点击登录
                </div>
              </>
            )}
          </div>

          {/* 展开箭头 — 仅展开时显示 */}
          {expanded && (
            <IconEdit size={14} color="rgba(255,255,255,0.35)" />
          )}
        </div>

        {/* ── 导航菜单 ── */}
        <nav style={{
          flex: 1,
          padding: `${space.xs}px 0`,
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
        }}>
          {navItems.map((item) => {
            const active = location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
            const Icon = item.icon;
            return (
              <div
                key={item.path}
                onClick={() => navigate(item.path)}
                title={item.label}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: expanded ? 'flex-start' : 'center',
                  gap: 12,
                  padding: expanded ? '12px 20px' : '14px 0',
                  margin: '0 8px',
                  borderRadius: radius.md,
                  cursor: 'pointer',
                  fontSize: 14,
                  fontWeight: active ? 500 : 400,
                  background: active
                    ? '#2d7d46'
                    : 'transparent',
                  color: active
                    ? '#fff'
                    : 'rgba(255,255,255,0.60)',
                  transition: 'all 0.2s',
                  whiteSpace: 'nowrap',
                }}
                onMouseEnter={(e) => {
                  if (!active) {
                    e.currentTarget.style.background = 'rgba(45,125,70,0.25)';
                    e.currentTarget.style.color = '#fff';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    e.currentTarget.style.background = 'transparent';
                    e.currentTarget.style.color = 'rgba(255,255,255,0.60)';
                  }
                }}
              >
                <Icon
                  size={expanded ? 18 : 20}
                  color={active ? '#fff' : 'rgba(255,255,255,0.50)'}
                />
                <span style={{
                  opacity: expanded ? 1 : 0,
                  transition: 'opacity 0.12s 0.05s',
                  overflow: 'hidden',
                }}>
                  {item.label}
                </span>
              </div>
            );
          })}

          {/* ── 分割 + 产品介绍按钮 ── */}
          <div style={{ flex: 1 }} />
          <div style={{
            margin: '4px 14px 6px',
            height: 1,
            background: 'rgba(255,255,255,0.08)',
          }} />
          <div
            onClick={() => navigate('/product-intro')}
            title="产品介绍"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: expanded ? 'flex-start' : 'center',
              gap: 12,
              padding: expanded ? '12px 20px' : '14px 0',
              margin: '0 8px',
              borderRadius: radius.md,
              cursor: 'pointer',
              fontSize: 14,
              color: 'rgba(255,255,255,0.60)',
              whiteSpace: 'nowrap',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(45,125,70,0.25)';
              e.currentTarget.style.color = '#fff';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = 'rgba(255,255,255,0.60)';
            }}
          >
            <IconBook size={expanded ? 18 : 20} color="rgba(255,255,255,0.50)" />
            <span style={{
              opacity: expanded ? 1 : 0,
              transition: 'opacity 0.12s 0.05s',
              overflow: 'hidden',
            }}>
              产品介绍
            </span>
          </div>
        </nav>
      </aside>

      {/* ═══ 主内容区 ═══ */}
      <main ref={mainRef} style={{
        flex: 1,
        overflow: 'auto',
        padding: `${space.xl}px ${space.xxl}px`,
        background: '#f5f5f5',
        borderRadius: `${radius.xl}px 0 0 ${radius.xl}px`,
        marginLeft: -radius.xl,
        position: 'relative',
        zIndex: 1,
        boxShadow: '-2px 0 16px rgba(0,0,0,0.05)',
      }}>
        <Outlet />
      </main>
    </div>
  );
}
