// 教学助手 — Agent Skills 管理面板（按PPT/试卷分类）
import { useState, useEffect, useCallback, useRef } from 'react';
import { teachingAssistantApi, SkillItem, SkillType, SKILL_TYPE_LABELS } from '../../api/teachingAssistant';
import { SKILL_FILE_ACCEPT, useQASkillUpload } from '../../shared/qaSkillUpload';

/* ========== Design Tokens ========== */
const T = {
  accent: '#5B9E6F',
  accentGradient: 'linear-gradient(135deg, #2d7d46, #5B9E6F)',
  green: {
    strong: '#2d7d46',
    mid: '#3d7a4e',
    primary: '#5B9E6F',
    soft: '#88c8a0',
    bg: '#e6f7e6',
    bg2: '#d4edda',
  },
  textPri: '#0f172a',
  textSec: '#475569',
  textTer: '#94a3b8',
  border: '#e2e8f0',
  borderLight: '#f1f5f9',
  surface: '#ffffff',
  surfaceSoft: '#f5f7fa',
  shadowSm: '0 1px 3px rgba(0,0,0,0.04)',
  shadowMd: '0 4px 16px rgba(0,0,0,0.06)',
  shadowLg: '0 12px 40px rgba(0,0,0,0.12)',
  rSm: 6,
  rMd: 10,
  rLg: 14,
};

const TYPE_COLORS: Record<SkillType, { bg: string; text: string; border: string }> = {
  ppt: { bg: '#e6f7e6', text: '#2d7d46', border: '#88c8a0' },
  exam: { bg: '#fff7e6', text: '#ad6800', border: '#ffd591' },
  qa: { bg: '#e6f7e6', text: '#2d7d46', border: '#88c8a0' },
};

function formatDate(s: string): string {
  const d = new Date(s);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// 技能图标 SVG
const SkillSvg = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

// 关闭图标 SVG
const CloseSvg = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const DeleteSvg = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
  </svg>
);

const DocSvg = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
    <polyline points="10 9 9 9 8 9" />
  </svg>
);

const CheckSvg = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const UploadSvg = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

interface SkillManagerProps {
  visible: boolean;
  onClose: () => void;
}

