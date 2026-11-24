// 管理者端布局 — 侧边栏导航 + 内容区
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  colors, radius, typography, space,
  IconUsers, IconChart, IconShield, IconActivity,
} from '../design-system';

const navItems = [
  { path: '/admin/dashboard', label: '管理概览', icon: IconChart },
  { path: '/admin/users', label: '账号管理', icon: IconUsers },
  { path: '/admin/fees', label: '费用管理', icon: IconShield },
  { path: '/admin/apikeys', label: 'API Key 管理', icon: IconShield },
  { path: '/admin/usage', label: '浏览统计', icon: IconActivity },
];

export default function AdminLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#f5f5f5' }}>
      {/* 侧边栏 */}
      <aside style={{
        width: 220, background: '#0f1a0f', color: '#fff',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
      }}>
        <div style={{
          padding: `${space.lg}px ${space.md}px`,
          fontSize: typography['card-title'].fontSize,
          fontWeight: 700,
          letterSpacing: '-0.3px',
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <span style={{ fontSize: 20 }}>🔧</span>
          E-Learning 管理端
        </div>
        <nav style={{ flex: 1, padding: `${space.xs}px 0` }}>
          {navItems.map((item) => {
            const active = location.pathname === item.path;
            const Icon = item.icon;
            return (
              <div
                key={item.path}
                onClick={() => navigate(item.path)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '11px 20px',
                  cursor: 'pointer',
                  fontSize: 14,
                  fontWeight: active ? 500 : 400,
                  background: active ? 'rgba(255,255,255,0.08)' : 'transparent',
                  borderLeft: active ? `2px solid ${colors.success}` : '2px solid transparent',
                  color: active ? colors.success : 'rgba(255,255,255,0.65)',
                  transition: 'all 0.15s',
                }}
                onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = 'rgba(255,255,255,0.04)'; }}
                onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent'; }}
              >
                <Icon size={16} color={active ? colors.success : 'rgba(255,255,255,0.5)'} />
                {item.label}
              </div>
            );
          })}
        </nav>
        <div style={{
          padding: space.md, borderTop: '1px solid rgba(255,255,255,0.08)',
          display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          <button
            onClick={() => navigate('/classes')}
            style={{
              width: '100%',
              padding: '8px 0',
              background: 'transparent',
              border: '1px solid rgba(255,255,255,0.12)',
              color: 'rgba(255,255,255,0.45)',
              borderRadius: radius.pill,
              cursor: 'pointer',
              fontSize: 12,
              transition: 'color 0.15s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#aaa'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'rgba(255,255,255,0.45)'; }}
          >
            切换到教师端
          </button>
          <button
            onClick={handleLogout}
            style={{
              width: '100%',
              padding: '8px 0',
              background: 'transparent',
              border: '1px solid rgba(255,255,255,0.12)',
              color: 'rgba(255,255,255,0.45)',
              borderRadius: radius.pill,
              cursor: 'pointer',
              fontSize: 13,
              transition: 'color 0.15s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#fff'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'rgba(255,255,255,0.5)'; }}
          >
            退出登录
          </button>
        </div>
      </aside>

      {/* 主内容区 */}
      <main style={{ flex: 1, overflow: 'auto', padding: space.xl }}>
        <Outlet />
      </main>
    </div>
  );
}
