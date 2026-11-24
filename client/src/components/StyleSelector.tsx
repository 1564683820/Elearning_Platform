// 视觉风格选择器 — 可复用的视觉风格网格组件
import { VISUAL_STYLES, DEFAULT_VISUAL_STYLE, VisualStyleItem } from '../constants/visualStyles';
import { colors, radius, space, typography, green, cardStyle, IconCheck } from '../design-system';

interface StyleSelectorProps {
  /** 当前选中的风格 key */
  value: string;
  /** 选中回调 */
  onChange: (styleName: string) => void;
  /** 可选：自定义列数，默认 3 */
  columns?: number;
  /** 可选：标题 */
  title?: string;
  /** 可选：描述文字 */
  description?: string;
  /** 可选：卡片样式覆盖 */
  style?: React.CSSProperties;
}

export default function StyleSelector({
  value,
  onChange,
  columns = 3,
  title,
  description,
  style,
}: StyleSelectorProps) {
  return (
    <div style={style}>
      {/* 标题区域 */}
      {title && (
        <h3 style={{
          margin: 0, ...typography.subhead, fontWeight: 600,
          color: colors['text-primary'], marginBottom: 4,
        }}>
          {title}
        </h3>
      )}
      {description && (
        <p style={{
          ...typography['body-sm'], color: colors['text-tertiary'],
          margin: `0 0 ${space.sm}px`,
        }}>
          {description}
        </p>
      )}

      {/* 风格网格 */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gap: space.sm,
      }}>
        {VISUAL_STYLES.map((styleItem: VisualStyleItem) => {
          const isSelected = value === styleItem.name;
          return (
            <div
              key={styleItem.name}
              onClick={() => onChange(styleItem.name)}
              role="radio"
              aria-checked={isSelected}
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onChange(styleItem.name); } }}
              style={{
                borderRadius: radius.md,
                cursor: 'pointer',
                overflow: 'hidden',
                border: isSelected
                  ? `2px solid ${styleItem.color}`
                  : `2px solid ${colors.hairline}`,
                transition: 'all 0.2s ease',
                background: isSelected ? styleItem.bgColor : colors.canvas,
                boxShadow: isSelected
                  ? `0 2px 12px ${styleItem.color}30`
                  : 'none',
                outline: 'none',
              }}
              onMouseEnter={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.borderColor = styleItem.color + '60';
                  e.currentTarget.style.boxShadow = `0 1px 6px ${styleItem.color}15`;
                }
              }}
              onMouseLeave={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.borderColor = colors.hairline;
                  e.currentTarget.style.boxShadow = 'none';
                }
              }}
            >
              {/* 预览色块 */}
              <div style={{
                height: 64,
                background: `linear-gradient(135deg, ${styleItem.bgColor}, ${styleItem.color}15)`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 28,
                position: 'relative',
              }}>
                {styleItem.icon}
                {/* 选中标记 */}
                {isSelected && (
                  <div style={{
                    position: 'absolute', top: 6, right: 6,
                    width: 20, height: 20, borderRadius: '50%',
                    background: styleItem.color,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <IconCheck size={12} color="#fff" />
                  </div>
                )}
              </div>

              {/* 文字信息 */}
              <div style={{
                padding: `${space.sm}px ${space.xs}px`,
                textAlign: 'center',
              }}>
                <div style={{
                  fontWeight: isSelected ? 600 : 500,
                  fontSize: 13,
                  color: isSelected ? styleItem.color : colors['text-primary'],
                  marginBottom: 2,
                }}>
                  {styleItem.label}
                </div>
                <div style={{
                  fontSize: 11,
                  color: colors['text-tertiary'],
                  lineHeight: 1.4,
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}>
                  {styleItem.desc}
                </div>

                {/* 标签 */}
                <div style={{
                  display: 'flex', gap: 3, justifyContent: 'center',
                  marginTop: 6, flexWrap: 'wrap',
                }}>
                  {styleItem.tags.map((tag) => (
                    <span key={tag} style={{
                      padding: '1px 6px',
                      borderRadius: 50,
                      fontSize: 10,
                      background: isSelected ? styleItem.color + '20' : colors['surface-soft'],
                      color: isSelected ? styleItem.color : colors['text-tertiary'],
                    }}>
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
