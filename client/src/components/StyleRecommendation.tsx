// 风格推荐面板 — 调用 /teacher/ppt/analyze-content 展示 AI 推荐的视觉风格
import { useState, useEffect, useCallback } from 'react';
import { teacherApi } from '../api/teacher';
import { getVisualStyle, DEFAULT_VISUAL_STYLE } from '../constants/visualStyles';
import type { VisualStyleItem } from '../constants/visualStyles';
import {
  colors, green, radius, space, typography, cardStyle,
  btnPrimary, btnSecondary, btnSmall, btnSmallSecondary,
  IconBulb, IconCheck, IconRefresh, IconArrowRight,
  IconBook, IconChart, IconClock, IconActivity, IconPpt,
} from '../design-system';

// 内容分析返回类型
interface ContentProfileData {
  pageCount: number;
  totalWordCount: number;
  avgWordsPerPage: number;
  contentDensity: string;
  typeDistribution: Record<string, number>;
  dominantType: string;
  vocabularyCount: number;
  dialogueCount: number;
  questionCount: number;
  hasAiInteraction: boolean;
  hasListening: boolean;
  hasSpeaking: boolean;
  hasCatalog: boolean;
  estimatedDurationMinutes: number;
}

interface StyleCandidate {
  style: string;
  reason: string;
}

interface AnalysisResult {
  profile: ContentProfileData;
  recommendedStyle: string;
  layoutStrategy: Record<string, string>;
  styleCandidates: StyleCandidate[];
}

interface StyleRecommendationProps {
  /** 页面数据（知识图谱 sections 构建的页面列表） */
  pages: Record<string, unknown>[];
  /** 收到分析结果时的回调 */
  onChange?: (result: AnalysisResult) => void;
  /** 用户选中推荐风格的回调 */
  onSelectStyle?: (styleName: string) => void;
  /** 可选：外部组件样式 */
  style?: React.CSSProperties;
}

