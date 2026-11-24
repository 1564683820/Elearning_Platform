// API Key 管理 — 查看所有用户的 API Key 配置情况
import { useEffect, useState } from 'react';
import client from '../../api/client';
import { colors, radius, typography, space, cardStyle } from '../../design-system';

interface KeyInfo {
  id: number; api_base: string; model_name: string; is_valid: boolean;
}
interface UserKeyInfo {
  user_id: number; username: string; nickname: string;
  keys: Record<string, KeyInfo>;
}

const KEY_TYPES = ['llm', 'multimodal', 'embedding'];
const KEY_LABELS: Record<string, string> = { llm: '大语言模型', multimodal: '多模态', embedding: 'Embedding' };

export default function ApiKeyManagement() {
  const [items, setItems] = useState<UserKeyInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    client.get('/admin/apikeys', { params: { page, page_size: 50 } })
      .then(res => { setItems(res.data.data.items); setTotal(res.data.data.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page]);

  return (
    <div>
      <h1 style={{ ...typography.headline, marginBottom: space.lg }}>API Key 管理</h1>
      <p style={{ fontSize:13, color: colors['text-secondary'], marginBottom: space.lg }}>
        查看所有用户的 API Key 配置情况。共 {total} 条配置记录。
      </p>

      {loading ? (
        <div style={{ textAlign:'center', padding:40, color: colors['text-secondary'] }}>加载中...</div>
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap: space.md }}>
          {items.length === 0 && (
            <div style={{ ...cardStyle, textAlign:'center', padding:40, color: colors['text-secondary'] }}>
              暂无 API Key 配置数据
            </div>
          )}
          {items.map(uk => {
            const hasAnyKey = Object.keys(uk.keys).length > 0;
            return (
              <div key={uk.user_id} style={cardStyle}>
                <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom: hasAnyKey ? space.md : 0 }}>
                  <span style={{ fontWeight:600, fontSize:15 }}>{uk.nickname || uk.username || `#${uk.user_id}`}</span>
                  <span style={{ color: colors['text-secondary'], fontSize:12 }}>@{uk.username}</span>
                  <span style={{ color: colors['text-secondary'], fontSize:12 }}>UID: {uk.user_id}</span>
                </div>
                {hasAnyKey ? (
                  <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(280px,1fr))', gap: space.sm }}>
                    {KEY_TYPES.map(kt => {
                      const k = uk.keys[kt];
                      if (!k) return null;
                      return (
                        <div key={kt} style={{
                          padding:'10px 14px', borderRadius: radius.md,
                          background: k.is_valid ? '#e6f7e6' : '#fef2f2',
                          border: `1px solid ${k.is_valid ? '#88c8a0' : '#fecaca'}`,
                        }}>
                          <div style={{ display:'flex', justifyContent:'space-between', marginBottom:6 }}>
                            <span style={{ fontWeight:600, fontSize:13 }}>{KEY_LABELS[kt]}</span>
                            <span style={{
                              padding:'1px 8px', borderRadius: radius.pill, fontSize:11,
                              background: k.is_valid ? '#2d7d46' : '#dc2626',
                              color: '#fff', fontWeight:500,
                            }}>
                              {k.is_valid ? '有效' : '无效'}
                            </span>
                          </div>
                          <div style={{ fontSize:12, color: colors['text-secondary'], marginBottom:4, wordBreak:'break-all' }}>
                            <span>Base: {k.api_base || 'default'}</span>
                          </div>
                          <div style={{ fontSize:12, color: colors['text-secondary'] }}>
                            <span>Model: {k.model_name || 'default'}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div style={{ fontSize:13, color: colors['text-tertiary'] }}>该用户尚未配置任何 API Key</div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
