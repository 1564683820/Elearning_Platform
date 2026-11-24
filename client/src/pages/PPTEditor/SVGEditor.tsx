// SVG 在线编辑器组件
// 提供 SVG 幻灯片展示、元素选择、属性编辑、注解管理、撤销/保存等功能

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { teacherApi } from '../../api/teacher';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSecondary, btnSmall, btnSmallSecondary,
} from '../../design-system';

// ---- 类型 ----

interface EditorPage {
  index: number;
  svg: string;
}

interface ElementSelection {
  id: string;
  tag: string;
  attrs: Record<string, string>;
}

interface EditorStateData {
  active: boolean;
  svg_count?: number;
  pages?: Record<string, { edit_count: number; annotations: Record<string, string> }>;
}

// ---- 样式 ----

const EDITABLE_ATTRS = [
  { key: 'fill', label: '填充色', type: 'color' },
  { key: 'stroke', label: '描边色', type: 'color' },
  { key: 'opacity', label: '不透明度', type: 'range', min: 0, max: 1, step: 0.05 },
  { key: 'stroke-width', label: '描边宽', type: 'number', min: 0, max: 20 },
  { key: 'font-size', label: '字号', type: 'number', min: 8, max: 200 },
  { key: 'x', label: 'X 坐标', type: 'number' },
  { key: 'y', label: 'Y 坐标', type: 'number' },
];

// ---- 组件 ----

interface SVGEditorProps {
  pptId: string | number;
  initialSlideCount: number;
  onClose: () => void;
  onSaved?: () => void;
}

