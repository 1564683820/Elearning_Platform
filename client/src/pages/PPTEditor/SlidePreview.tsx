// 幻灯片内容渲染组件 — 支持 8 种页面类型，使用设计系统绿色主题
import React from 'react';
import {
  colors, green, radius, typography, space, cardStyle,
} from '../../design-system';

interface Props { type: string; content: any; compact?: boolean; showAnswers?: boolean }

export default function SlidePreview({ type, content, compact, showAnswers = true }: Props) {
  if (!content) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: colors['text-tertiary'] }}>
        暂无内容
      </div>
    );
  }
  const s = (large: number, mid: number) => compact ? mid : large;

  switch (type) {
    case 'title':
      return (
        <div style={{ textAlign: 'center', padding: compact ? space.md : 40 }}>
          <h1 style={{
            fontSize: s(32, 22), fontWeight: 700, marginBottom: space.xs,
            color: colors['text-primary'],
          }}>{content.main_title}</h1>
          <p style={{
            fontSize: s(20, 15), color: colors['text-secondary'],
            marginBottom: space.xxs,
          }}>{content.subtitle}</p>
          <p style={{ fontSize: 14, color: colors['text-tertiary'] }}>{content.grade}</p>
        </div>
      );
    case 'objective':
      return (
        <ul style={{ fontSize: s(15, 13), lineHeight: 2, color: colors['text-primary'] }}>
          {(content.items || []).map((item: string, i: number) => <li key={i}>{item}</li>)}
        </ul>
      );
    case 'vocabulary':
      return (
        <div style={{ display: 'grid', gap: compact ? 6 : space.sm }}>
          {(content.words || []).map((w: any, i: number) => (
            <div key={i} style={{
              ...cardStyle, padding: compact ? space.xs : space.md,
            }}>
              <div style={{
                fontSize: s(18, 15), fontWeight: 700, color: colors['text-primary'],
              }}>
                {w.word} <span style={{
                  fontSize: s(14, 12), fontWeight: 400, color: colors['text-tertiary'],
                }}>{w.phonetic}</span>
              </div>
              <div style={{ fontSize: s(14, 12), color: colors['text-secondary'] }}>{w.translation}</div>
              {!compact && (
                <div style={{
                  fontSize: 13, color: colors['text-tertiary'],
                  fontStyle: 'italic', marginTop: space.xxs,
                }}>{w.example}</div>
              )}
            </div>
          ))}
        </div>
      );
    case 'dialogue':
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: compact ? 4 : space.xs }}>
          {(content.dialogues || []).map((d: any, i: number) => (
            <div key={i} style={{
              alignSelf: d.speaker === 'A' ? 'flex-start' : 'flex-end',
              background: d.speaker === 'A' ? green.bg3 : green.bg,
              borderRadius: radius.lg,
              padding: compact ? `${space.xxs}px ${space.sm}px` : `${space.xs}px ${space.md}px`,
              maxWidth: '80%',
            }}>
              <div style={{
                fontWeight: 600, fontSize: s(14, 12), color: colors.success,
              }}>{d.speaker}</div>
              <div style={{
                fontSize: s(15, 13), marginTop: 2, color: colors['text-primary'],
              }}>{d.text}</div>
              {!compact && (
                <div style={{
                  fontSize: 13, color: colors['text-tertiary'], marginTop: 2,
                }}>{d.translation}</div>
              )}
            </div>
          ))}
        </div>
      );
    case 'grammar':
      return (
        <div style={{ display: 'grid', gap: compact ? 6 : space.sm }}>
          {(content.points || []).map((p: any, i: number) => (
            <div key={i} style={{
              ...cardStyle,
              borderLeft: `4px solid ${colors.warning}`,
              padding: compact ? space.xs : space.md,
            }}>
              <div style={{
                fontWeight: 700, fontSize: s(15, 13), marginBottom: space.xxs,
                color: colors['text-primary'],
              }}>{p.rule}</div>
              <div style={{
                fontSize: s(14, 12), color: colors['text-secondary'], marginBottom: space.xxs,
              }}>
                例句：<em>{p.example}</em>
              </div>
              {!compact && (
                <div style={{ fontSize: 13, color: colors['text-tertiary'] }}>{p.explanation}</div>
              )}
            </div>
          ))}
        </div>
      );
    case 'practice':
      return (
        <div style={{ display: 'grid', gap: compact ? 8 : space.md }}>
          {(content.questions || []).map((q: any, i: number) => (
            <div key={i} style={{
              ...cardStyle,
              padding: compact ? space.xs : space.md,
              background: colors.canvas,
            }}>
              <div style={{
                fontWeight: 600, fontSize: s(14, 12), marginBottom: 6,
                color: colors['text-primary'],
              }}>{i + 1}. {q.stem}</div>
              <div style={{ display: 'grid', gap: 2 }}>
                {(q.options || []).map((opt: string, j: number) => (
                  <div key={j} style={{
                    padding: compact ? `${space.xxs}px ${space.xs}px` : `${6}px ${space.sm}px`,
                    borderRadius: radius.sm,
                    background: showAnswers && q.answer === j ? green.bg : colors.canvas,
                    border: showAnswers && q.answer === j
                      ? `1px solid ${colors.success}`
                      : `1px solid ${colors.hairline}`,
                    fontSize: compact ? 12 : 13,
                    color: colors['text-primary'],
                  }}>
                    {String.fromCharCode(65 + j)}. {opt}
                    {showAnswers && q.answer === j && (
                      <span style={{ marginLeft: 8, color: colors.success }}>✓</span>
                    )}
                  </div>
                ))}
              </div>
              {!compact && showAnswers && (
                <div style={{
                  marginTop: 6, fontSize: 12, color: colors['text-secondary'],
                  background: green.bg3, padding: `${space.xxs}px ${space.xs}px`,
                  borderRadius: radius.sm,
                }}>
                  {q.explanation}
                </div>
              )}
            </div>
          ))}
        </div>
      );
    case 'interactive':
      return (
        <div style={{ textAlign: 'center', padding: compact ? space.xs : space.lg }}>
          <h3 style={{
            margin: `0 0 ${space.xs}px`, fontSize: s(18, 15),
            color: colors['text-primary'],
          }}>{content.description || '互动活动'}</h3>
          <ol style={{
            textAlign: 'left', lineHeight: compact ? 1.6 : 2,
            fontSize: s(14, 12), color: colors['text-secondary'],
          }}>
            {(content.steps || []).map((s: string, i: number) => <li key={i}>{s}</li>)}
          </ol>
        </div>
      );
    case 'ai_interaction':
      return (
        <div>
          <div style={{
            background: green.bg3, padding: compact ? space.xs : space.sm,
            borderRadius: radius.md, marginBottom: space.sm, textAlign: 'center',
            border: `1px solid ${green.bg}`,
          }}>
            <span style={{
              fontSize: s(13, 12), color: colors['text-secondary'],
              fontStyle: 'italic',
            }}>💬 {content.prompt || '你对今天学的内容有什么疑问吗？试试向我提问吧！'}</span>
          </div>
          <div style={{ display: 'grid', gap: compact ? 6 : space.xs }}>
            {(content.questions || []).map((q: any, i: number) => (
              <div key={i} style={{
                ...cardStyle, padding: compact ? space.xs : space.md,
                cursor: 'pointer',
                borderLeft: `4px solid ${colors.primary}`,
                transition: 'all 0.2s',
              }}
                onMouseEnter={(e) => { e.currentTarget.style.background = green.bg3; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = colors.canvas; }}
              >
                <div style={{
                  fontWeight: 600, fontSize: s(14, 12), marginBottom: q.hint ? 4 : 0,
                  color: colors['text-primary'],
                }}>{q.question}</div>
                {q.hint && (
                  <div style={{
                    fontSize: s(12, 11), color: colors['text-tertiary'],
                  }}>{q.hint}</div>
                )}
                {!compact && (
                  <div style={{
                    marginTop: 6, fontSize: 11, color: colors.primary,
                    textAlign: 'right', fontWeight: 600,
                  }}>▶ 向AI提问</div>
                )}
              </div>
            ))}
          </div>
          <div style={{
            marginTop: space.xs, fontSize: s(11, 10), color: colors['text-tertiary'],
            textAlign: 'center',
          }}>点击问题向 AI 提问，或输入自己的问题！</div>
        </div>
      );
    case 'summary':
    case 'listening':
      return (
        <div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: space.xs, marginBottom: space.xs,
            padding: `${space.xs}px ${space.sm}px`, background: green.bg3,
            borderRadius: radius.md, border: `1px solid ${green.bg}`,
          }}>
            <span style={{
              fontSize: s(13, 12), color: colors['text-tertiary'],
              fontWeight: 500, textTransform: 'uppercase',
              letterSpacing: 0.5,
            }}>音频</span>
            <span style={{ fontSize: s(13, 12), color: colors['text-secondary'] }}>
              {(content.audio_text || '').substring(0, compact ? 30 : 60)}...
            </span>
          </div>
          {content.subtitle && (
            <div style={{
              fontSize: s(13, 12), color: colors['text-secondary'],
              fontStyle: 'italic', marginBottom: space.xs,
            }}>{content.subtitle}</div>
          )}
          {(content.questions || []).map((q: any, i: number) => (
            <div key={i} style={{
              ...cardStyle, padding: compact ? 6 : space.xs, marginBottom: 6,
            }}>
              <div style={{
                fontWeight: 600, fontSize: s(13, 12), marginBottom: space.xxs,
                color: colors['text-primary'],
              }}>{i + 1}. {q.stem}</div>
              <div style={{ fontSize: s(12, 11), color: colors['text-secondary'] }}>
                {(q.options || []).map((opt: string, j: number) => (
                  <div key={j} style={{ padding: '2px 0' }}>{String.fromCharCode(65 + j)}. {opt}</div>
                ))}
              </div>
            </div>
          ))}
        </div>
      );
    case 'speaking':
      return (
        <div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: space.xs, marginBottom: space.xs,
            padding: `${space.xs}px ${space.sm}px`, background: green.bg3,
            borderRadius: radius.md, border: `1px solid ${green.bg}`,
          }}>
            <span style={{
              fontSize: s(13, 12), color: colors['text-tertiary'],
              fontWeight: 500, textTransform: 'uppercase',
              letterSpacing: 0.5,
            }}>朗读</span>
            <span style={{ fontSize: s(13, 12), color: colors['text-secondary'] }}>
              {(content.text || '').substring(0, compact ? 30 : 60)}...
            </span>
          </div>
          <div style={{
            fontSize: s(15, 13), lineHeight: 1.8, marginBottom: space.xxs,
            color: colors['text-primary'],
          }}>{content.text}</div>
          {content.translation && (
            <div style={{
              fontSize: s(13, 12), color: colors['text-secondary'],
              fontStyle: 'italic', marginBottom: space.xxs,
            }}>{content.translation}</div>
          )}
          {content.tips && (
            <div style={{
              fontSize: s(12, 11), color: colors['text-secondary'],
              background: green.bg3, padding: space.xs, borderRadius: radius.sm,
              borderLeft: `3px solid ${colors.warning}`,
            }}>{content.tips}</div>
          )}
        </div>
      );
    default:
      return (
        <pre style={{
          fontSize: compact ? 11 : 13, color: colors['text-tertiary'],
          whiteSpace: 'pre-wrap',
        }}>
          {JSON.stringify(content, null, 2)}
        </pre>
      );
  }
}
