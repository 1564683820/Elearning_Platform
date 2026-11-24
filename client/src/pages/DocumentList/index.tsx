// 文档管理 — 文档列表、上传、分类/学段筛选、删除、重处理
import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { isAxiosError } from 'axios';
import { loginLink } from '../../api/client';
import { teacherApi, DocumentOut, StepProgress, DOC_CATEGORY_NAMES, STAGE_CATEGORY_NAMES, PARSE_STATUS_NAMES, PARSE_STATUS_COLORS, VECTOR_STATUS_NAMES, VECTOR_STATUS_COLORS } from '../../api/teacher';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary, chipStyle,
  inputStyle, labelStyle,
  IconPlus, IconTrash, IconEdit, IconRefresh, IconFile, IconDocument, IconX, IconCheck, IconExternal,
  progressBarStyle, progressBarFill,
} from '../../design-system';

// 文件类型 → 图标/颜色 (svg-free)
const FILE_TYPE_META: Record<string, { label: string; color: string }> = {
  pdf:   { label: 'PDF', color: green.strong },
  word:  { label: 'DOC', color: green.mid },
  ppt:   { label: 'PPT', color: green.primary },
  txt:   { label: 'TXT', color: '#555' },
  image: { label: 'IMG', color: green.soft },
};

// 格式化文件大小
function fmtSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

const XS = 8;

// 构建带 Token 的文档预览/下载 URL
function getDocPreviewUrl(docId: number): string | null {
  const token = localStorage.getItem('token');
  if (!token) return null;
  // getBaseURL 返回 '/api/v1'，我们直接拼接
  return `/Elearning/api/v1/documents/${docId}/download?token=${encodeURIComponent(token)}`;
}

