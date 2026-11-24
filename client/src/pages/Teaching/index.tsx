// 教学页 — 课堂情景对话 & 更多教学工具
import { useNavigate } from 'react-router-dom';
import {
  colors, radius, typography, space, cardStyle,
  btnPrimary, btnSmall,
  IconSpeaker, IconBulb, IconGrid,
} from '../../design-system';

const features = [
  {
    id: 'scene-dialogue',
    title: '课堂情景对话',
    desc: '模拟真实课堂场景，AI 驱动的师生对话练习，支持多轮互动与即时反馈。',
    icon: IconSpeaker,
    status: 'ready' as const,
    path: '/teaching/scene-dialogue',
  },
  {
    id: 'question-bank',
    title: '题库管理',
    desc: '查看记单词训练中的各类练习（单词、语法、阅读、翻译、作文）的题目，支持 AI 批量生成更多题目。',
    icon: IconGrid,
    status: 'ready' as const,
    path: '/question-bank',
  },
  {
    id: 'teaching-assistant',
    title: '教学助手',
    desc: 'AI 驱动的教学辅助对话，支持知识点查询、学生分析、错题总结、备课助手。',
    icon: IconSpeaker,
    status: 'ready' as const,
    path: '/teaching-assistant',
  },
  {
    id: 'more-coming',
    title: '更多功能',
    desc: '更多教学工具即将上线，敬请期待。',
    icon: IconBulb,
    status: 'coming' as const,
    path: null,
  },
];

export default function Teaching() {
  const navigate = useNavigate();

  return (
    <div>
      <div style={{ marginBottom: space.xl }}>
        <h1 style={{ ...typography.headline, margin: 0, color: colors['text-primary'] }}>教学</h1>
        <p style={{ ...typography['body-sm'], color: colors['text-tertiary'], marginTop: 4, marginBottom: 0 }}>
          课堂教学工具集
        </p>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
        gap: space.lg,
      }}>
        {features.map((f) => {
          const Icon = f.icon;
          return (
            <div
              key={f.id}
              style={{
                ...cardStyle,
                cursor: f.status === 'ready' ? 'pointer' : 'default',
                transition: 'box-shadow 0.2s, transform 0.2s',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                minHeight: 200,
              }}
              onClick={() => f.status === 'ready' && f.path && navigate(f.path)}
              onMouseEnter={(e) => {
                if (f.status === 'ready') {
                  e.currentTarget.style.boxShadow = '0 6px 24px rgba(0,0,0,0.10)';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.boxShadow = '';
                e.currentTarget.style.transform = '';
              }}
            >
              <div>
                <div style={{
                  width: 44, height: 44, borderRadius: radius.md,
                  background: f.status === 'ready' ? colors['block-lime'] : colors['surface-soft'],
                  display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: space.md,
                }}>
                  <Icon size={22} color={f.status === 'ready' ? colors.primary : colors['text-tertiary']} />
                </div>
                <h3 style={{ margin: '0 0 6px', fontSize: 16, fontWeight: 600, color: colors['text-primary'] }}>
                  {f.title}
                </h3>
                <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: colors['text-tertiary'] }}>
                  {f.desc}
                </p>
              </div>
              <div style={{ marginTop: space.md, display: 'flex', alignItems: 'center', gap: 8 }}>
                {f.status === 'ready' ? (
                  <span style={{ ...btnSmall, padding: '5px 16px', fontSize: 12 }}>进入</span>
                ) : (
                  <span style={{
                    display: 'inline-block', padding: '5px 14px', borderRadius: radius.pill,
                    background: colors['surface-soft'], color: colors['text-tertiary'],
                    fontSize: 12, fontWeight: 500,
                  }}>
                    即将上线
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