export default function SVGEditor({ pptId, initialSlideCount, onClose, onSaved }: SVGEditorProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentPage, setCurrentPage] = useState(0);
  const [svgContent, setSvgContent] = useState('');
  const [editDepth, setEditDepth] = useState(0);
  const [annotations, setAnnotations] = useState<Record<string, string>>({});
  const [existingAnnotations, setExistingAnnotations] = useState<{ element_id: string; tag: string; annotation: string }[]>([]);
  const [selection, setSelection] = useState<ElementSelection | null>(null);
  const [editMessage, setEditMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [editorState, setEditorState] = useState<EditorStateData | null>(null);
  const svgContainerRef = useRef<HTMLDivElement>(null);

  // 初始化编辑器
  const initEditor = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      await teacherApi.ppt.editorStart(pptId);
      await loadPage(0);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '初始化编辑器失败');
    } finally {
      setLoading(false);
    }
  }, [pptId]);

  // 加载指定页
  const loadPage = useCallback(async (pageIndex: number) => {
    try {
      const res = await teacherApi.ppt.getEditorSlide(pptId, pageIndex, true);
      setSvgContent(res.svg);
      setCurrentPage(pageIndex);
      setEditDepth(res.edit_depth);
      setAnnotations(res.annotations || {});
      setExistingAnnotations(res.existing_annotations || []);
      setSelection(null);
      setEditMessage('');
    } catch (e: any) {
      setError(`加载第 ${pageIndex + 1} 页失败: ${e?.response?.data?.detail || e?.message}`);
    }
  }, [pptId]);

  useEffect(() => {
    initEditor();
  }, [initEditor]);

  // SVG 元素点击处理
  const handleSvgClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as SVGElement;
    if (!target || target === svgContainerRef.current?.querySelector('svg')) {
      setSelection(null);
      return;
    }

    const elId = target.getAttribute('id');
    if (!elId) {
      // 尝试找最近的带 id 的父元素
      let parent = target.parentElement;
      while (parent && parent !== svgContainerRef.current) {
        const pid = parent.getAttribute('id');
        if (pid) {
          setSelection({
            id: pid,
            tag: parent.tagName.toLowerCase(),
            attrs: getElementAttrs(parent),
          });
          return;
        }
        parent = parent.parentElement;
      }
      setSelection(null);
      return;
    }

    setSelection({
      id: elId,
      tag: target.tagName.toLowerCase(),
      attrs: getElementAttrs(target),
    });
  }, []);

  // 获取元素所有非空属性
  function getElementAttrs(el: Element): Record<string, string> {
    const attrs: Record<string, string> = {};
    for (let i = 0; i < el.attributes.length; i++) {
      const attr = el.attributes[i];
      if (attr.value && !attr.name.startsWith('data-')) {
        attrs[attr.name] = attr.value;
      }
    }
    return attrs;
  }

  // 提交编辑
  const handleEdit = useCallback(async (attrs: Record<string, string | null>) => {
    if (!selection) return;
    setEditMessage('');
    try {
      const changes = Object.entries(attrs)
        .filter(([, v]) => v !== undefined)
        .map(([key, value]) => ({
          kind: 'attr' as const,
          key,
          old: selection.attrs[key] || '',
          new: value || '',
        }));

      await teacherApi.ppt.submitEdit(pptId, currentPage, {
        element_id: selection.id,
        attrs: attrs as Record<string, string | null>,
        changes,
      });

      // 重新加载页面以反映编辑
      await loadPage(currentPage);
      setEditMessage('编辑已应用 ✓');
    } catch (e: any) {
      setEditMessage(`编辑失败: ${e?.response?.data?.detail || e?.message}`);
    }
  }, [pptId, currentPage, selection, loadPage]);

  // 设置文本
  const handleSetText = useCallback(async (text: string) => {
    if (!selection) return;
    setEditMessage('');
    try {
      await teacherApi.ppt.submitEdit(pptId, currentPage, {
        element_id: selection.id,
        text,
      });
      await loadPage(currentPage);
      setEditMessage('文本已更新 ✓');
    } catch (e: any) {
      setEditMessage(`文本更新失败: ${e?.response?.data?.detail || e?.message}`);
    }
  }, [pptId, currentPage, selection, loadPage]);

  // 撤销
  const handleUndo = useCallback(async () => {
    setEditMessage('');
    try {
      const res = await teacherApi.ppt.undoEdit(pptId, currentPage);
      setEditDepth(res.edit_depth);
      await loadPage(currentPage);
      setEditMessage(res.edit_depth > 0 ? '已撤销 ✓' : '无可撤销的编辑');
    } catch (e: any) {
      setEditMessage(`撤销失败: ${e?.response?.data?.detail || e?.message}`);
    }
  }, [pptId, currentPage, loadPage]);

  // 保存所有
  const handleSaveAll = useCallback(async () => {
    setSaving(true);
    setEditMessage('');
    try {
      const res = await teacherApi.ppt.saveAllEdits(pptId);
      setEditMessage(res.message);
      onSaved?.();
      onClose();
    } catch (e: any) {
      setEditMessage(`保存失败: ${e?.response?.data?.detail || e?.message}`);
    } finally {
      setSaving(false);
    }
  }, [pptId, onClose, onSaved]);

  // 注解操作
  const handleSetAnnotation = useCallback(async (elementId: string, annotation: string) => {
    try {
      const res = await teacherApi.ppt.setAnnotation(pptId, currentPage, { element_id: elementId, annotation });
      setAnnotations(res.annotations || {});
      setEditMessage('注解已保存 ✓');
    } catch (e: any) {
      setEditMessage(`注解失败: ${e?.response?.data?.detail || e?.message}`);
    }
  }, [pptId, currentPage]);

  const handleDeleteAnnotation = useCallback(async (elementId: string) => {
    try {
      const res = await teacherApi.ppt.deleteAnnotation(pptId, currentPage, elementId);
      setAnnotations(res.annotations || {});
      setEditMessage('注解已删除 ✓');
    } catch (e: any) {
      setEditMessage(`删除注解失败: ${e?.response?.data?.detail || e?.message}`);
    }
  }, [pptId, currentPage]);

  // 页面导航
  const goToPage = useCallback((pageIndex: number) => {
    if (pageIndex < 0 || pageIndex >= initialSlideCount) return;
    loadPage(pageIndex);
  }, [loadPage, initialSlideCount]);

  // 调试状态
  const handleCheckState = useCallback(async () => {
    try {
      const state = await teacherApi.ppt.getEditorState(pptId);
      setEditorState(state);
    } catch (e: any) {
      setEditMessage(`获取状态失败: ${e?.message}`);
    }
  }, [pptId]);

  // ---- 渲染 ----

  const overlayStyle: React.CSSProperties = {
    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
    background: colors.overlay, display: 'flex', zIndex: 300,
  };

  const panelStyle: React.CSSProperties = {
    ...cardStyle, margin: space.sm, display: 'flex', flexDirection: 'column', overflow: 'hidden',
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{
        ...cardStyle, margin: space.md, flex: 1, display: 'flex', flexDirection: 'column',
        maxWidth: 'calc(100vw - 32px)', maxHeight: 'calc(100vh - 32px)',
      }}>
        {/* 标题栏 */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: `${space.sm}px ${space.md}px`, borderBottom: `1px solid ${colors.hairline}`,
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: space.sm }}>
            <span style={{ ...typography['card-title'] }}>SVG 在线编辑器</span>
            <span style={{ ...typography.caption, color: colors['text-tertiary'] }}>
              第 {currentPage + 1}/{initialSlideCount} 页
            </span>
          </div>
          <div style={{ display: 'flex', gap: space.xs, alignItems: 'center' }}>
            {/* 导航按钮 */}
            <button onClick={() => goToPage(currentPage - 1)} disabled={currentPage <= 0}
              style={{ ...btnSmallSecondary, opacity: currentPage <= 0 ? 0.4 : 1 }}>
              ◀ 上一页
            </button>
            <button onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= initialSlideCount - 1}
              style={{ ...btnSmallSecondary, opacity: currentPage >= initialSlideCount - 1 ? 0.4 : 1 }}>
              下一页 ▶
            </button>
            <div style={{ width: 1, height: 20, background: colors.hairline, margin: '0 4px' }} />
            <button onClick={handleUndo} title="撤销" style={btnSmallSecondary}>
              ↩ 撤销
            </button>
            <button onClick={handleCheckState} title="调试状态" style={btnSmallSecondary}>
              🔍
            </button>
            <button onClick={handleSaveAll} disabled={saving}
              style={{ ...btnPrimary, opacity: saving ? 0.7 : 1 }}>
              {saving ? '保存中...' : '💾 保存所有'}
            </button>
            <button onClick={onClose} style={btnSmallSecondary}>✕ 关闭</button>
          </div>
        </div>

        {/* 状态消息 */}
        {editMessage && (
          <div style={{
            padding: `6px ${space.md}px`, fontSize: 13, color: editMessage.includes('失败') ? colors.danger : colors.success,
            background: editMessage.includes('失败') ? '#FFF0F0' : '#F0FFF0',
            borderBottom: `1px solid ${colors.hairline}`, flexShrink: 0,
          }}>
            {editMessage}
          </div>
        )}

        {loading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: colors['text-tertiary'] }}>
            加载中...
          </div>
        ) : error ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: colors.danger, flexDirection: 'column', gap: space.sm }}>
            <div>{error}</div>
            <button onClick={initEditor} style={btnSecondary}>重试</button>
            <button onClick={onClose} style={btnSecondary}>关闭</button>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
            {/* SVG 展示区 */}
            <div style={{
              flex: 1, overflow: 'auto', padding: space.md,
              background: '#f5f5f5', display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
            }}>
              <div
                ref={svgContainerRef}
                onClick={handleSvgClick}
                style={{
                  background: '#fff', boxShadow: '0 2px 12px rgba(0,0,0,0.1)',
                  cursor: 'pointer', maxWidth: '100%',
                }}
                dangerouslySetInnerHTML={{ __html: svgContent }}
              />
            </div>

            {/* 右侧属性面板 */}
            <div style={{
              width: 320, flexShrink: 0, borderLeft: `1px solid ${colors.hairline}`,
              display: 'flex', flexDirection: 'column', overflow: 'hidden',
            }}>
              {/* 元素属性 */}
              <div style={{ padding: space.md, borderBottom: `1px solid ${colors.hairline}`, flexShrink: 0 }}>
                <div style={{ ...typography['card-title'], fontSize: 14, marginBottom: space.sm }}>
                  元素属性
                </div>
                {selection ? (
                  <div>
                    <div style={{ fontSize: 12, color: colors['text-tertiary'], marginBottom: 4 }}>
                      #{selection.id} &lt;{selection.tag}&gt;
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                      {EDITABLE_ATTRS.map((attr) => {
                        const value = selection.attrs[attr.key] || '';
                        if (attr.type === 'color') {
                          return (
                            <div key={attr.key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                              <label style={{ width: 80, fontSize: 12, color: colors['text-secondary'], flexShrink: 0 }}>{attr.label}</label>
                              <input type="color" value={value || '#000000'}
                                onChange={(e) => handleEdit({ [attr.key]: e.target.value })}
                                style={{ width: 32, height: 24, padding: 0, border: `1px solid ${colors.hairline}`, borderRadius: 4, cursor: 'pointer' }} />
                              <input type="text" value={value}
                                onChange={(e) => handleEdit({ [attr.key]: e.target.value || null })}
                                style={{
                                  flex: 1, padding: '2px 6px', fontSize: 12, border: `1px solid ${colors.hairline}`,
                                  borderRadius: 4, outline: 'none',
                                }} />
                            </div>
                          );
                        }
                        if (attr.type === 'range') {
                          return (
                            <div key={attr.key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                              <label style={{ width: 80, fontSize: 12, color: colors['text-secondary'], flexShrink: 0 }}>{attr.label}</label>
                              <input type="range" min={attr.min} max={attr.max} step={attr.step}
                                value={parseFloat(value) || 1}
                                onChange={(e) => handleEdit({ [attr.key]: e.target.value })}
                                style={{ flex: 1 }} />
                              <span style={{ fontSize: 11, width: 36, textAlign: 'right', color: colors['text-secondary'] }}>
                                {parseFloat(value).toFixed(2)}
                              </span>
                            </div>
                          );
                        }
                        return (
                          <div key={attr.key} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <label style={{ width: 80, fontSize: 12, color: colors['text-secondary'], flexShrink: 0 }}>{attr.label}</label>
                            <input type="text" value={value}
                              onChange={(e) => handleEdit({ [attr.key]: e.target.value || null })}
                              style={{
                                flex: 1, padding: '2px 6px', fontSize: 12, border: `1px solid ${colors.hairline}`,
                                borderRadius: 4, outline: 'none',
                              }} />
                          </div>
                        );
                      })}
                    </div>

                    {/* 文本编辑 */}
                    {(selection.tag === 'text' || selection.tag === 'tspan') && (
                      <div style={{ marginTop: space.sm }}>
                        <label style={{ fontSize: 12, color: colors['text-secondary'], display: 'block', marginBottom: 4 }}>
                          文本内容
                        </label>
                        <textarea
                          defaultValue={selection.attrs['text-content'] || ''}
                          onBlur={(e) => handleSetText(e.target.value)}
                          rows={3}
                          style={{
                            width: '100%', padding: '4px 8px', fontSize: 12, border: `1px solid ${colors.hairline}`,
                            borderRadius: 4, outline: 'none', resize: 'vertical', fontFamily: 'monospace',
                          }}
                        />
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ fontSize: 12, color: colors['text-tertiary'], fontStyle: 'italic' }}>
                    点击 SVG 中的元素以编辑其属性
                  </div>
                )}
              </div>

              {/* 注解面板 */}
              <div style={{
                flex: 1, overflow: 'auto', padding: space.md, display: 'flex', flexDirection: 'column', gap: space.xs,
              }}>
                <div style={{ ...typography['card-title'], fontSize: 14, marginBottom: 4 }}>
                  元素注解
                </div>

                {/* 选中元素添加注解 */}
                {selection && (
                  <div style={{ display: 'flex', gap: 4, marginBottom: space.sm }}>
                    <input
                      placeholder="输入注解..."
                      defaultValue={annotations[selection.id] || ''}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          handleSetAnnotation(selection.id, (e.target as HTMLInputElement).value);
                        }
                      }}
                      onBlur={(e) => handleSetAnnotation(selection.id, e.target.value)}
                      style={{
                        flex: 1, padding: '4px 8px', fontSize: 12, border: `1px solid ${colors.hairline}`,
                        borderRadius: 4, outline: 'none',
                      }}
                    />
                  </div>
                )}

                {/* 已有注解列表 */}
                {Object.keys(annotations).length > 0 ? (
                  Object.entries(annotations).map(([elId, ann]) => (
                    <div key={elId} style={{
                      padding: `6px ${space.sm}px`, borderRadius: radius.sm,
                      background: colors['surface-soft'], border: `1px solid ${colors.hairline}`,
                      fontSize: 12,
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: 600, color: colors['text-primary'], fontSize: 11 }}>#{elId}</span>
                        <button onClick={() => handleDeleteAnnotation(elId)}
                          style={{
                            background: 'none', border: 'none', cursor: 'pointer',
                            fontSize: 14, color: colors['text-tertiary'], padding: 2, lineHeight: 1,
                          }}
                          title="删除注解">✕</button>
                      </div>
                      <div style={{ color: colors['text-secondary'], marginTop: 2, fontSize: 12, wordBreak: 'break-all' }}>
                        {ann}
                      </div>
                    </div>
                  ))
                ) : (
                  <div style={{ fontSize: 12, color: colors['text-tertiary'], fontStyle: 'italic' }}>
                    暂无注解
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* 调试状态弹窗 */}
        {editorState && (
          <div style={{
            position: 'absolute', right: 340, top: 60, ...cardStyle,
            padding: space.sm, fontSize: 12, maxWidth: 400, maxHeight: 300, overflow: 'auto',
            boxShadow: '0 4px 20px rgba(0,0,0,0.2)', zIndex: 10,
          }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>编辑器状态</div>
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', color: colors['text-secondary'] }}>
              {JSON.stringify(editorState, null, 2)}
            </pre>
            <button onClick={() => setEditorState(null)} style={{ ...btnSmallSecondary, marginTop: 4 }}>关闭</button>
          </div>
        )}
      </div>
    </div>
  );
}