export default function SkillManager({ visible, onClose }: SkillManagerProps) {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadType, setUploadType] = useState<SkillType>('ppt');
  const [activeTab, setActiveTab] = useState<SkillType | 'all'>('all');
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const qaUpload = useQASkillUpload();

  const loadSkills = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await teachingAssistantApi.listSkills();
      setSkills(res.items || []);
    } catch {
      setError('加载技能列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (visible) {
      loadSkills();
      setSuccessMsg('');
      setError('');
    }
  }, [visible, loadSkills]);

  const showToast = (msg: string) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(''), 3000);
  };

  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (uploadType === 'qa') {
      setError('');
      qaUpload.select(file);
      e.currentTarget.value = '';
      return;
    }
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (ext !== 'md' && ext !== 'markdown') {
      setError('仅支持 .md 或 .markdown 格式的 SKILL 文件');
      e.target.value = '';
      return;
    }

    // 检查是否已有同名同类型技能
    if (skills.some(s => s.file_name === file.name && s.skill_type === uploadType)) {
      const typeLabel = SKILL_TYPE_LABELS[uploadType];
      setError(`${typeLabel}技能"${file.name}"已存在，请先删除后再上传`);
      e.target.value = '';
      return;
    }

    setUploading(true);
    setError('');
    try {
      const result = await teachingAssistantApi.uploadSkill(file, uploadType);
      showToast(`${SKILL_TYPE_LABELS[result.skill_type]}技能"${result.name}"上传成功`);
      await loadSkills();
    } catch (err: any) {
      setError(err.message || '上传失败');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  }, [skills, uploadType, loadSkills, qaUpload]);

  async function submitQASkill() {
    const saved = await qaUpload.submit();
    if (saved) {
      setActiveTab('qa');
      showToast('Skill 已上传');
      await loadSkills();
    }
  }

  const handleActivate = useCallback(async (skillId: string, name: string) => {
    try {
      await teachingAssistantApi.activateSkill(skillId);
      showToast(`已激活技能"${name}"`);
      await loadSkills();
    } catch {
      setError('激活失败');
    }
  }, [loadSkills]);

  const handleDeactivate = useCallback(async (skillId: string, name: string) => {
    try {
      await teachingAssistantApi.deactivateSkill(skillId);
      showToast(`已停用技能"${name}"`);
      await loadSkills();
    } catch {
      setError('停用失败');
    }
  }, [loadSkills]);

  const handleDelete = useCallback(async (skillId: string, name: string) => {
    if (!window.confirm(`确定要删除技能"${name}"吗？此操作不可撤销。`)) return;
    try {
      await teachingAssistantApi.deleteSkill(skillId);
      showToast(`技能"${name}"已删除`);
      await loadSkills();
    } catch {
      setError('删除失败');
    }
  }, [loadSkills]);

  // 按类型过滤 + 已激活排前面
  const filteredSkills = skills
    .filter(s => activeTab === 'all' || s.skill_type === activeTab)
    .sort((a, b) => {
      if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
      return 0;
    });

  const pptSkills = skills.filter(s => s.skill_type === 'ppt');
  const examSkills = skills.filter(s => s.skill_type === 'exam');
  const qaSkills = skills.filter(s => s.skill_type === 'qa');
  const activePpt = pptSkills.find(s => s.is_active);
  const activeExam = examSkills.find(s => s.is_active);

  if (!visible) return null;

  function closeManager() {
    if (qaUpload.busy) return;
    qaUpload.select();
    onClose();
  }

  // 样式
  const overlayStyle: React.CSSProperties = {
    position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
    background: 'rgba(0,0,0,0.35)', zIndex: 1000,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  };

  const panelStyle: React.CSSProperties = {
    width: 520, maxHeight: '82vh', background: T.surface,
    borderRadius: T.rLg, boxShadow: T.shadowLg,
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  };

  const headerStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '16px 20px', borderBottom: `1px solid ${T.borderLight}`, flexShrink: 0,
  };

  const bodyStyle: React.CSSProperties = {
    flex: 1, overflowY: 'auto', padding: '16px 20px',
  };

  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: '6px 14px', borderRadius: 20, border: 'none',
    background: active ? T.accentGradient : 'transparent',
    color: active ? '#fff' : T.textSec, cursor: 'pointer',
    fontSize: 12, fontWeight: active ? 600 : 500,
    transition: 'all 0.15s', whiteSpace: 'nowrap',
  });

  const typeSelectStyle: React.CSSProperties = {
    padding: '5px 8px', borderRadius: T.rSm, border: `1px solid ${T.border}`,
    background: T.surface, color: T.textPri, fontSize: 12, cursor: 'pointer',
    outline: 'none',
  };

  return (
    <div style={overlayStyle} onClick={(e) => { if (e.target === e.currentTarget) closeManager(); }}
      role="dialog" aria-modal="true" aria-label="Agent Skills 管理">
      <div style={panelStyle} onClick={e => e.stopPropagation()}>
        {/* 头部 */}
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: T.accent }}><SkillSvg /></span>
            <span style={{ fontSize: 15, fontWeight: 600, color: T.textPri }}>技能管理</span>
          </div>
          <button style={{
            width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: 'none', background: 'transparent', cursor: 'pointer', color: T.textTer,
            borderRadius: '50%', transition: 'background 0.15s',
          }} onClick={closeManager} disabled={qaUpload.busy} aria-label="关闭"
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = T.borderLight; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}>
            <CloseSvg />
          </button>
        </div>

        {/* 内容 */}
        <div style={bodyStyle}>
          {/* 提示信息 */}
          {successMsg && (
            <div style={{ padding: '8px 14px', borderRadius: T.rSm, background: T.green.bg, color: T.green.strong, fontSize: 13, marginBottom: 12, border: `1px solid ${T.green.bg2}` }}>
              {successMsg}
            </div>
          )}
          {error && (
            <div style={{ padding: '8px 14px', borderRadius: T.rSm, background: '#fff2f0', color: '#cf1322', fontSize: 13, marginBottom: 12, border: '1px solid #ffccc7' }}>
              {error}
            </div>
          )}

          {/* 上传区域 — 含类型选择器 */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <label style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              padding: '12px', border: `2px dashed ${uploading ? T.accent : T.border}`, borderRadius: T.rMd,
              background: uploading ? T.green.bg : T.surfaceSoft, cursor: uploading ? 'wait' : 'pointer',
              transition: 'all 0.2s', opacity: uploading ? 0.6 : 1,
            }}
              onMouseEnter={e => { if (!uploading) { const el = e.currentTarget as HTMLElement; el.style.borderColor = T.accent; el.style.background = T.green.bg; } }}
              onMouseLeave={e => { if (!uploading) { const el = e.currentTarget as HTMLElement; el.style.borderColor = T.border; el.style.background = T.surfaceSoft; } }}>
              <UploadSvg />
              <span style={{ fontSize: 13, fontWeight: 500, color: uploading ? T.textTer : T.accent }}>
                {uploading ? '上传中...' : '上传 SKILL.md'}
              </span>
              <input ref={fileInputRef} type="file" style={{ position: 'absolute', top: 0, left: 0, width: 0, height: 0, opacity: 0 }}
                accept={SKILL_FILE_ACCEPT} onChange={handleUpload} disabled={uploading || qaUpload.busy} />
            </label>
            <select value={uploadType} disabled={uploading || qaUpload.busy} onChange={e => {
              qaUpload.select();
              setUploadType(e.target.value as SkillType);
            }}
              style={typeSelectStyle} title="选择技能类型">
              <option value="ppt">📊 PPT设计</option>
              <option value="exam">📝 试卷设计</option>
              <option value="qa">问答</option>
            </select>
          </div>
          {uploadType === 'qa' && qaUpload.file && <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ overflowWrap: 'anywhere' }}>{qaUpload.file.name}</span>
              <button type="button" style={tabStyle(false)} disabled={qaUpload.busy} onClick={() => qaUpload.select()}>取消</button>
              <button type="button" style={tabStyle(true)} disabled={Boolean(qaUpload.invalid) || qaUpload.busy}
                onClick={() => void submitQASkill()}>{qaUpload.busy ? '上传中…' : '确认上传'}</button>
            </div>
            {qaUpload.error && <p role="alert" style={{ color: '#9c392c' }}>{qaUpload.error}</p>}
          </div>}

          {/* 分类标签卡片 — 显示每个类型的激活状态 */}
          <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            {(['ppt', 'exam'] as SkillType[]).map(st => {
              const stSkills = st === 'ppt' ? pptSkills : examSkills;
              const stActive = st === 'ppt' ? activePpt : activeExam;
              const tc = TYPE_COLORS[st];
              return (
                <div key={st} style={{
                  flex: 1, padding: '10px 12px', borderRadius: T.rMd,
                  background: stActive ? tc.bg : T.surfaceSoft,
                  border: `1px solid ${stActive ? tc.border : T.borderLight}`,
                  transition: 'all 0.15s',
                }}>
                  <div style={{ fontSize: 12, color: T.textTer, marginBottom: 2 }}>
                    {SKILL_TYPE_LABELS[st]} · {stSkills.length}个技能
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: stActive ? tc.text : T.textSec }}>
                    {stActive ? `● ${stActive.name}` : '未激活'}
                  </div>
                </div>
              );
            })}
          </div>

          {/* 分类 Tab */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <button style={tabStyle(activeTab === 'all')} onClick={() => setActiveTab('all')}>
              全部 ({skills.length})
            </button>
            <button style={tabStyle(activeTab === 'ppt')} onClick={() => setActiveTab('ppt')}>
              📊 PPT设计 ({pptSkills.length})
            </button>
            <button style={tabStyle(activeTab === 'exam')} onClick={() => setActiveTab('exam')}>
              📝 试卷设计 ({examSkills.length})
            </button>
            <button style={tabStyle(activeTab === 'qa')} onClick={() => setActiveTab('qa')}>
              问答 ({qaSkills.length})
            </button>
          </div>

          {/* 分隔 */}
          <div style={{ fontSize: 12, fontWeight: 600, color: T.textTer, marginBottom: 8 }}>
            {skills.length > 0 ? `共 ${skills.length} 个技能` : '暂无技能'}
          </div>

          {/* 加载中 */}
          {loading && (
            <div style={{ textAlign: 'center', padding: 20, color: T.textTer, fontSize: 13 }}>加载中...</div>
          )}

          {/* 空状态 */}
          {!loading && filteredSkills.length === 0 && (
            <div style={{ textAlign: 'center', padding: 24, color: T.textTer, fontSize: 13 }}>
              <div style={{ marginBottom: 8, opacity: 0.4 }}><DocSvg /></div>
              {activeTab === 'all'
                ? '还没有上传任何技能\n上传 SKILL.md 文件来定制小e的设计风格'
                : `还没有${SKILL_TYPE_LABELS[activeTab]}技能\n上传 SKILL.md 并选择"${SKILL_TYPE_LABELS[activeTab]}"类型`}
            </div>
          )}

          {/* 技能列表 */}
          <div style={{ maxHeight: 300, overflowY: 'auto' }}>
            {filteredSkills.map(skill => {
              const isActive = skill.is_active;
              const tc = TYPE_COLORS[skill.skill_type];
              return (
                <div key={skill.id} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 12,
                  padding: '12px 14px', borderRadius: T.rMd,
                  background: isActive ? tc.bg : T.surfaceSoft,
                  border: `1px solid ${isActive ? tc.border : T.borderLight}`,
                  marginBottom: 8, transition: 'all 0.15s',
                }} onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLElement).style.borderColor = tc.border; }}
                  onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLElement).style.borderColor = T.borderLight; }}>
                  {/* 图标 */}
                  <div style={{
                    width: 36, height: 36, borderRadius: 8,
                    background: isActive ? tc.bg + '80' : T.borderLight,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: isActive ? tc.text : T.textTer, flexShrink: 0,
                  }}>
                    <DocSvg />
                  </div>
                  {/* 信息 */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: T.textPri }}>
                        {skill.name}
                      </span>
                      {/* 类型标签 */}
                      <span style={{
                        fontSize: 10, fontWeight: 500, padding: '1px 6px', borderRadius: 8,
                        background: tc.bg, color: tc.text, border: `1px solid ${tc.border}`,
                      }}>
                        {SKILL_TYPE_LABELS[skill.skill_type]}
                      </span>
                      {isActive && (
                        <span style={{
                          fontSize: 10, fontWeight: 600, color: '#ffffff', background: T.accentGradient,
                          padding: '1px 6px', borderRadius: 10, lineHeight: '16px',
                        }}>
                          生效中
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: T.textSec, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {skill.description || '无描述'}
                    </div>
                    <div style={{ fontSize: 11, color: T.textTer, marginTop: 2 }}>
                      {formatDate(skill.created_at)} · {skill.file_name}
                    </div>
                  </div>
                  {/* 操作按钮 */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flexShrink: 0 }}>
                    {skill.skill_type === 'qa' ? null : isActive ? (
                      <button style={{
                        padding: '4px 10px', border: `1px solid ${T.border}`, borderRadius: T.rSm,
                        background: T.surface, color: T.textSec, cursor: 'pointer', fontSize: 11,
                        transition: 'all 0.15s', whiteSpace: 'nowrap',
                      }} onClick={() => handleDeactivate(skill.id, skill.name)}
                        onMouseEnter={e => {
                          const el = e.currentTarget as HTMLElement;
                          el.style.borderColor = '#dc3545'; el.style.color = '#dc3545';
                        }}
                        onMouseLeave={e => {
                          const el = e.currentTarget as HTMLElement;
                          el.style.borderColor = T.border; el.style.color = T.textSec;
                        }}>
                        停用
                      </button>
                    ) : (
                      <button style={{
                        padding: '4px 10px', border: 'none', borderRadius: T.rSm,
                        background: T.accentGradient, color: '#ffffff', cursor: 'pointer', fontSize: 11,
                        fontWeight: 500, transition: 'opacity 0.15s', whiteSpace: 'nowrap',
                      }} onClick={() => handleActivate(skill.id, skill.name)}
                        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '0.85'; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                          <CheckSvg /> 启用
                        </span>
                      </button>
                    )}
                    <button style={{
                      padding: '4px 10px', border: 'none', borderRadius: T.rSm,
                      background: 'transparent', color: T.textTer, cursor: 'pointer', fontSize: 11,
                      transition: 'all 0.15s', whiteSpace: 'nowrap',
                    }} onClick={() => handleDelete(skill.id, skill.name)}
                      onMouseEnter={e => {
                        const el = e.currentTarget as HTMLElement;
                        el.style.background = '#fff2f0'; el.style.color = '#cf1322';
                      }}
                      onMouseLeave={e => {
                        const el = e.currentTarget as HTMLElement;
                        el.style.background = 'transparent'; el.style.color = T.textTer;
                      }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                        <DeleteSvg /> 删除
                      </span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
