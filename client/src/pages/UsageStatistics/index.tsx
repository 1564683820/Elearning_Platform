// 浏览统计 — 小程序端和教师端使用人数/时长统计
import { useEffect, useState } from 'react';
import client from '../../api/client';
import { colors, radius, typography, space, cardStyle } from '../../design-system';

interface DailyTrend {
  date: string; active_students: number; total_minutes: number;
}
interface UsageData {
  total_users: { student: number; teacher: number; admin: number };
  recent_activity: {
    active_students_ndays: number; active_teachers_ndays: number;
    total_study_minutes_ndays: number; period_days: number;
  };
  daily_trend: DailyTrend[];
}

export default function UsageStatistics() {
  const [data, setData] = useState<UsageData | null>(null);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    client.get('/admin/statistics/usage', { params: { days } })
      .then(res => setData(res.data.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [days]);

  const maxVal = Math.max(1, ...(data?.daily_trend ?? []).map(d => d.active_students));
  const maxMin = Math.max(1, ...(data?.daily_trend ?? []).map(d => d.total_minutes));

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom: space.lg }}>
        <h1 style={{ ...typography.headline }}>浏览统计</h1>
        <div style={{ display:'flex', gap:8 }}>
          {[7, 14, 30].map(n => (
            <div key={n} onClick={() => setDays(n)}
              style={{
                padding:'6px 16px', borderRadius: radius.pill, cursor:'pointer', fontSize:13,
                background: days === n ? colors.primary : colors.canvas,
                color: days === n ? '#fff' : colors['text-secondary'],
                border: `1px solid ${days === n ? colors.primary : colors.hairline}`,
                fontWeight: days === n ? 500 : 400, transition:'all 0.15s',
              }}>
              近{n}天
            </div>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign:'center', padding:40, color: colors['text-secondary'] }}>加载中...</div>
      ) : (
        <>
          {/* 总览卡片 */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(220px,1fr))', gap: space.md, marginBottom: space.xl }}>
            {[
              { l: '学生总数', v: data?.total_users?.student ?? 0, c: '#2d7d46' },
              { l: '教师总数', v: data?.total_users?.teacher ?? 0, c: '#5B9E6F' },
              { l: `近${days}天活跃学生`, v: data?.recent_activity?.active_students_ndays ?? 0, c: '#3b82f6' },
              { l: `近${days}天活跃教师`, v: data?.recent_activity?.active_teachers_ndays ?? 0, c: '#8b5cf6' },
              { l: `学习总时长(分钟)`, v: (data?.recent_activity?.total_study_minutes_ndays ?? 0).toLocaleString(), c: '#d97706' },
            ].map(c => (
              <div key={c.l} style={{ ...cardStyle, borderLeft: `4px solid ${c.c}` }}>
                <div style={{ fontSize:12, color: colors['text-secondary'], marginBottom:8 }}>{c.l}</div>
                <div style={{ fontSize:28, fontWeight:700, color: c.c }}>{c.v}</div>
              </div>
            ))}
          </div>

          {/* 日趋势图 */}
          <div style={cardStyle}>
            <h3 style={{ ...typography['card-title'], marginBottom: space.md }}>每日活跃趋势</h3>
            <div style={{ display:'flex', gap: 2, alignItems:'flex-end', height:160, padding:'16px 0' }}>
              {(data?.daily_trend ?? []).map(d => {
                const h = maxVal > 0 ? (d.active_students / maxVal) * 140 : 0;
                return (
                  <div key={d.date} style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center', height:'100%', justifyContent:'flex-end' }}>
                    <div style={{
                      width:'100%', maxWidth:40, height: Math.max(4, h),
                      background: colors.primary, borderRadius: `${radius.sm}px ${radius.sm}px 0 0`,
                      opacity: 0.8, minHeight: 4,
                      transition:'height 0.3s',
                    }} />
                    <div style={{ fontSize:10, color: colors['text-secondary'], marginTop:6, transform:'rotate(-45deg)', whiteSpace:'nowrap' }}>
                      {d.date.slice(5)}
                    </div>
                    <div style={{ fontSize:10, fontWeight:600, color: colors.primary }}>{d.active_students}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 每日学习时长趋势 */}
          <div style={{ ...cardStyle, marginTop: space.md }}>
            <h3 style={{ ...typography['card-title'], marginBottom: space.md }}>每日学习时长（分钟）</h3>
            <div style={{ display:'flex', gap: 2, alignItems:'flex-end', height:160, padding:'16px 0' }}>
              {(data?.daily_trend ?? []).map(d => {
                const h = maxMin > 0 ? (d.total_minutes / maxMin) * 140 : 0;
                return (
                  <div key={d.date} style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center', height:'100%', justifyContent:'flex-end' }}>
                    <div style={{
                      width:'100%', maxWidth:40, height: Math.max(4, h),
                      background: '#d97706', borderRadius: `${radius.sm}px ${radius.sm}px 0 0`,
                      opacity: 0.8, minHeight: 4,
                      transition:'height 0.3s',
                    }} />
                    <div style={{ fontSize:10, color: colors['text-secondary'], marginTop:6, transform:'rotate(-45deg)', whiteSpace:'nowrap' }}>
                      {d.date.slice(5)}
                    </div>
                    <div style={{ fontSize:10, fontWeight:600, color: '#d97706' }}>{Math.round(d.total_minutes)}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 明细表格 */}
          <div style={{ ...cardStyle, marginTop: space.md }}>
            <h3 style={{ ...typography['card-title'], marginBottom: space.md }}>日数据明细</h3>
            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:14 }}>
              <thead><tr style={{ borderBottom:`1px solid ${colors.hairline}`, color: colors['text-secondary'], fontSize:12 }}>
                <th style={{ padding:'10px 12px', textAlign:'left' }}>日期</th>
                <th style={{ padding:'10px 12px', textAlign:'right' }}>活跃学生</th>
                <th style={{ padding:'10px 12px', textAlign:'right' }}>学习时长(分钟)</th>
              </tr></thead>
              <tbody>
                {(data?.daily_trend ?? []).slice().reverse().map(d => (
                  <tr key={d.date} style={{ borderBottom:`1px solid ${colors['hairline-soft']}` }}>
                    <td style={{ padding:'10px 12px', fontWeight:500 }}>{d.date}</td>
                    <td style={{ padding:'10px 12px', textAlign:'right' }}>{d.active_students}</td>
                    <td style={{ padding:'10px 12px', textAlign:'right' }}>{Math.round(d.total_minutes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
