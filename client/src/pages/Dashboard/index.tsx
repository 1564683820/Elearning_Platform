// 数据看板页 — 班级正确率图表、高频错题、活跃度、AI 智能查询
import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { teacherApi, ClassDashboardData, StudentData, AIQueryResponse } from '../../api/teacher';
import {
  colors, green, radius, typography, space, cardStyle, btnPrimary, btnSmall, btnSmallSecondary, inputStyle,
  colorBlockLime, colorBlockLilac, colorBlockCoral,
  IconUsers, IconBook, IconActivity, IconChart, IconArrowRight, IconBack, IconBulb,
  progressBarStyle, progressBarFill,
} from '../../design-system';

const xs = 8; // shorthand

export default function Dashboard() {
  const { classId } = useParams();
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState<ClassDashboardData | null>(null);
  const [students, setStudents] = useState<StudentData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // AI 查询（流式）
  const [aiQuestion, setAiQuestion] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiStreamingContent, setAiStreamingContent] = useState('');
  const [aiStatus, setAiStatus] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setDashboard(null);
    setStudents([]);
    setError('');
    if (!classId) {
      setError('缺少班级参数');
      setLoading(false);
      return;
    }
    Promise.all([
      teacherApi.getClassDashboard(classId),
      teacherApi.listStudents(classId),
    ]).then(([dash, stu]) => {
      if (!active) return;
      setDashboard(dash);
      setStudents(stu || []);
    }).catch((err: any) => {
      if (!active) return;
      setError(err?.response?.data?.detail || err?.message || '加载失败，请检查权限');
    })
    .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [classId]);

  useEffect(() => {
    setAiStreamingContent('');
    setAiLoading(false);
    setAiStatus('');
    return () => { abortRef.current?.abort(); abortRef.current = null; };
  }, [classId]);

  const handleAiQuery = async () => {
    if (!aiQuestion.trim() || !classId) return;
    abortRef.current?.abort();
    setAiLoading(true);
    setAiStreamingContent('');
    setAiStatus('小e正在思考...');

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const resp = await teacherApi.aiQueryStream({
        class_id: classId,
        question: aiQuestion,
      }, controller.signal);
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData?.detail || `HTTP ${resp.status}`);
      }
      const reader = resp.body?.getReader();
      if (!reader) throw new Error('无法读取响应流');

      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done || controller.signal.aborted) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (data === '[DONE]') continue;
          try {
            const p = JSON.parse(data);
            const ev = p.event || p.type;
            if (ev === 'status') {
              setAiStatus(p.message || '处理中...');
            } else if (ev === 'chunk') {
              setAiStreamingContent(prev => prev + (p.text || p.content || ''));
            } else if (ev === 'done') {
              setAiStatus('');
            }
          } catch { /* ignore */ }
        }
      }
    } catch (err: any) {
      if (controller.signal.aborted || err.name === 'AbortError') return;
      setAiStreamingContent(`**出错了**：${err.message || '请求失败，请重试'}`);
      setAiStatus('');
    } finally {
      if (abortRef.current === controller) {
        setAiLoading(false);
        setAiStatus('');
        abortRef.current = null;
      }
    }
  };

  if (loading) return <p style={{ color: colors['text-tertiary'] }}>加载中...</p>;
  if (!dashboard) return <p style={{ color: colors.danger }}>{error || '班级不存在'}</p>;

  const StatCard = ({ label, value, color }: { label: string; value: string | number; color: string }) => (
    <div style={{
      ...cardStyle, flex: 1, minWidth: 160,
      display: 'flex', flexDirection: 'column', gap: 4,
    }}>
      <span style={{
        fontSize: typography.eyebrow.fontSize,
        fontWeight: typography.eyebrow.fontWeight,
        letterSpacing: typography.eyebrow.letterSpacing,
        textTransform: 'uppercase', color: colors['text-tertiary'],
      }}>{label}</span>
      <span style={{ fontSize: 28, fontWeight: 550, color, lineHeight: 1.1 }}>{value}</span>
    </div>
  );

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
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
          }}>{dashboard.class_name}</h1>
          <p style={{ margin: '4px 0 0', color: colors['text-secondary'], fontSize: typography['body-sm'].fontSize }}>
            数据看板
          </p>
        </div>
        <button onClick={() => navigate('/classes')} style={btnSmallSecondary}>
          <IconBack size={13} color={colors['text-secondary']} /> 返回班级列表
        </button>
      </div>

      {/* 统计卡片 */}
      <div style={{ display: 'flex', gap: space.md, marginBottom: space.xl, flexWrap: 'wrap' }}>
        <StatCard label="学生人数" value={dashboard.student_count} color={colors.success} />
        <StatCard label="总单词量" value={dashboard.total_words} color={colors.info} />
        <StatCard label="平均正确率" value={dashboard.avg_accuracy + '%'} color={colors.warning} />
        <StatCard label="今日活跃" value={dashboard.active_today} color={green.strong} />
      </div>

      {/* 高频错题 */}
      <div style={{ ...cardStyle, marginBottom: space.xl, background: colors['block-lilac'] }}>
        <h3 style={{
          margin: `0 0 ${space.md}px`, fontSize: typography.headline.fontSize,
          fontWeight: typography.headline.fontWeight,
          letterSpacing: typography.headline.letterSpacing,
          color: colors['text-primary'],
        }}>高频错题 TOP 5</h3>
        {dashboard.top_mistakes.length === 0 ? (
          <p style={{ color: colors['text-tertiary'] }}>暂无数据</p>
        ) : (
          dashboard.top_mistakes.map((m, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between',
              padding: '10px 0', borderBottom: `1px solid ${colors['hairline-soft']}`,
              fontSize: typography.body.fontSize,
            }}>
              <span style={{ color: colors['text-primary'] }}>{m.knowledge_point}</span>
              <span style={{ color: colors.danger, fontWeight: 500 }}>{m.count} 次</span>
            </div>
          ))
        )}
      </div>

      {/* AI 智能查询 */}
      <div style={{ ...cardStyle, marginBottom: space.xl, background: colors['block-coral'] }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: xs, marginBottom: space.sm }}>
          <IconBulb size={20} color={colors['text-primary']} />
          <h3 style={{
            margin: 0, fontSize: typography.headline.fontSize,
            fontWeight: typography.headline.fontWeight,
            color: colors['text-primary'],
          }}>AI 智能查询</h3>
        </div>
        <p style={{ fontSize: typography['body-sm'].fontSize, color: colors['text-secondary'], margin: `0 0 ${space.md}px` }}>
          用自然语言提问，小e 分析班级学习数据并给出建议
        </p>
        <div style={{ display: 'flex', gap: space.sm }}>
          <textarea
            value={aiQuestion}
            onChange={(e) => setAiQuestion(e.target.value)}
            placeholder="如：哪些知识点学生最容易出错？基础薄弱的学生应该怎么提高？"
            style={{
              ...inputStyle, flex: 1, minHeight: 60,
              resize: 'vertical', fontSize: typography.body.fontSize,
            }}
          />
          <button
            onClick={handleAiQuery}
            disabled={aiLoading || !aiQuestion.trim()}
            style={{
              ...btnPrimary, alignSelf: 'flex-end',
              background: aiLoading ? colors['text-tertiary'] : colors.primary,
              padding: '10px 20px',
              minHeight: 44,
            }}
          >
            {aiLoading ? '分析中...' : '查询'}
          </button>
        </div>

        {/* 流式加载状态 */}
        {aiLoading && !aiStreamingContent && (
          <div style={{ marginTop: space.md, display: 'flex', alignItems: 'center', gap: 6, padding: '12px 16px', background: colors.canvas, borderRadius: radius.md }}>
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: green.primary, animation: 'pulse 1.4s ease-in-out infinite' }} />
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: green.primary, animation: 'pulse 1.4s ease-in-out 0.2s infinite' }} />
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: green.primary, animation: 'pulse 1.4s ease-in-out 0.4s infinite' }} />
            <span style={{ fontSize: 13, color: colors['text-secondary'], marginLeft: 4 }}>{aiStatus || '小e正在思考...'}</span>
          </div>
        )}

        {/* 流式输出内容 */}
        {aiStreamingContent && (
          <div style={{
            marginTop: space.md, padding: space.md,
            background: colors.canvas, borderRadius: radius.md,
          }}>
            <div style={{
              margin: 0, fontSize: typography.body.fontSize,
              color: colors['text-primary'], lineHeight: 1.7,
              wordBreak: 'break-word',
            }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                code({ className, children, ...props }: any) {
                  if (!className) return <code style={{ background: green.bg2, padding: '2px 6px', borderRadius: 4, fontSize: '0.88em', color: green.strong }} {...props}>{children}</code>;
                  return <pre style={{ background: '#1e293b', color: '#e2e8f0', padding: 14, borderRadius: 8, overflow: 'auto', fontSize: 13, whiteSpace: 'pre-wrap' }}><code className={className} {...props}>{children}</code></pre>;
                },
                p({ children, ...props }: any) {
                  return <p style={{ margin: '0 0 8px', lineHeight: 1.7 }} {...props}>{children}</p>;
                },
                ul({ children, ...props }: any) {
                  return <ul style={{ margin: '0 0 8px', paddingLeft: 20 }} {...props}>{children}</ul>;
                },
                ol({ children, ...props }: any) {
                  return <ol style={{ margin: '0 0 8px', paddingLeft: 20 }} {...props}>{children}</ol>;
                },
                li({ children, ...props }: any) {
                  return <li style={{ marginBottom: 4 }} {...props}>{children}</li>;
                },
                strong({ children, ...props }: any) {
                  return <strong style={{ fontWeight: 600 }} {...props}>{children}</strong>;
                },
                h1({ children, ...props }: any) {
                  return <h1 style={{ fontSize: 18, fontWeight: 600, margin: '12px 0 6px' }} {...props}>{children}</h1>;
                },
                h2({ children, ...props }: any) {
                  return <h2 style={{ fontSize: 16, fontWeight: 600, margin: '10px 0 5px' }} {...props}>{children}</h2>;
                },
                h3({ children, ...props }: any) {
                  return <h3 style={{ fontSize: 14, fontWeight: 600, margin: '8px 0 4px' }} {...props}>{children}</h3>;
                },
              }}>{aiStreamingContent}</ReactMarkdown>
              {aiLoading && (
                <span style={{ display: 'inline-block', width: 2, height: 16, background: colors.primary, marginLeft: 2, verticalAlign: 'middle', animation: 'cursor-blink 0.8s step-end infinite' }} aria-hidden="true" />
              )}
            </div>
          </div>
        )}
      </div>

      {/* 学生列表 */}
      <div style={cardStyle}>
        <h3 style={{
          margin: `0 0 ${space.md}px`, fontSize: typography.headline.fontSize,
          fontWeight: typography.headline.fontWeight,
          color: colors['text-primary'],
        }}>学生列表</h3>
        {students.length === 0 ? (
          <p style={{ color: colors['text-tertiary'] }}>暂无学生加入</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: typography['body-sm'].fontSize }}>
              <thead>
                <tr style={{
                  borderBottom: `1px solid ${colors.hairline}`,
                  color: colors['text-secondary'],
                  fontSize: typography.caption.fontSize,
                  fontWeight: 500,
                  textTransform: 'uppercase',
                  letterSpacing: typography.eyebrow.letterSpacing,
                  textAlign: 'left',
                }}>
                  <th style={{ padding: '10px xs' }}>姓名</th>
                  <th style={{ padding: '10px xs' }}>加入天数</th>
                  <th style={{ padding: '10px xs' }}>单词量</th>
                  <th style={{ padding: '10px xs' }}>训练次数</th>
                  <th style={{ padding: '10px xs' }}>正确率</th>
                  <th style={{ padding: '10px xs' }} />
                </tr>
              </thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.student_id} style={{ borderBottom: `1px solid ${colors['hairline-soft']}` }}>
                    <td style={{ padding: '10px xs', fontWeight: 500, color: colors['text-primary'] }}>{s.nickname}</td>
                    <td style={{ padding: '10px xs', color: colors['text-secondary'] }}>{s.study_days} 天</td>
                    <td style={{ padding: '10px xs', color: colors['text-secondary'] }}>{s.total_words}</td>
                    <td style={{ padding: '10px xs', color: colors['text-secondary'] }}>{s.total_training}</td>
                    <td style={{
                      padding: '10px xs', fontWeight: 500,
                      color: s.avg_accuracy >= 70 ? colors.success : colors.danger,
                    }}>
                      {s.avg_accuracy}%
                    </td>
                    <td style={{ padding: '10px xs' }}>
                      <button
                        onClick={() => navigate(`/classes/${classId}/students/${s.student_id}`)}
                        style={btnSmallSecondary}
                      >
                        详情 <IconArrowRight size={11} color={colors['text-secondary']} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
