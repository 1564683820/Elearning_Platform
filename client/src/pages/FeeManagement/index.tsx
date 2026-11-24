// 费用管理 — 查看费用统计、订单明细
import { useEffect, useState } from 'react';
import client from '../../api/client';
import { colors, radius, typography, space, cardStyle } from '../../design-system';

interface FeeStats {
  total_revenue: number; order_count: number;
  period: { start: string; end: string };
  by_plan: Record<string, { count: number; amount: number }>;
  membership_distribution: { vip_total: number; free_total: number };
}
interface FeeDetailItem {
  id: number; user_id: number; username: string; nickname: string;
  plan_id: string; amount: number; status: string; created_at: string;
}

export default function FeeManagement() {
  const [stats, setStats] = useState<FeeStats | null>(null);
  const [detail, setDetail] = useState<FeeDetailItem[]>([]);
  const [detailTotal, setDetailTotal] = useState(0);
  const [detailPage, setDetailPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const fetchData = () => {
    setLoading(true);
    Promise.all([
      client.get('/admin/statistics/fees'),
      client.get('/admin/statistics/fees/detail', { params: { page: detailPage, page_size: 20 } }),
    ]).then(([sr, dr]) => {
      setStats(sr.data.data);
      const d = dr.data.data;
      setDetail(d.items); setDetailTotal(d.total);
    }).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, [detailPage]);

  if (loading) return <div style={{ textAlign:'center', padding:40, color: colors['text-secondary'] }}>加载中...</div>;

  return (
    <div>
      <h1 style={{ ...typography.headline, marginBottom: space.lg }}>费用管理</h1>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(200px,1fr))', gap: space.md, marginBottom: space.xl }}>
        {[
          { l: '总收入', v: `¥${(stats?.total_revenue ?? 0).toFixed(2)}`, c: colors.success },
          { l: '付费订单数', v: String(stats?.order_count ?? 0), c: '#3b82f6' },
          { l: 'VIP 用户', v: String(stats?.membership_distribution?.vip_total ?? 0), c: '#8b5cf6' },
          { l: '免费用户', v: String(stats?.membership_distribution?.free_total ?? 0), c: '#d97706' },
        ].map(c => (
          <div key={c.l} style={{ ...cardStyle, borderLeft: `4px solid ${c.c}` }}>
            <div style={{ fontSize:12, color: colors['text-secondary'], marginBottom:8 }}>{c.l}</div>
            <div style={{ fontSize:28, fontWeight:700, color: c.c }}>{c.v}</div>
          </div>
        ))}
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap: space.lg, marginBottom: space.xl }}>
        <div style={cardStyle}>
          <h3 style={{ ...typography['card-title'], marginBottom: space.md }}>套餐销售统计</h3>
          {Object.keys(stats?.by_plan ?? {}).length > 0 ? (
            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:14 }}>
              <thead><tr style={{ borderBottom:`1px solid ${colors.hairline}`, color: colors['text-secondary'], fontSize:12 }}>
                <th style={{ padding:'8px 12px', textAlign:'left' }}>套餐</th>
                <th style={{ padding:'8px 12px', textAlign:'right' }}>订单数</th>
                <th style={{ padding:'8px 12px', textAlign:'right' }}>金额</th>
              </tr></thead>
              <tbody>
                {Object.entries(stats!.by_plan!).map(([plan, info]) => (
                  <tr key={plan} style={{ borderBottom:`1px solid ${colors['hairline-soft']}` }}>
                    <td style={{ padding:'10px 12px', fontWeight:500 }}>{plan}</td>
                    <td style={{ padding:'10px 12px', textAlign:'right' }}>{info.count}</td>
                    <td style={{ padding:'10px 12px', textAlign:'right', fontWeight:600 }}>¥{info.amount.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div style={{ color: colors['text-secondary'], fontSize:14 }}>暂无数据</div>}
        </div>
        <div style={cardStyle}>
          <h3 style={{ ...typography['card-title'], marginBottom: space.md }}>会员分布</h3>
          {stats ? (() => {
            const total = (stats.membership_distribution.vip_total + stats.membership_distribution.free_total) || 1;
            return ['VIP', '免费'].map((l, i) => {
              const val = i === 0 ? stats.membership_distribution.vip_total : stats.membership_distribution.free_total;
              const pct = (val / total) * 100;
              return (
                <div key={l} style={{ marginBottom:12 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                    <span style={{ fontSize:13, color: colors['text-secondary'] }}>{l}</span>
                    <span style={{ fontSize:13, fontWeight:600 }}>{val}</span>
                  </div>
                  <div style={{ height:8, background: colors['surface-soft'], borderRadius: radius.pill, overflow:'hidden' }}>
                    <div style={{ height:'100%', width:`${pct}%`, background: i===0 ? '#8b5cf6' : '#d97706', borderRadius: radius.pill }} />
                  </div>
                </div>
              );
            });
          })() : null}
        </div>
      </div>

      <div style={cardStyle}>
        <h3 style={{ ...typography['card-title'], marginBottom: space.md }}>费用明细</h3>
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:14 }}>
          <thead><tr style={{ borderBottom:`1px solid ${colors.hairline}`, color: colors['text-secondary'], fontSize:12 }}>
            <th style={{ padding:'10px 12px', textAlign:'left' }}>订单ID</th>
            <th style={{ padding:'10px 12px', textAlign:'left' }}>用户</th>
            <th style={{ padding:'10px 12px', textAlign:'left' }}>套餐</th>
            <th style={{ padding:'10px 12px', textAlign:'right' }}>金额</th>
            <th style={{ padding:'10px 12px', textAlign:'left' }}>状态</th>
            <th style={{ padding:'10px 12px', textAlign:'left' }}>时间</th>
          </tr></thead>
          <tbody>
            {detail.map(item => (
              <tr key={item.id} style={{ borderBottom:`1px solid ${colors['hairline-soft']}` }}>
                <td style={{ padding:'10px 12px', color: colors['text-secondary'] }}>{item.id}</td>
                <td style={{ padding:'10px 12px', fontWeight:500 }}>{item.username || item.nickname || `#${item.user_id}`}</td>
                <td style={{ padding:'10px 12px' }}>{item.plan_id}</td>
                <td style={{ padding:'10px 12px', textAlign:'right', fontWeight:600 }}>¥{item.amount.toFixed(2)}</td>
                <td style={{ padding:'10px 12px' }}>
                  <span style={{ padding:'2px 10px', borderRadius: radius.pill, fontSize:12,
                    background: item.status === 'paid' ? '#e6f7e6' : '#fef3c7',
                    color: item.status === 'paid' ? '#2d7d46' : '#d97706', fontWeight:500 }}>
                    {item.status === 'paid' ? '已支付' : item.status}
                  </span>
                </td>
                <td style={{ padding:'10px 12px', color: colors['text-secondary'], fontSize:13 }}>
                  {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '-'}
                </td>
              </tr>
            ))}
            {detail.length === 0 && <tr><td colSpan={6} style={{ textAlign:'center', padding:30, color: colors['text-secondary'] }}>暂无订单数据</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
