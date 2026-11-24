// 系统状态页 — 查看各服务连接状态 + 编辑 LLM/MySQL 配置
import { useState, useEffect, useCallback } from 'react';
import client from '../../api/client';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary, chipStyle,
  inputStyle, labelStyle,
  IconRefresh, IconEdit, IconX, IconCheck,
} from '../../design-system';

interface ServiceStatus {
  name: string;
  status: string;
  latency_ms: number | null;
  detail: string;
  extras?: Record<string, any>;
  config?: Record<string, any>;
}

interface SystemStatusData {
  overall: string;
  services: ServiceStatus[];
  timestamp: string;
}

interface ConfigData {
  effective: Record<string, any>;
  overrides: Record<string, any>;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  ok:       { label: '正常',   color: '#2d7d46', bg: '#e8f5e9' },
  degraded: { label: '降级',   color: '#5B9E6F', bg: '#e6f7e6' },
  warning:  { label: '告警',   color: '#c77600', bg: '#fff8e1' },
  error:    { label: '异常',   color: '#c62828', bg: '#ffebee' },
};

// Service SVG icons (inline, no emoji)
function SvcIcon({ name, size = 22 }: { name: string; size?: number }) {
  const c = '#888';
  switch (name) {
    case 'MySQL':
      return (
        <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke={c} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="4" width="16" height="13" rx="2" /><path d="M2 8h16" /><path d="M7 12h6" />
        </svg>
      );
    case 'Redis':
      return (
        <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke={c} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="10" cy="10" r="7" /><path d="M10 6v4l3 2" />
        </svg>
      );
    case 'Milvus':
      return (
        <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke={c} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 2l6 3v6l-6 3-6-3V5l6-3z" /><path d="M10 8l6-3" /><path d="M10 8v6" /><path d="M4 5l6 3" />
        </svg>
      );
    case 'LLM 服务':
      return (
        <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke={c} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 8a5 5 0 0 1 10 0c0 3-2 5-3 6v2H8v-2c-1-1-3-3-3-6z" /><path d="M8 18h4" />
        </svg>
      );
    case 'Embedding 服务':
      return (
        <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke={c} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="3" width="7" height="6" rx="1" /><rect x="11" y="3" width="7" height="6" rx="1" />
          <rect x="2" y="12" width="7" height="6" rx="1" /><rect x="11" y="12" width="7" height="6" rx="1" />
        </svg>
      );
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke={c} strokeWidth="1.5">
          <circle cx="10" cy="10" r="8" /><path d="M10 6v4l3 3" />
        </svg>
      );
  }
}

const XS = 8;

interface EditableField {
  key: string;
  label: string;
  type: 'text' | 'password' | 'number';
  placeholder?: string;
}

const EDITABLE_SERVICES: Record<string, { title: string; fields: EditableField[] }> = {
  MySQL: {
    title: 'MySQL 配置',
    fields: [
      { key: 'MYSQL_HOST', label: '主机', type: 'text', placeholder: '127.0.0.1' },
      { key: 'MYSQL_PORT', label: '端口', type: 'number', placeholder: '3306' },
      { key: 'MYSQL_USER', label: '用户名', type: 'text', placeholder: 'root' },
      { key: 'MYSQL_PASSWORD', label: '密码', type: 'password', placeholder: '********' },
      { key: 'MYSQL_DATABASE', label: '数据库名', type: 'text', placeholder: 'elearningtest' },
    ],
  },
  'LLM 服务': {
    title: 'LLM 配置',
    fields: [
      { key: 'LLM_API_BASE', label: 'API 地址', type: 'text', placeholder: 'https://api.openai.com/v1' },
      { key: 'LLM_API_KEY', label: 'API Key', type: 'password', placeholder: 'sk-...' },
      { key: 'LLM_MODEL', label: '模型', type: 'text', placeholder: 'gpt-4' },
    ],
  },
};

