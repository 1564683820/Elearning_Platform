// 课堂报告页 — 课后展示互动数据汇总
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { teacherApi, ClassroomReport } from '../../api/teacher';
import {
  colors, green, radius, typography, space, cardStyle,
  btnSmallSecondary,
  IconBack,
  progressBarStyle, progressBarFill,
} from '../../design-system';

const XS = 8;

export default function PPTReport() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [report, setReport] = useState<ClassroomReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!sessionId) return;
    teacherApi.ppt.getReport(sessionId)
      .then(setReport)
      .catch((e: any) => alert('加载报告失败: ' + e.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) return <div style={{ textAlign: 'center', padding: 60, color: colors['text-tertiary'] }}>加载中...</div>;
  if (!report) return <div style={{ textAlign: 'center', padding: 60, color: colors['text-tertiary'] }}>报告不存在</div>;

  const { session, interaction_summary: s, page_stats: ps } = report;

  const cards = [
    { label: '互动总次数', value: s.total_votes + s.total_quizzes + s.total_questions, color: '#2d7d46' },
    { label: '投票数', value: s.total_votes, color: '#5B9E6F' },
    { label: '答题数', value: s.total_quizzes, color: '#3d7a4e' },
    { label: '弹幕数', value: s.total_danmaku, color: '#88c8a0' },
    { label: '提问数', value: s.total_questions, color: '#2d7d46' },
    { label: '翻页次数', value: s.total_page_flips, color: '#3d7a4e' },
  ];

  const duration = session.started_at && session.ended_at
    ? Math.round((new Date(session.ended_at).getTime() - new Date(session.started_at).getTime()) / 60000)
    : 0;

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <button onClick={() => navigate('/ppt')} style={btnSmallSecondary}>
        <IconBack size={13} color={colors['text-secondary']} /> 返回列表
      </button>

      {/* 头部信息 */}
      <div style={{ ...cardStyle, marginTop: space.md, marginBottom: space.lg }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 22, fontWeight: 700, color: colors['text-primary'] }}>课堂报告</h2>
        <p style={{ margin: 0, color: colors['text-secondary'], fontSize: 14 }}>{session.title}</p>
        <div style={{ marginTop: space.sm, display: 'flex', gap: space.lg, fontSize: typography['body-sm'].fontSize, color: colors['text-secondary'], flexWrap: 'wrap' }}>
          <span>时长: {duration} 分钟</span>
          <span>学生: {session.student_count} 人</span>
          <span>翻页: {s.total_page_flips} 次</span>
          <span>{session.started_at ? new Date(session.started_at).toLocaleString() : ''}</span>
        </div>
      </div>

      {/* 数据卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: space.sm, marginBottom: space.lg }}>
        {cards.map((c, i) => (
          <div key={i} style={{ ...cardStyle, textAlign: 'center' }}>
            <div style={{ fontSize: 26, fontWeight: 700, color: c.color }}>{c.value}</div>
            <div style={{ fontSize: typography['body-sm'].fontSize, color: colors['text-tertiary'], marginTop: 2 }}>{c.label}</div>
          </div>
        ))}
      </div>

      {/* 答题正确率 */}
      <div style={{ ...cardStyle, marginBottom: space.lg }}>
        <h3 style={{ margin: `0 0 ${space.sm}px`, fontSize: 16, fontWeight: 600, color: colors['text-primary'] }}>答题正确率</h3>
        {s.quiz_accuracy_summary.total > 0 ? (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: space.sm, marginBottom: XS }}>
              <div style={progressBarStyle(100)}>
                <div style={{ ...progressBarFill(s.quiz_accuracy_summary.accuracy), transition: 'width 1s' }} />
              </div>
              <span style={{ fontSize: 20, fontWeight: 700, color: colors.success }}>{s.quiz_accuracy_summary.accuracy}%</span>
            </div>
            <div style={{ fontSize: typography['body-sm'].fontSize, color: colors['text-tertiary'] }}>
              共 {s.quiz_accuracy_summary.total} 题，正确 {s.quiz_accuracy_summary.correct} 题
            </div>
          </div>
        ) : (
          <div style={{ color: colors['text-tertiary'], fontSize: 14 }}>暂无答题数据</div>
        )}
      </div>

      {/* 翻页时序 */}
      <div style={cardStyle}>
        <h3 style={{ margin: `0 0 ${space.sm}px`, fontSize: 16, fontWeight: 600, color: colors['text-primary'] }}>翻页记录</h3>
        {ps.length > 0 ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: XS }}>
            {ps.map((p: any, i: number) => (
              <div key={i} style={{
                padding: '4px 12px', background: colors['block-lime'], borderRadius: radius.pill,
                fontSize: 12, color: colors.success,
              }}>
                P{p.page || p.page_index || i + 1}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: colors['text-tertiary'], fontSize: 14 }}>暂无翻页记录</div>
        )}
      </div>
    </div>
  );
}
