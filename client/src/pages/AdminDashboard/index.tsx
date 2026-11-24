// 管理端概览 — 系统关键数据总览
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import client from '../../api/client';
import { colors, radius, typography, space, cardStyle, btnPrimary } from '../../design-system';

interface DashboardData {
  total_users: { student: number; teacher: number; admin: number };
  recent_activity: {
    active_students_ndays: number;
    active_teachers_ndays: number;
    total_study_minutes_ndays: number;
    period_days: number;
  };
}

export default function AdminDashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    client.get('/admin/statistics/usage?days=7')
      .then((res) => setData(res.data.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center', color: colors['text-secondary'] }}>加载中...</div>;
  }

  const cards = [
    { label: '学生总数', value: data?.total_users?.student ?? 0, color: '#2d7d46', icon: '👨‍🎓' },
    { label: '教师总数', value: data?.total_users?.teacher ?? 0, color: '#5B9E6F', icon: '👨‍🏫' },
    { label: '近7天活跃学生', value: data?.recent_activity?.active_students_ndays ?? 0, color: '#88c8a0', icon: '📊' },
    { label: '近7天学习时长(分钟)', value: data?.recent_activity?.total_study_minutes_ndays ?? 0, color: '#3d7a4e', icon: '⏱️' },
  ];

  return (
    <div>
      <h1 style={{ ...typography.headline, marginBottom: space.lg }}>管理概览</h1>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: space.md, marginBottom: space.xl }}>
        {cards.map((card) => (
          <div key={card.label} style={{
            ...cardStyle,
            borderLeft: `4px solid ${card.color}`,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <span style={{ fontSize: 28 }}>{card.icon}</span>
              <span style={{ fontSize: typography['body-sm'].fontSize, color: colors['text-secondary'] }}>{card.label}</span>
            </div>
            <div style={{ fontSize: 32, fontWeight: 700, color: card.color }}>{card.value}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: space.lg }}>
        <div style={cardStyle}>
          <h3 style={{ ...typography['card-title'], marginBottom: space.md }}>管理功能</h3>
          {[
            { path: '/admin/users', label: '账号管理', desc: '管理学生和教师账号', icon: '👤' },
            { path: '/admin/fees', label: '费用管理', desc: '查看费用统计和明细', icon: '💰' },
            { path: '/admin/apikeys', label: 'API Key 管理', desc: '管理项目 API Key 配置', icon: '🔑' },
            { path: '/admin/usage', label: '浏览统计', desc: '小程序端和教师端使用数据', icon: '📈' },
          ].map((item) => (
            <div
              key={item.path}
              onClick={() => navigate(item.path)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '12px 16px', borderRadius: radius.md,
                cursor: 'pointer', marginBottom: 8,
                background: colors['surface-soft'],
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = colors['block-lime']; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = colors['surface-soft']; }}
            >
              <span style={{ fontSize: 24 }}>{item.icon}</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{item.label}</div>
                <div style={{ fontSize: 12, color: colors['text-secondary'] }}>{item.desc}</div>
              </div>
            </div>
          ))}
        </div>

        <div style={cardStyle}>
          <h3 style={{ ...typography['card-title'], marginBottom: space.md }}>系统状态</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: `1px solid ${colors.hairline}` }}>
              <span style={{ color: colors['text-secondary'] }}>教师端活跃 (7天)</span>
              <span style={{ fontWeight: 600 }}>{data?.recent_activity?.active_teachers_ndays ?? 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: `1px solid ${colors.hairline}` }}>
              <span style={{ color: colors['text-secondary'] }}>学习总时长 (分钟)</span>
              <span style={{ fontWeight: 600 }}>{(data?.recent_activity?.total_study_minutes_ndays ?? 0).toLocaleString()}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: `1px solid ${colors.hairline}` }}>
              <span style={{ color: colors['text-secondary'] }}>教师</span>
              <span style={{ fontWeight: 600 }}>{data?.total_users?.teacher ?? 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
              <span style={{ color: colors['text-secondary'] }}>学生</span>
              <span style={{ fontWeight: 600 }}>{data?.total_users?.student ?? 0}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