export default function SystemStatus() {
  const [data, setData] = useState<SystemStatusData | null>(null);
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [openEdit, setOpenEdit] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchStatus = useCallback(async (silent = false) => {
    if (!silent) setLoading(true); else setRefreshing(true);
    setError('');
    try {
      const res = await client.get('/system/status');
      setData(res.data.data || res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || '获取状态失败');
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }, []);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await client.get('/system/config');
      setConfig(res.data.data || res.data);
    } catch { /* 容错 */ }
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchConfig();
    const interval = setInterval(() => fetchStatus(true), 30000);
    return () => clearInterval(interval);
  }, [fetchStatus, fetchConfig]);

  const handleOpenEdit = (svcName: string) => {
    if (!config) return;
    const form: Record<string, any> = {};
    const svc = EDITABLE_SERVICES[svcName];
    if (!svc) return;
    for (const field of svc.fields) {
      form[field.key] = (config.overrides[field.key] ?? config.effective[field.key]) ?? '';
    }
    setEditForm(form);
    setOpenEdit(svcName);
    setSaveMsg(null);
  };

  const handleCloseEdit = () => { setOpenEdit(null); setEditForm({}); setSaveMsg(null); };

  const handleFieldChange = (key: string, value: string) => {
    setEditForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSaveConfig = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const patch: Record<string, any> = {};
      for (const key of Object.keys(editForm)) {
        const val = editForm[key];
        if (val !== '' && val !== config?.effective[key]) patch[key] = val;
        else if (val === '') patch[key] = null;
      }
      await client.patch('/system/config', patch);
      setSaveMsg({ type: 'success', text: '配置已保存，将在下次检查时生效' });
      await Promise.all([fetchStatus(true), fetchConfig()]);
    } catch (err: any) {
      setSaveMsg({ type: 'error', text: err?.response?.data?.detail || err.message || '保存失败' });
    } finally { setSaving(false); }
  };

  const overallCfg = STATUS_CONFIG[data?.overall || 'error'] || STATUS_CONFIG.error;

  const ServiceCard = ({ svc }: { svc: ServiceStatus }) => {
    const cfg = STATUS_CONFIG[svc.status] || STATUS_CONFIG.error;
    const editable = !!EDITABLE_SERVICES[svc.name];
    return (
      <div style={{
        ...cardStyle,
        borderLeft: `4px solid ${cfg.color}`,
        display: 'flex', flexDirection: 'column', gap: XS,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: XS }}>
          <SvcIcon name={svc.name} />
          <span style={{ fontSize: 16, fontWeight: 600, color: colors['text-primary'] }}>{svc.name}</span>
          <span style={{
            marginLeft: 'auto', padding: '2px 12px', borderRadius: radius.pill,
            fontSize: 12, fontWeight: 500, color: cfg.color, background: cfg.bg,
          }}>
            {cfg.label}
          </span>
        </div>
        <div style={{ display: 'flex', gap: space.md, fontSize: typography['body-sm'].fontSize, color: colors['text-tertiary'] }}>
          {svc.latency_ms !== null && <span>{svc.latency_ms}ms</span>}
          {svc.extras?.model && <span>{svc.extras.model}</span>}
        </div>
        <p style={{ margin: 0, fontSize: typography['body-sm'].fontSize, color: svc.status === 'ok' ? colors['text-secondary'] : cfg.color, lineHeight: 1.5 }}>
          {svc.detail}
        </p>
        {svc.extras?.databases && (
          <div style={{ fontSize: 12, color: colors['text-tertiary'] }}>
            Milvus 数据库: {svc.extras.databases.join(', ')}
          </div>
        )}
        {svc.extras?.model_available !== undefined && !svc.extras.model_available && (
          <div style={{ fontSize: 12, color: '#c77600' }}>
            当前配置的模型 &quot;{svc.extras.model}&quot; 在 API 中不可用
          </div>
        )}
        <div style={{ display: 'flex', gap: XS, marginTop: XS }}>
          {editable && (
            <button onClick={() => handleOpenEdit(svc.name)} style={btnSmallSecondary}>
              <IconEdit size={12} color={colors['text-secondary']} /> 编辑
            </button>
          )}
        </div>
      </div>
    );
  };

  const EditPanel = () => {
    if (!openEdit) return null;
    const svcConfig = EDITABLE_SERVICES[openEdit];
    if (!svcConfig) return null;
    return (
      <>
        <div onClick={handleCloseEdit} style={{
          position: 'fixed', inset: 0, background: colors.overlay, zIndex: 999,
        }} />
        <div style={{
          position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
          background: colors.canvas, borderRadius: radius.lg, padding: space.xl,
          width: 480, maxWidth: '90vw', maxHeight: '80vh', overflowY: 'auto',
          zIndex: 1000, boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.lg }}>
            <h3 style={{ margin: 0, fontSize: 18, color: colors['text-primary'] }}>
              <SvcIcon name={openEdit} size={18} /> {svcConfig.title}
            </h3>
            <button onClick={handleCloseEdit} style={{
              width: 28, height: 28, borderRadius: '50%', border: 'none',
              cursor: 'pointer', background: colors['surface-soft'], display: 'flex',
              alignItems: 'center', justifyContent: 'center', color: colors['text-secondary'],
            }}>
              <IconX size={14} color={colors['text-secondary']} />
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: space.sm }}>
            {svcConfig.fields.map((field) => (
              <div key={field.key}>
                <label style={labelStyle}>{field.label}</label>
                <input
                  type={field.type} placeholder={field.placeholder}
                  value={editForm[field.key] ?? ''}
                  onChange={(e) => handleFieldChange(field.key, e.target.value)}
                  style={inputStyle}
                />
              </div>
            ))}
          </div>

          {saveMsg && (
            <div style={{
              marginTop: space.sm, padding: space.sm, borderRadius: radius.md,
              background: saveMsg.type === 'success' ? colors['block-lime'] : '#ffebee',
              color: saveMsg.type === 'success' ? colors.success : '#c62828',
              fontSize: 13, display: 'flex', alignItems: 'center', gap: XS,
            }}>
              {saveMsg.type === 'success' ? <IconCheck size={14} color={colors.success} /> : <IconX size={14} color="#c62828" />}
              {saveMsg.text}
            </div>
          )}

          <div style={{ display: 'flex', gap: space.sm, marginTop: space.lg, justifyContent: 'flex-end' }}>
            <button onClick={handleCloseEdit} style={btnSmallSecondary}>取消</button>
            <button onClick={handleSaveConfig} disabled={saving} style={{
              ...btnPrimary, opacity: saving ? 0.5 : 1,
            }}>
              {saving ? '保存中...' : '保存配置'}
            </button>
          </div>
        </div>
      </>
    );
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
        <p style={{ color: colors['text-tertiary'], fontSize: 16 }}>正在检查系统状态...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ background: '#ffebee', borderRadius: radius.lg, padding: space.lg, color: '#c62828' }}>
        <h3 style={{ margin: '0 0 XS', fontSize: 16 }}>获取状态失败</h3>
        <p style={{ margin: 0, fontSize: 14 }}>{error}</p>
        <button onClick={() => fetchStatus()} style={{ ...btnPrimary, marginTop: space.sm }}>
          重试
        </button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      {/* 页面标题 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: space.xl }}>
        <div>
          <h1 style={{
            margin: 0, fontSize: typography['display-lg'].fontSize,
            fontWeight: typography['display-lg'].fontWeight,
            letterSpacing: typography['display-lg'].letterSpacing,
            color: colors['text-primary'],
          }}>系统状态</h1>
          <p style={{ margin: '4px 0 0', color: colors['text-secondary'], fontSize: typography['body-sm'].fontSize }}>
            查看各服务连接状态，支持编辑 MySQL 和 LLM 配置
            {data && ` - 上次检查: ${data.timestamp}`}
          </p>
        </div>
        <div style={{ display: 'flex', gap: space.sm, alignItems: 'center' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: XS,
            padding: '6px 16px', borderRadius: radius.pill,
            background: overallCfg.bg, color: overallCfg.color,
            fontSize: 14, fontWeight: 500,
          }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: overallCfg.color, display: 'inline-block' }} />
            整体: {overallCfg.label}
          </div>
          <button onClick={() => fetchStatus(true)} disabled={refreshing} style={{
            ...btnSmallSecondary, opacity: refreshing ? 0.5 : 1,
          }}>
            <IconRefresh size={12} color={colors['text-secondary']} />
            {refreshing ? '刷新中...' : '刷新'}
          </button>
        </div>
      </div>

      {/* 服务状态卡片网格 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: space.sm }}>
        {data?.services.map((svc) => (
          <ServiceCard key={svc.name} svc={svc} />
        ))}
      </div>

      {/* 底部状态概要 */}
      {data && (
        <div style={{
          ...cardStyle, marginTop: space.xl,
          display: 'flex', gap: space.lg, flexWrap: 'wrap',
        }}>
          {['ok', 'degraded', 'warning', 'error'].map((s) => {
            const cfg = STATUS_CONFIG[s];
            const count = data.services.filter((svc) => svc.status === s).length;
            if (count === 0) return null;
            return (
              <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 14 }}>
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: cfg.color, display: 'inline-block' }} />
                <span style={{ color: cfg.color, fontWeight: 500 }}>{cfg.label}</span>
                <span style={{ color: colors['text-tertiary'] }}>{count} 个服务</span>
              </div>
            );
          })}
        </div>
      )}

      <EditPanel />
    </div>
  );
}
