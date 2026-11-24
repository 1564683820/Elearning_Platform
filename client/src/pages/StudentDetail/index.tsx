// 学生详情页 — 错题分布、正确率、薄弱点
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { teacherApi, StudentDetailData } from '../../api/teacher';
import {
  colors, green, radius, typography, space, cardStyle, btnSmallSecondary,
  colorBlockLime, colorBlockLilac, colorBlockCoral,
  IconBack, IconArrowRight,
  progressBarStyle, progressBarFill,
} from '../../design-system';

const xs = 8;

export default function StudentDetail() {
  const { classId, studentId } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<StudentDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setDetail(null);
    setError('');
    if (!classId || !studentId) {
      setError('缺少班级或学生参数');
      setLoading(false);
      return;
    }
    teacherApi.getStudentDetail(classId, studentId)
      .then(result => { if (active) setDetail(result); })
      .catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : '加载学生详情失败'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [classId, studentId]);

  if (loading) return <p style={{ color: colors['text-tertiary'] }}>加载中...</p>;
  if (!detail) return <p role="alert" style={{ color: colors.danger }}>{error || '学生不存在'}</p>;

  const StatCard = ({ label, value, color }: { label: string; value: string | number; color: string }) => (
    <div style={{
      ...cardStyle, flex: 1, minWidth: 140,
      display: 'flex', flexDirection: 'column', gap: 4,
    }}>
      <span style={{
        fontSize: typography.eyebrow.fontSize,
        fontWeight: typography.eyebrow.fontWeight,
        letterSpacing: typography.eyebrow.letterSpacing,
        textTransform: 'uppercase', color: colors['text-tertiary'],
      }}>{label}</span>
      <span style={{ fontSize: 26, fontWeight: 550, color, lineHeight: 1.1 }}>{value}</span>
    </div>
  );

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      {/* 顶栏 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: space.xl,
      }}>
        <div>
          <h1 style={{
            margin: 0, fontSize: typography['display-lg'].fontSize,
            fontWeight: typography['display-lg'].fontWeight,
            letterSpacing: typography['display-lg'].letterSpacing,
            color: colors['text-primary'],
          }}>{detail.nickname}</h1>
          <p style={{ margin: '4px 0 0', color: colors['text-secondary'], fontSize: typography['body-sm'].fontSize }}>
            学习详情
          </p>
        </div>
        <button onClick={() => navigate(`/classes/${classId}/dashboard`)} style={btnSmallSecondary}>
          <IconBack size={13} color={colors['text-secondary']} /> 返回看板
        </button>
      </div>

      {/* 统计卡片 */}
      <div style={{ display: 'flex', gap: space.md, marginBottom: space.xl, flexWrap: 'wrap' }}>
        <StatCard label="加入天数" value={detail.joined_days + ' 天'} color={colors.success} />
        <StatCard label="单词量" value={detail.total_words} color={colors.info} />
        <StatCard label="训练次数" value={detail.total_training} color={colors.warning} />
        <StatCard label="总正确率" value={detail.avg_accuracy + '%'} color={green.strong} />
      </div>

      {/* 各分类正确率 */}
      <div style={{ ...cardStyle, marginBottom: space.xl, background: colors['block-mint'] }}>
        <h3 style={{
          margin: `0 0 ${space.md}px`, fontSize: typography.headline.fontSize,
          fontWeight: typography.headline.fontWeight,
          color: colors['text-primary'],
        }}>各分类正确率</h3>
        {detail.category_breakdown.length === 0 ? (
          <p style={{ color: colors['text-tertiary'] }}>暂无数据</p>
        ) : (
          detail.category_breakdown.map((c, i) => (
            <div key={i} style={{ marginBottom: space.sm }}>
              <div style={{
                display: 'flex', justifyContent: 'space-between',
                marginBottom: 4, fontSize: typography['body-sm'].fontSize,
              }}>
                <span style={{ color: colors['text-primary'] }}>{c.category}</span>
                <span style={{
                  color: c.accuracy >= 70 ? colors.success : colors.danger,
                  fontWeight: 500,
                }}>{c.accuracy}%</span>
              </div>
              <div style={progressBarStyle(100)}>
                <div style={{
                  ...progressBarFill(c.accuracy),
                  background: c.accuracy >= 70 ? colors.success : colors.danger,
                }} />
              </div>
            </div>
          ))
        )}
      </div>

      {/* 薄弱知识点 */}
      <div style={{ ...cardStyle, background: colors['block-coral'] }}>
        <h3 style={{
          margin: `0 0 ${space.md}px`, fontSize: typography.headline.fontSize,
          fontWeight: typography.headline.fontWeight,
          color: colors['text-primary'],
        }}>薄弱知识点</h3>
        {detail.weakness_points.length === 0 ? (
          <p style={{ color: colors['text-tertiary'] }}>暂无薄弱点</p>
        ) : (
          detail.weakness_points.map((w, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between',
              padding: '10px 0', borderBottom: `1px solid ${colors['hairline-soft']}`,
              fontSize: typography.body.fontSize, color: colors['text-primary'],
            }}>
              <span>{w.knowledge_point}</span>
              <span style={{ color: colors.danger, fontWeight: 500 }}>错 {w.count} 次</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
