// PPT 列表页 — 展示所有备课 PPT，支持筛选、创建、批量导出与删除
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { teacherApi, PPTListItem } from '../../api/teacher';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary, chipStyle,
  shadows, progressBarStyle, progressBarFill,
  IconPlus, IconTrash, IconPpt, IconCheck, IconEdit,
  IconSearch, IconRefresh, IconFile, IconDownload,
} from '../../design-system';

const LESSON_COLORS: Record<string, string> = {
  new_lesson: colors.success,
  review: green.primary,
  exercise: colors.info,
  conversation: green.strong,
};

const LESSON_NAMES: Record<string, string> = {
  new_lesson: '新授课',
  review: '复习课',
  exercise: '练习课',
  conversation: '口语课',
};

const STATUS_NAMES: Record<string, string> = { draft: '草稿', published: '已发布' };
const XS = 8;

export default function PPTList() {
  const navigate = useNavigate();
  const [ppts, setPpts] = useState<PPTListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string | undefined>(undefined);
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [exporting, setExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);

  const loadPpts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await teacherApi.ppt.list({ status: filter, page_size: 50 });
      setPpts(res.items);
    } catch (e: any) {
      alert('加载失败: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { loadPpts(); }, [loadPpts]);

  const handleDelete = async (id: number, title: string) => {
    if (!window.confirm('确定删除「' + title + '」？')) return;
    try {
      await teacherApi.ppt.delete(id);
      loadPpts();
    } catch (e: any) {
      alert('删除失败: ' + e.message);
    }
  };

  const handlePublish = async (id: number) => {
    try {
      await teacherApi.ppt.publish(id);
      loadPpts();
    } catch (e: any) {
      alert('发布失败: ' + e.message);
    }
  };

  const handleBatchExport = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    setExporting(true);
    setExportProgress(0);
    for (let i = 0; i < ids.length; i++) {
      try {
        const result = await teacherApi.ppt.export(ids[i]);
        if (result?.html_content) {
          const blob = new Blob([result.html_content], { type: 'text/html;charset=utf-8' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `${result.title || '课件'}.html`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }
      } catch (_) { /* skip errors */ }
      setExportProgress(Math.round(((i + 1) / ids.length) * 100));
    }
    setExporting(false);
    setSelectedIds(new Set());
  };

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const filtered = search.trim()
    ? ppts.filter(p => p.title.toLowerCase().includes(search.toLowerCase()))
    : ppts;

  return (
    <div style={{ maxWidth: 1024, margin: '0 auto', padding: space.section + 'px 0' }}>
      {/* 顶栏 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        marginBottom: space.xl,
      }}>
        <div>
          <h1 style={{
            margin: 0, fontSize: typography['display-lg'].fontSize,
            fontWeight: typography['display-lg'].fontWeight,
            letterSpacing: typography['display-lg'].letterSpacing,
            color: colors['text-primary'],
          }}>AI 备课 PPT</h1>
          <p style={{
            margin: `${space.xxs}px 0 0`, color: colors['text-secondary'],
            fontSize: typography['body-sm'].fontSize,
          }}>
            选择课型，AI 自动生成互动课件
          </p>
        </div>
        <div style={{ display: 'flex', gap: XS }}>
          <button onClick={() => navigate('/ppt/create')} style={btnPrimary}>
            <IconPlus size={14} color="#fff" /> 创建新 PPT
          </button>
        </div>
      </div>

      {/* 筛选 + 搜索 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: space.lg, flexWrap: 'wrap', gap: XS,
      }}>
        <div style={{ display: 'flex', gap: XS, flexWrap: 'wrap' }}>
          {[undefined, ...Object.keys(LESSON_NAMES)].map((k) => {
            const key = k ?? 'all';
            const active = filter === k;
            return (
              <button key={key} onClick={() => setFilter(k)} style={chipStyle(active)}>
                {k ? LESSON_NAMES[k] : '全部'}
              </button>
            );
          })}
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: XS,
          border: `1px solid ${colors.hairline}`, borderRadius: radius.pill,
          padding: '4px 12px', background: colors.canvas,
        }}>
          <IconSearch size={14} color={colors['text-tertiary']} />
          <input
            placeholder="搜索标题..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              border: 'none', outline: 'none', fontSize: 13, background: 'transparent',
              width: 160, color: colors['text-primary'],
            }}
          />
        </div>
      </div>

      {/* 批量操作栏 */}
      {selectedIds.size > 0 && (
        <div style={{
          marginBottom: space.md, display: 'flex', alignItems: 'center', gap: XS,
          padding: space.sm, background: green.bg3, borderRadius: radius.md,
        }}>
          <span style={{ fontSize: 13, color: colors.success, fontWeight: 500 }}>
            已选 {selectedIds.size} 项
          </span>
          <button
            onClick={handleBatchExport}
            disabled={exporting}
            style={{ ...btnSmall, background: colors.primary, marginLeft: 'auto' }}
          >
            <IconDownload size={12} color="#fff" /> 批量导出 PPTX
          </button>
          <button onClick={() => setSelectedIds(new Set())} style={btnSmallSecondary}>
            取消选择
          </button>
        </div>
      )}

      {/* 导出进度条 */}
      {exporting && (
        <div style={{ marginBottom: space.md }}>
          <div style={progressBarStyle(exportProgress)}>
            <div style={progressBarFill(exportProgress)} />
          </div>
          <p style={{ margin: `${space.xxs}px 0 0`, fontSize: 12, color: colors['text-tertiary'] }}>
            导出中... {exportProgress}%
          </p>
        </div>
      )}

      {/* 列表 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: colors['text-tertiary'] }}>加载中...</div>
      ) : filtered.length === 0 ? (
        <div style={{
          ...cardStyle, textAlign: 'center', padding: 60,
          border: `2px dashed ${colors.hairline}`, display: 'flex', flexDirection: 'column',
          alignItems: 'center', gap: space.md,
        }}>
          <IconPpt size={48} color={colors['text-tertiary']} />
          <p style={{ color: colors['text-tertiary'], margin: 0, fontSize: 15 }}>
            {search ? '未找到匹配的 PPT' : '暂无 PPT，点击右上角创建第一个'}
          </p>
          {!search && (
            <button onClick={() => navigate('/ppt/create')} style={btnPrimary}>
              <IconPlus size={14} color="#fff" /> 创建新 PPT
            </button>
          )}
        </div>
      ) : (
        <div style={{ display: 'grid', gap: space.sm, gridTemplateColumns: 'repeat(auto-fill, minmax(310px, 1fr))' }}>
          {filtered.map((ppt) => {
            const color = LESSON_COLORS[ppt.lesson_type] || colors['text-secondary'];
            const selected = selectedIds.has(ppt.id);
            return (
              <div key={ppt.id} style={{
                ...cardStyle,
                display: 'flex', flexDirection: 'column',
                cursor: 'pointer',
                transition: 'box-shadow 0.2s, transform 0.2s, border-color 0.2s',
                borderColor: selected ? colors.primary : colors.hairline,
                position: 'relative',
              }}
                onClick={() => navigate('/ppt/edit/' + ppt.id)}
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = shadows.elevated;
                  e.currentTarget.style.transform = 'translateY(-2px)';
                }}
                onMouseLeave={(e) => {
                  if (!selected) e.currentTarget.style.borderColor = colors.hairline;
                  e.currentTarget.style.boxShadow = shadows.soft;
                  e.currentTarget.style.transform = 'none';
                }}
              >
                {/* 选择框 */}
                <div
                  style={{
                    position: 'absolute', top: space.sm, right: space.sm, zIndex: 2,
                    width: 22, height: 22, borderRadius: radius.sm,
                    border: `2px solid ${selected ? colors.primary : colors.hairline}`,
                    background: selected ? colors.primary : 'transparent',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    cursor: 'pointer',
                  }}
                  onClick={(e) => { e.stopPropagation(); toggleSelect(ppt.id); }}
                >
                  {selected && <IconCheck size={12} color="#fff" />}
                </div>

                {/* 标签行 */}
                <div style={{ display: 'flex', gap: XS, marginBottom: space.sm, flexWrap: 'wrap', paddingRight: 28 }}>
                  <span style={{
                    background: color + '15',
                    color: color,
                    padding: '2px 12px', borderRadius: radius.pill, fontSize: 12, fontWeight: 500,
                  }}>{ppt.lesson_type_name || LESSON_NAMES[ppt.lesson_type] || ppt.lesson_type}</span>
                  <span style={{
                    background: ppt.status === 'published' ? colors['block-lime'] : colors['surface-soft'],
                    color: ppt.status === 'published' ? colors.success : colors['text-secondary'],
                    padding: '2px 12px', borderRadius: radius.pill, fontSize: 12,
                  }}>{STATUS_NAMES[ppt.status] || ppt.status}</span>
                  {ppt.grade && (
                    <span style={{
                      background: green.bg3, color: green.mid,
                      padding: '2px 12px', borderRadius: radius.pill, fontSize: 12,
                    }}>{ppt.grade}</span>
                  )}
                </div>

                {/* 标题 */}
                <h3 style={{
                  margin: `0 0 ${XS}px`, fontSize: typography['card-title'].fontSize,
                  fontWeight: 600, color: colors['text-primary'], lineHeight: 1.3,
                  paddingRight: 28,
                }}>{ppt.title}</h3>

                {/* 底部信息 */}
                <div style={{
                  marginTop: 'auto', paddingTop: space.sm,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  borderTop: `1px solid ${colors['hairline-soft']}`,
                  fontSize: typography['body-sm'].fontSize,
                  color: colors['text-tertiary'],
                }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <IconPpt size={12} color={colors['text-tertiary']} /> {ppt.slide_count} 页
                  </span>
                  <span>{new Date(ppt.updated_at).toLocaleDateString()}</span>
                </div>

                {/* 操作 */}
                <div style={{ marginTop: space.sm, display: 'flex', gap: XS }} onClick={(e) => e.stopPropagation()}>
                  <button onClick={() => navigate('/ppt/edit/' + ppt.id)} style={{ ...btnSmall, flex: 1 }}>
                    <IconEdit size={12} color="#fff" /> 编辑
                  </button>
                  {ppt.status === 'draft' && (
                    <button onClick={() => handlePublish(ppt.id)} style={{
                      ...btnSmall,
                      background: colors['block-lime'], color: colors.success, border: 'none',
                    }}>
                      <IconCheck size={12} color={colors.success} /> 发布
                    </button>
                  )}
                  <button onClick={() => handleDelete(ppt.id, ppt.title)} style={btnSmallSecondary}>
                    <IconTrash size={12} color={colors.danger} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