export default function DocumentList() {
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [listError, setListError] = useState<{ message: string; loginRequired: boolean } | null>(null);

  // 筛选
  const [filterCat, setFilterCat] = useState<string | undefined>(undefined);
  const [filterStage, setFilterStage] = useState<string | undefined>(undefined);

  // 上传对话框
  const [showUpload, setShowUpload] = useState(false);

  // 编辑对话框
  const [editDoc, setEditDoc] = useState<DocumentOut | null>(null);

  // 预览对话框
  const [previewDoc, setPreviewDoc] = useState<DocumentOut | null>(null);

  // 所有可选分类/学段
  const [allCats, setAllCats] = useState<{ value: string; label: string }[]>([]);
  const [allStages, setAllStages] = useState<{ value: string; label: string }[]>([]);

  const fetchDocs = async () => {
    setLoading(true);
    setListError(null);
    try {
      const res = await teacherApi.documents.list({
        page_size: 100,
        doc_category: filterCat,
        stage_category: filterStage,
      });
      setDocs(res.items);
      setTotal(res.total);
    } catch (error) {
      setListError({
        message: error instanceof Error ? error.message : '请求失败',
        loginRequired: isAxiosError(error) && error.response?.status === 401,
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchCategories = async () => {
    try {
      const res = await teacherApi.documents.getCategories();
      setAllCats(res.doc_categories);
      setAllStages(res.stage_categories);
    } catch { /* 静默处理 */ }
  };

  useEffect(() => { fetchCategories(); }, []);
  useEffect(() => { fetchDocs(); }, [filterCat, filterStage]);

  const handleDelete = async (doc: DocumentOut) => {
    if (!window.confirm('确定删除「' + doc.filename + '」？删除后无法恢复。')) return;
    try {
      await teacherApi.documents.delete(doc.id);
      fetchDocs();
    } catch (e: any) {
      alert('删除失败: ' + e.message);
    }
  };

  const handleReprocess = async (doc: DocumentOut) => {
    if (!window.confirm('确定重新处理「' + doc.filename + '」？将重新解析并向量化。')) return;
    try {
      await teacherApi.documents.reprocess(doc.id);
      alert('文档已加入处理队列，稍后刷新查看状态');
      setTimeout(fetchDocs, 2000);
    } catch (e: any) {
      alert('重处理失败: ' + e.message);
    }
  };

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
          }}>文档管理</h1>
          <p style={{ margin: '4px 0 0', color: colors['text-secondary'], fontSize: typography['body-sm'].fontSize }}>
            上传教学文档，AI 自动解析并构建知识库
          </p>
        </div>
        <button onClick={() => setShowUpload(true)} style={btnPrimary}>
          <IconPlus size={14} color="#fff" /> 上传文档
        </button>
      </div>

      {/* 筛选行 */}
      <div style={{ marginBottom: space.lg, display: 'flex', gap: XS, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{
          fontSize: typography.caption.fontSize,
          fontWeight: 500,
          color: colors['text-tertiary'],
          textTransform: 'uppercase',
          letterSpacing: typography.eyebrow.letterSpacing,
        }}>分类</span>
        <button
          onClick={() => setFilterCat(undefined)}
          style={chipStyle(filterCat === undefined)}
        >全部</button>
        {allCats.map((cat) => (
          <button
            key={cat.value}
            onClick={() => setFilterCat(cat.value)}
            style={chipStyle(filterCat === cat.value)}
          >{cat.label}</button>
        ))}

        <span style={{
          fontSize: typography.caption.fontSize,
          fontWeight: 500,
          color: colors['text-tertiary'],
          textTransform: 'uppercase',
          letterSpacing: typography.eyebrow.letterSpacing,
          marginLeft: 12,
        }}>学段</span>
        <button
          onClick={() => setFilterStage(undefined)}
          style={chipStyle(filterStage === undefined)}
        >全部</button>
        {allStages.map((s) => (
          <button
            key={s.value}
            onClick={() => setFilterStage(s.value)}
            style={chipStyle(filterStage === s.value)}
          >{s.label}</button>
        ))}
      </div>

      {/* 统计条 */}
      <div style={{ marginBottom: space.md, fontSize: typography['body-sm'].fontSize, color: colors['text-secondary'] }}>
        共 {total} 个文档
      </div>

      {/* 列表区域 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 80, color: colors['text-tertiary'] }}>加载中...</div>
      ) : listError ? (
        <div role="alert" style={{ textAlign: 'center', padding: 48 }}>
          {listError.loginRequired ? <Link to={loginLink()}>登录后查看文档</Link> : (
            <><p>加载文档列表失败：{listError.message}</p><button style={btnSmall} onClick={fetchDocs}>重试</button></>
          )}
        </div>
      ) : docs.length === 0 ? (
        <div style={{
          ...cardStyle, textAlign: 'center', padding: 80,
          border: `2px dashed ${colors.hairline}`,
        }}>
          <div style={{ marginBottom: space.sm }}>
            <IconDocument size={40} color={colors['text-tertiary']} />
          </div>
          <div style={{ fontSize: 16, marginBottom: XS, color: colors['text-secondary'] }}>暂无文档</div>
          <p style={{ fontSize: 14, color: colors['text-tertiary'], margin: 0 }}>
            点击右上角「上传文档」添加教学资料
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: space.sm, gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))' }}>
          {docs.map((doc) => {
            const ftMeta = FILE_TYPE_META[doc.file_type] || { label: 'FILE', color: colors['text-secondary'] };
            const statusColor = PARSE_STATUS_COLORS[doc.parse_status] || colors['text-tertiary'];
            const statusName = PARSE_STATUS_NAMES[doc.parse_status] || '未知';
            return (
              <div key={doc.id} style={{
                ...cardStyle,
                display: 'flex', flexDirection: 'column',
                transition: 'box-shadow 0.2s',
              }}
                onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.1)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; }}
              >
                {/* 顶行：文件图标 + 标题 */}
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: space.sm, marginBottom: space.sm }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: radius.md,
                    background: ftMeta.color + '15',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: ftMeta.color }}>{ftMeta.label}</span>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: 15, fontWeight: 600, lineHeight: 1.3,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      marginBottom: 4, color: colors['text-primary'],
                    }} title={doc.filename}>{doc.filename}</div>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {/* 解析状态 */}
                      <span style={{
                        background: statusColor + '18', color: statusColor,
                        padding: '1px 10px', borderRadius: radius.pill, fontSize: 11, fontWeight: 500,
                      }} title={doc.parse_status === 2 && doc.vector_status !== 2 ? '已解析但未入库' : ''}>{statusName}</span>
                      {/* 向量化状态 */}
                      {(() => {
                        const vColor = VECTOR_STATUS_COLORS[doc.vector_status] || '#999';
                        const vName = VECTOR_STATUS_NAMES[doc.vector_status] || '未知';
                        return (
                          <span style={{
                            background: vColor + '18', color: vColor,
                            padding: '1px 10px', borderRadius: radius.pill, fontSize: 11, fontWeight: 500,
                          }}>{vName}</span>
                        );
                      })()}
                      {/* 分类 */}
                      {doc.doc_category !== 'other' && (
                        <span style={{
                          background: colors['block-lime'], color: colors.success,
                          padding: '1px 10px', borderRadius: radius.pill, fontSize: 11,
                        }}>{DOC_CATEGORY_NAMES[doc.doc_category] || doc.doc_category}</span>
                      )}
                      {/* 学段 */}
                      {doc.stage_category !== 'other' && (
                        <span style={{
                          background: colors['block-cream'], color: '#92400e',
                          padding: '1px 10px', borderRadius: radius.pill, fontSize: 11,
                        }}>{STAGE_CATEGORY_NAMES[doc.stage_category] || doc.stage_category}</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* 底部：大小 + 日期 + 标签 */}
                <div style={{
                  marginTop: 'auto', paddingTop: space.sm, borderTop: `1px solid ${colors['hairline-soft']}`,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                  <div style={{ display: 'flex', gap: space.sm, fontSize: typography['body-sm'].fontSize, color: colors['text-tertiary'] }}>
                    <span>{fmtSize(doc.file_size)}</span>
                    <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                  </div>
                  {doc.doc_tags && (
                    <span style={{
                      fontSize: 11, color: colors['text-tertiary'],
                      maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      # {doc.doc_tags}
                    </span>
                  )}
                </div>

                {/* 操作按钮 */}
                <div style={{ marginTop: space.sm, display: 'flex', gap: XS }}>
                  <button onClick={() => setPreviewDoc(doc)} style={{ ...btnSmallSecondary }}>
                    <IconExternal size={12} color={green.strong} /> 预览
                  </button>
                  <button onClick={() => setEditDoc(doc)} style={{ ...btnSmallSecondary, flex: 1 }}>
                    <IconEdit size={12} color={colors['text-secondary']} /> 编辑
                  </button>
                  {doc.parse_status !== 2 && (
                    <button onClick={() => handleReprocess(doc)} style={{
                      ...btnSmall,
                      background: colors['block-lilac'], color: green.strong, border: 'none',
                    }}>
                      <IconRefresh size={12} color={green.strong} /> 重处理
                    </button>
                  )}
                  <button onClick={() => handleDelete(doc)} style={btnSmallSecondary}>
                    <IconTrash size={12} color={colors.danger} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 上传对话框 */}
      {showUpload && (
        <UploadDialog
          categories={allCats}
          stages={allStages}
          onClose={() => setShowUpload(false)}
          onRefresh={fetchDocs}
        />
      )}

      {/* 编辑对话框 */}
      {editDoc && (
        <EditDialog
          doc={editDoc}
          categories={allCats}
          stages={allStages}
          onClose={() => setEditDoc(null)}
          onSuccess={() => { setEditDoc(null); fetchDocs(); }}
        />
      )}

      {/* 预览对话框 */}
      {previewDoc && (
        <PreviewDialog
          doc={previewDoc}
          onClose={() => setPreviewDoc(null)}
        />
      )}
    </div>
  );
}

// ========== 进度条面板 ==========
function ProgressPanel({ progress }: { progress: { status: string; percent: number; steps: Record<string, StepProgress> } }) {
  const steps = Object.values(progress.steps);
  const stepColors: Record<string, string> = {
    pending: colors.hairline,
    running: colors.info,
    done: colors.success,
    error: colors.danger,
  };

  return (
    <div>
      {/* 总进度 */}
      <div style={{ marginBottom: space.lg }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: typography['body-sm'].fontSize }}>
          <span style={{ fontWeight: 500, color: colors['text-primary'] }}>总进度</span>
          <span style={{ color: progress.percent === 100 ? colors.success : colors.info, fontWeight: 500 }}>
            {progress.percent}%
          </span>
        </div>
        <div style={{ height: 8, background: colors['surface-soft'], borderRadius: radius.pill, overflow: 'hidden' }}>
          <div style={{
            height: '100%', borderRadius: radius.pill,
            background: progress.status === 'error' ? colors.danger : progress.percent === 100 ? colors.success : 'linear-gradient(90deg, ' + colors.info + ', #60a5fa)',
            width: progress.percent + '%',
            transition: 'width 0.5s ease',
          }} />
        </div>
      </div>

      {/* 分步骤进度 */}
      {steps.map((step, idx) => {
        const color = stepColors[step.status] || colors.hairline;
        const isActive = step.status === 'running';
        return (
          <div key={idx} style={{ marginBottom: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  width: 8, height: 8, borderRadius: '50%', background: color,
                  boxShadow: isActive ? `0 0 6px ${color}` : 'none',
                  transition: 'all 0.3s',
                }} />
                <span style={{ fontSize: typography['body-sm'].fontSize, fontWeight: 500, color: step.status === 'pending' ? colors['text-tertiary'] : colors['text-primary'] }}>
                  {step.label}
                </span>
              </div>
              <span style={{ fontSize: typography['body-sm'].fontSize, color: step.status === 'pending' ? colors['text-tertiary'] : colors['text-secondary'] }}>
                {step.status === 'pending' ? '等待中' :
                 step.status === 'running' ? (step.current !== undefined && step.total ? step.current + '/' + step.total : step.percent + '%') :
                 step.status === 'done' ? '完成' : '失败'}
              </span>
            </div>
            {/* 进度条 */}
            <div style={{ height: 6, background: colors['surface-soft'], borderRadius: radius.pill, overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: radius.pill,
                background: step.status === 'done' ? colors.success :
                           step.status === 'error' ? colors.danger :
                           step.status === 'running' ? colors.info : colors.hairline,
                width: step.status === 'pending' ? 0 : step.percent + '%',
                transition: 'width 0.5s ease',
              }} />
            </div>
            {/* 状态消息 */}
            {step.message && step.status !== 'pending' && (
              <div style={{ fontSize: 11, color: step.status === 'error' ? colors.danger : colors['text-tertiary'], marginTop: 2 }}>
                {step.message}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ========== 上传文档对话框 ==========
function UploadDialog({ categories, stages, onClose, onRefresh }: {
  categories: { value: string; label: string }[];
  stages: { value: string; label: string }[];
  onClose: () => void;
  onRefresh: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [docCat, setDocCat] = useState('other');
  const [stageCat, setStageCat] = useState('other');
  const [tags, setTags] = useState('');
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [processProgress, setProcessProgress] = useState<{
    status: string; percent: number; steps: Record<string, StepProgress>;
  } | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cancelledRef = useRef(false);

  // 轮询异步 Job 进度
  const startPolling = useCallback((jobId: string) => {
    cancelledRef.current = false;
    const poll = async () => {
      if (cancelledRef.current) return;
      try {
        const job = await teacherApi.documents.getJobProgress(jobId);
        if (cancelledRef.current) return;
        setProcessProgress({
          status: job.status,
          percent: job.percent,
          steps: job.steps,
        });
        if (job.status === 'done' || job.status === 'error') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          if (job.status === 'done') {
            setErrorMessage(null);
            // 刷新列表（后台已 commit），但保持弹窗不关闭
            onRefresh();
          } else if (job.status === 'error') {
            setErrorMessage(job.error || '处理失败');
          }
        }
      } catch {
        // 轮询失败不终止，继续重试
      }
    };
    poll();
    pollRef.current = setInterval(poll, 1500);
  }, [onRefresh]);

  // 清理轮询
  useEffect(() => {
    return () => {
      cancelledRef.current = true;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  const handleUpload = async () => {
    if (!file) { alert('请选择文件'); return; }
    setUploading(true);
    setErrorMessage(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('doc_category', docCat);
      fd.append('stage_category', stageCat);
      fd.append('doc_tags', tags);
      const result = await teacherApi.documents.uploadAsync(fd);
      setUploading(false);
      setProcessing(true);
      startPolling(result.job_id);
    } catch (e: any) {
      alert('上传失败: ' + e.message);
      setUploading(false);
    }
  };

  const handleClose = () => {
    cancelledRef.current = true;
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    onClose();
  };

  // ==== 处理中状态：显示进度条 ====
  if (processing) {
    const isComplete = processProgress?.status === 'done';
    const isError = processProgress?.status === 'error';
    return (
      <div style={{
        position: 'fixed', inset: 0, background: colors.overlay, zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }} onClick={handleClose}>
        <div style={{
          background: colors.canvas, borderRadius: radius.lg, padding: space.xl,
          width: 520, maxWidth: '90vw',
          boxShadow: '0 8px 40px rgba(0,0,0,0.15)',
        }} onClick={(e) => e.stopPropagation()}>
          <h3 style={{ margin: '0 0 6px', fontSize: 18, fontWeight: 600, color: colors['text-primary'] }}>
            {isComplete ? '处理完成' : isError ? '处理失败' : '正在处理...'}
          </h3>
          {errorMessage && (
            <p style={{ margin: '4px 0 0', fontSize: 13, color: colors.danger }}>{errorMessage}</p>
          )}
          <p style={{ margin: '0 0 20px', fontSize: 13, color: colors['text-tertiary'], wordBreak: 'break-all' }}>
            {file?.name}
          </p>

          {processProgress ? (
            <ProgressPanel progress={processProgress} />
          ) : (
            <div style={{ textAlign: 'center', padding: 30, color: colors['text-tertiary'] }}>
              等待处理开始...
            </div>
          )}

          <div style={{ display: 'flex', gap: space.sm, justifyContent: 'flex-end', marginTop: space.lg }}>
            {isComplete && (
              <button onClick={handleClose} style={btnPrimary}>完成</button>
            )}
            {isError && (
              <>
                <button onClick={handleClose} style={btnSmallSecondary}>关闭</button>
                <button onClick={handleUpload} style={btnPrimary}>重试</button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: colors.overlay, zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={handleClose}>
      <div style={{
        background: colors.canvas, borderRadius: radius.lg, padding: space.xl,
        width: 480, maxWidth: '90vw',
        boxShadow: '0 8px 40px rgba(0,0,0,0.15)',
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          marginBottom: space.lg,
        }}>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: colors['text-primary'] }}>
            上传文档
          </h3>
          <button onClick={handleClose} style={{
            border: 'none', background: 'none', cursor: 'pointer',
            color: colors['text-tertiary'], fontSize: 18, lineHeight: 1,
          }}>
            <IconX size={18} color={colors['text-tertiary']} />
          </button>
        </div>

        {/* 拖拽上传区域 */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files[0];
            if (f) setFile(f);
          }}
          onClick={() => fileRef.current?.click()}
          style={{
            border: `2px dashed ${dragging ? colors.primary : colors.hairline}`,
            borderRadius: radius.lg, padding: 40, textAlign: 'center', cursor: 'pointer',
            background: dragging ? colors['surface-soft'] : colors.canvas,
            transition: 'all 0.15s', marginBottom: space.md,
          }}
        >
          <IconFile size={32} color={colors['text-tertiary']} />
          <p style={{ margin: '8px 0 0', fontSize: 14, color: colors['text-secondary'] }}>
            {file ? file.name : '点击或拖拽文件到此处上传'}
          </p>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: colors['text-tertiary'] }}>
            支持 PDF / Word / PPT / TXT / 图片
          </p>
          <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.png,.jpg,.jpeg,.gif,.webp"
            onChange={(e) => { if (e.target.files?.[0]) setFile(e.target.files[0]); }}
            style={{ display: 'none' }} />
        </div>

        <div style={{ marginBottom: space.sm }}>
          <label style={labelStyle}>文档分类</label>
          <select value={docCat} onChange={(e) => setDocCat(e.target.value)} style={inputStyle}>
            {categories.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: space.sm }}>
          <label style={labelStyle}>学段</label>
          <select value={stageCat} onChange={(e) => setStageCat(e.target.value)} style={inputStyle}>
            {stages.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: space.lg }}>
          <label style={labelStyle}>标签（选填）</label>
          <input value={tags} onChange={(e) => setTags(e.target.value)}
            style={inputStyle} placeholder="如：Unit3, 语法" />
        </div>

        <div style={{ display: 'flex', gap: space.sm, justifyContent: 'flex-end' }}>
          <button onClick={handleClose} style={btnSmallSecondary}>取消</button>
          <button onClick={handleUpload} disabled={uploading || !file} style={{
            ...btnPrimary,
            opacity: uploading || !file ? 0.5 : 1,
          }}>
            {uploading ? '上传中...' : '开始上传'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ========== 编辑对话框 ==========
function EditDialog({ doc, categories, stages, onClose, onSuccess }: {
  doc: DocumentOut;
  categories: { value: string; label: string }[];
  stages: { value: string; label: string }[];
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [docCat, setDocCat] = useState(doc.doc_category);
  const [stageCat, setStageCat] = useState(doc.stage_category);
  const [tags, setTags] = useState(doc.doc_tags || '');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await teacherApi.documents.update(doc.id, {
        doc_category: docCat,
        stage_category: stageCat,
        doc_tags: tags,
      });
      onSuccess();
    } catch (e: any) {
      alert('保存失败: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: colors.overlay, zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: colors.canvas, borderRadius: radius.lg, padding: space.xl,
        width: 440, maxWidth: '90vw',
        boxShadow: '0 8px 40px rgba(0,0,0,0.15)',
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          marginBottom: space.lg,
        }}>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: colors['text-primary'] }}>
            编辑文档
          </h3>
          <button onClick={onClose} style={{ border: 'none', background: 'none', cursor: 'pointer' }}>
            <IconX size={18} color={colors['text-tertiary']} />
          </button>
        </div>

        <p style={{ fontSize: 13, color: colors['text-secondary'], margin: `0 0 ${space.md}px`, wordBreak: 'break-all' }}>
          {doc.filename}
        </p>

        <div style={{ marginBottom: space.sm }}>
          <label style={labelStyle}>文档分类</label>
          <select value={docCat} onChange={(e) => setDocCat(e.target.value)} style={inputStyle}>
            {categories.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: space.sm }}>
          <label style={labelStyle}>学段</label>
          <select value={stageCat} onChange={(e) => setStageCat(e.target.value)} style={inputStyle}>
            {stages.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: space.lg }}>
          <label style={labelStyle}>标签</label>
          <input value={tags} onChange={(e) => setTags(e.target.value)}
            style={inputStyle} placeholder="逗号分隔" />
        </div>

        <div style={{ display: 'flex', gap: space.sm, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={btnSmallSecondary}>取消</button>
          <button onClick={handleSave} disabled={saving} style={{
            ...btnPrimary,
            opacity: saving ? 0.5 : 1,
          }}>
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ========== 预览对话框 ==========
function PreviewDialog({ doc, onClose }: { doc: DocumentOut; onClose: () => void }) {
  const downloadUrl = getDocPreviewUrl(doc.id);
  const [textContent, setTextContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 获取提取的文本内容
  useEffect(() => {
    let cancelled = false;
    const fetchText = async () => {
      setLoading(true);
      try {
        const result = await teacherApi.documents.getTextContent(doc.id);
        if (cancelled) return;
        if (result && result.text) {
          setTextContent(result.text);
        } else {
          setError(result?.hint || '该文档暂无提取的文本内容');
        }
      } catch {
        if (!cancelled) setError('获取文本内容失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchText();
    return () => { cancelled = true; };
  }, [doc.id]);

  // 文件类型中文标签
  const typeLabel = {
    pdf: 'PDF', word: 'Word', ppt: 'PPT', txt: 'TXT', image: '图片',
  }[doc.file_type] || 'FILE';

  // 点击外部关闭
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={handleOverlayClick}>
      <div style={{
        background: colors.canvas, borderRadius: radius.lg,
        width: '90vw', height: '90vh', maxWidth: 1200,
        display: 'flex', flexDirection: 'column',
        boxShadow: '0 8px 40px rgba(0,0,0,0.25)',
        overflow: 'hidden',
      }}>
        {/* 顶部栏 */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: `${space.md}px ${space.lg}px`,
          borderBottom: `1px solid ${colors.hairline}`,
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: space.sm, minWidth: 0 }}>
            <div style={{
              width: 28, height: 28, borderRadius: radius.md,
              background: (FILE_TYPE_META[doc.file_type]?.color || green.primary) + '15',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              <span style={{
                fontSize: 10, fontWeight: 700,
                color: FILE_TYPE_META[doc.file_type]?.color || green.primary,
              }}>
                {typeLabel}
              </span>
            </div>
            <div style={{
              fontSize: typography.body.fontSize, fontWeight: 600,
              color: colors['text-primary'],
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }} title={doc.filename}>
              {doc.filename}
            </div>
            {textContent && (
              <span style={{
                fontSize: 12, color: colors['text-tertiary'],
                background: colors['surface-soft'], padding: '2px 8px', borderRadius: radius.pill,
              }}>
                {textContent.length.toLocaleString()} 字符
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: space.sm }}>
            {downloadUrl && (
              <a href={downloadUrl} target="_blank" rel="noopener noreferrer"
                style={{ ...btnSmall, textDecoration: 'none' }}>
                <IconExternal size={12} color="#fff" /> 原始文件
              </a>
            )}
            <button onClick={onClose} style={{
              border: 'none', background: colors['surface-soft'],
              cursor: 'pointer', width: 32, height: 32, borderRadius: radius.md,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <IconX size={16} color={colors['text-secondary']} />
            </button>
          </div>
        </div>

        {/* 内容区 */}
        <div style={{
          flex: 1, position: 'relative', overflow: 'auto',
          background: '#fafafa',
        }}>
          {loading ? (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              height: '100%', color: colors['text-tertiary'], fontSize: 14,
            }}>
              正在加载文本内容...
            </div>
          ) : error && !textContent ? (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              height: '100%', gap: space.md, padding: space.xl,
            }}>
              <div style={{
                width: 64, height: 64, borderRadius: radius.full,
                background: colors['surface-soft'],
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <IconFile size={32} color={colors['text-tertiary']} />
              </div>
              <p style={{ fontSize: 15, color: colors['text-secondary'], margin: 0 }}>
                {error}
              </p>
              {downloadUrl && (
                <>
                  <p style={{ fontSize: 13, color: colors['text-tertiary'], margin: 0, textAlign: 'center' }}>
                    可以下载原始文件查看完整内容
                  </p>
                  <a href={downloadUrl} target="_blank" rel="noopener noreferrer" style={btnPrimary}>
                    <IconExternal size={14} color="#fff" /> 下载原始文件
                  </a>
                </>
              )}
            </div>
          ) : textContent ? (
            <div style={{
              padding: `${space.lg}px ${space.xl}px`,
              fontFamily: '"PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", sans-serif',
              fontSize: 15,
              lineHeight: 1.8,
              color: colors['text-primary'],
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>
              {textContent}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