export default function StyleRecommendation({
  pages,
  onChange,
  onSelectStyle,
  style,
}: StyleRecommendationProps) {
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState<string>('');

  // 执行内容分析
  const analyze = useCallback(async () => {
    if (!pages || pages.length === 0) {
      setError('没有可分析的页面数据');
      return;
    }
    setAnalyzing(true);
    setError('');
    try {
      const data = await teacherApi.ppt.analyzeContent({ pages });
      setResult(data as unknown as AnalysisResult);
      setSelectedCandidate(data.recommendedStyle);
      onChange?.(data as unknown as AnalysisResult);
    } catch (e: any) {
      setError(e.message || '内容分析失败，请稍后重试');
      setResult(null);
    } finally {
      setAnalyzing(false);
    }
  }, [pages, onChange]);

  // 页面数据变化时自动重新分析
  useEffect(() => {
    if (pages && pages.length > 0) {
      analyze();
    }
  }, []); // 仅在挂载时分析一次，避免频繁请求

  // 密度标签映射
  const densityLabel: Record<string, string> = {
    sparse: '稀疏',
    medium: '适中',
    dense: '密集',
  };

  // 类型标签映射
  const typeLabels: Record<string, string> = {
    title_slide: '封面',
    catalog: '目录',
    objective: '学习目标',
    vocabulary: '词汇',
    dialogue: '对话',
    grammar: '语法',
    practice: '练习题',
    listening: '听力',
    speaking: '口语',
    interactive: '互动活动',
    ai_interaction: 'AI互动',
    summary: '总结',
    content: '内容',
  };

  // 渲染加载中
  if (analyzing) {
    return (
      <div style={{
        ...cardStyle,
        background: `linear-gradient(135deg, ${green.bg3}, ${colors.canvas})`,
        borderColor: colors.success + '20',
        ...style,
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: space.sm,
          padding: space.md,
        }}>
          <div style={{
            width: 48, height: 48, borderRadius: '50%',
            background: `linear-gradient(135deg, ${colors.success}, ${green.soft})`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <IconBulb size={22} color="#fff" />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ ...typography.subhead, fontWeight: 600, color: colors['text-primary'] }}>
              AI 正在分析内容特征...
            </div>
            <div style={{
              display: 'flex', alignItems: 'center', gap: space.xs,
              ...typography['body-sm'], color: colors['text-secondary'],
            }}>
              <div style={{
                width: 12, height: 12, border: `2px solid ${colors.success}`,
                borderTopColor: 'transparent', borderRadius: '50%',
                animation: 'spin 0.6s linear infinite',
              }} />
              <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
              分析页面内容、类型分布、推荐最佳视觉风格
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 渲染错误
  if (error || !result) {
    return (
      <div style={{
        ...cardStyle,
        background: '#fef2f2', borderColor: colors.danger + '20',
        ...style,
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: space.md,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: space.sm }}>
            <IconBulb size={18} color={colors.danger} />
            <span style={{ ...typography['body-sm'], color: colors.danger }}>
              {error || '暂无分析结果'}
            </span>
          </div>
          <button onClick={analyze} style={{
            ...btnSmallSecondary, padding: '4px 12px', fontSize: 12,
          }}>
            <IconRefresh size={12} color={colors['text-secondary']} />
            重试
          </button>
        </div>
      </div>
    );
  }

  const { profile, recommendedStyle, styleCandidates, layoutStrategy } = result;
  const candidateStyles = styleCandidates.slice(1, 4); // 展示 Top 2-3 候选项

  return (
    <div style={style}>
      {/* 推荐结果卡片 */}
      <div style={{
        ...cardStyle,
        background: `linear-gradient(135deg, ${green.bg3}, ${colors.canvas})`,
        borderColor: colors.success + '20',
        marginBottom: space.sm,
      }}>
        {/* 头部 — 推荐风格高亮 */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: space.md,
          padding: space.md,
          borderBottom: `1px solid ${colors.success}15`,
        }}>
          <div style={{
            width: 56, height: 56, borderRadius: radius.lg,
            background: `linear-gradient(135deg, ${colors.success}, ${green.soft})`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
            boxShadow: `0 2px 12px ${colors.success}30`,
          }}>
            <IconBulb size={26} color="#fff" />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{
              ...typography.eyebrow, color: colors.success, fontWeight: 600,
              textTransform: 'uppercase', marginBottom: 2,
            }}>
              AI 智能推荐
            </div>
            <div style={{ ...typography.subhead, fontWeight: 600, color: colors['text-primary'] }}>
              推荐使用「
              <span style={{ color: colors.success }}>
                {getVisualStyle(recommendedStyle).label}
              </span>
              」风格
            </div>
            <div style={{ ...typography['body-sm'], color: colors['text-secondary'], marginTop: 2 }}>
              {styleCandidates[0]?.reason || '根据内容特征自动匹配最佳视觉风格'}
            </div>
          </div>
          {/* 一键应用推荐 */}
          <button
            onClick={() => onSelectStyle?.(recommendedStyle)}
            style={{
              ...btnPrimary,
              padding: '10px 20px', fontSize: 14, fontWeight: 600,
              borderRadius: radius.md, gap: 6,
            }}
          >
            <IconCheck size={14} color="#fff" />
            使用推荐
          </button>
        </div>

        {/* 内容概览 */}
        <div style={{
          display: 'flex', gap: space.sm,
          padding: `${space.sm}px ${space.md}px`,
          borderBottom: `1px solid ${colors.success}10`,
          flexWrap: 'wrap',
        }}>
          <StatBadge icon={<IconPpt size={12} />} label="页数" value={String(profile.pageCount)} />
          <StatBadge icon={<IconBook size={12} />} label="总字数" value={`约${profile.totalWordCount}`} />
          <StatBadge icon={<IconClock size={12} />} label="预估时长" value={`${profile.estimatedDurationMinutes}分钟`} />
          <StatBadge icon={<IconChart size={12} />} label="密度" value={densityLabel[profile.contentDensity] || profile.contentDensity} />
          <StatBadge icon={<IconActivity size={12} />} label="主要类型" value={typeLabels[profile.dominantType] || profile.dominantType} />
          {profile.vocabularyCount > 0 && (
            <StatBadge icon="📝" label="词汇" value={String(profile.vocabularyCount)} />
          )}
          {profile.dialogueCount > 0 && (
            <StatBadge icon="💬" label="对话" value={String(profile.dialogueCount)} />
          )}
          {profile.questionCount > 0 && (
            <StatBadge icon="❓" label="题目" value={String(profile.questionCount)} />
          )}
        </div>

        {/* 类型分布条 */}
        {Object.keys(profile.typeDistribution).length > 0 && (
          <div style={{
            padding: `${space.sm}px ${space.md}px`,
            borderBottom: `1px solid ${colors.success}10`,
          }}>
            <div style={{
              ...typography.caption, color: colors['text-tertiary'],
              marginBottom: space.xs,
            }}>
              页面类型分布
            </div>
            <div style={{
              display: 'flex', height: 6, borderRadius: radius.pill,
              overflow: 'hidden', gap: 2,
            }}>
              {Object.entries(profile.typeDistribution).map(([type, count]) => {
                const pct = ((count / profile.pageCount) * 100).toFixed(0);
                return (
                  <div
                    key={type}
                    title={`${typeLabels[type] || type}: ${count} 页 (${pct}%)`}
                    style={{
                      flex: count,
                      height: '100%',
                      borderRadius: radius.pill,
                      background: type === profile.dominantType
                        ? `linear-gradient(90deg, ${colors.success}, ${green.soft})`
                        : colors['surface-soft'],
                      transition: 'all 0.3s',
                    }}
                  />
                );
              })}
            </div>
          </div>
        )}

        {/* 备选方案 */}
        {candidateStyles.length > 0 && (
          <div style={{ padding: `${space.sm}px ${space.md}px ${space.md}px` }}>
            <div style={{
              ...typography.caption, color: colors['text-tertiary'],
              marginBottom: space.xs,
            }}>
              其他推荐方案
            </div>
            <div style={{ display: 'flex', gap: space.sm, flexWrap: 'wrap' }}>
              {candidateStyles.map((candidate) => {
                const styleItem = getVisualStyle(candidate.style);
                const isActive = selectedCandidate === candidate.style;
                return (
                  <button
                    key={candidate.style}
                    onClick={() => {
                      setSelectedCandidate(candidate.style);
                      onSelectStyle?.(candidate.style);
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: space.xs,
                      padding: `${space.xs}px ${space.sm}px`,
                      borderRadius: radius.pill,
                      border: isActive
                        ? `1.5px solid ${styleItem.color}`
                        : `1px solid ${colors.hairline}`,
                      background: isActive ? styleItem.bgColor : colors.canvas,
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      outline: 'none',
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive) e.currentTarget.style.borderColor = styleItem.color + '60';
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) e.currentTarget.style.borderColor = colors.hairline;
                    }}
                  >
                    <span style={{ fontSize: 16 }}>{styleItem.icon}</span>
                    <div style={{ textAlign: 'left' }}>
                      <div style={{
                        ...typography['body-sm'], fontWeight: 600,
                        color: isActive ? styleItem.color : colors['text-primary'],
                      }}>
                        {styleItem.label}
                      </div>
                      <div style={{
                        fontSize: 11, color: colors['text-tertiary'],
                        lineHeight: 1.3, maxWidth: 200,
                      }}>
                        {candidate.reason}
                      </div>
                    </div>
                    {isActive && <IconCheck size={12} color={styleItem.color} />}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* 布局策略建议 */}
        {layoutStrategy && Object.keys(layoutStrategy).length > 0 && (
          <div style={{
            padding: `0 ${space.md}px ${space.md}px`,
          }}>
            <div style={{
              ...typography.caption, color: colors['text-tertiary'],
              marginBottom: space.xs,
            }}>
              布局策略建议
            </div>
            <div style={{ display: 'flex', gap: space.xs, flexWrap: 'wrap' }}>
              {Object.entries(layoutStrategy).map(([type, layout]) => (
                <span key={type} style={{
                  padding: '2px 10px', borderRadius: radius.pill,
                  fontSize: 11, fontWeight: 500,
                  background: green.bg3, color: colors.success,
                  border: `1px solid ${colors.success}20`,
                }}>
                  {typeLabels[type] || type} → {layout}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 刷新按钮 */}
      <div style={{ textAlign: 'right', marginBottom: space.sm }}>
        <button
          onClick={analyze}
          disabled={analyzing}
          style={{
            ...btnSmallSecondary, padding: '4px 12px', fontSize: 12, gap: 4,
          }}
        >
          <IconRefresh size={12} color={colors['text-tertiary']} />
          重新分析
        </button>
      </div>
    </div>
  );
}

// 统计徽章子组件
function StatBadge({
  icon, label, value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 4,
      padding: '3px 10px',
      borderRadius: radius.pill,
      background: colors.canvas,
      border: `1px solid ${colors.success}15`,
    }}>
      <span style={{ color: colors.success }}>{icon}</span>
      <span style={{ ...typography.caption, color: colors['text-tertiary'] }}>{label}</span>
      <span style={{ ...typography.caption, fontWeight: 600, color: colors.success }}>{value}</span>
    </div>
  );
}
