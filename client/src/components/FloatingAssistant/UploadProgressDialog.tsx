// 上传进度弹窗 — 显示分块进度、向量化入库等详细步骤，支持后台进行
import { useState, useCallback, useRef, useEffect } from 'react';
import { teacherApi, UploadJobData, JOB_STEP_LABELS } from '../../api/teacher';
import { DragFile } from './useFileDrop';
import { IconX, IconFile, IconCheck } from '../../design-system';

interface UploadProgressDialogProps {
  files: DragFile[];
  onClose: () => void;
  onBackground: () => void;
  onUploadSuccess: (results: { fileUrl: string; fileName: string }[]) => void;
  visible: boolean;
}

interface FileUploadState {
  id: string;
  fileName: string;
  fileSize: number;
  status: 'pending' | 'uploading' | 'processing' | 'done' | 'error';
  percent: number;
  error?: string;
  steps: Record<string, { label: string; percent: number; status: string; message: string }>;
  jobId?: string;
  docId?: number;
  fileUrl?: string;
}

// 步骤顺序
const STEP_KEYS = ['upload', 'cleanup', 'parse', 'chunk', 'embed'];

const POLL_INTERVAL = 1500; // ms

export default function UploadProgressDialog({
  files: initialFiles, onClose, onBackground, onUploadSuccess, visible,
}: UploadProgressDialogProps) {
  const [fileStates, setFileStates] = useState<FileUploadState[]>(() =>
    initialFiles.map(df => ({
      id: df.id,
      fileName: df.file.name,
      fileSize: df.file.size,
      status: 'pending' as const,
      percent: 0,
      steps: {},
    }))
  );

  const [started, setStarted] = useState(false);
  const pollingRef = useRef<Set<string>>(new Set());
  const notifiedRef = useRef(false);

  // ── 进度轮询 ──
  const pollProgress = useCallback(async (jobId: string, fileId: string) => {
    if (pollingRef.current.has(jobId)) return;
    pollingRef.current.add(jobId);

    const poll = async () => {
      try {
        const data: UploadJobData = await teacherApi.documents.getJobProgress(jobId);

        const stepEntries = Object.entries(data.steps || {}).map(([key, step]) => [key, {
          label: JOB_STEP_LABELS[key] || key,
          percent: step.percent,
          status: step.status,
          message: step.message,
        }]);
        const stepsObj = Object.fromEntries(stepEntries);

        setFileStates(prev => prev.map(fs =>
          fs.id === fileId ? {
            ...fs,
            status: data.status === 'done' ? 'done' : data.status === 'error' ? 'error' : 'processing',
            percent: data.percent,
            steps: stepsObj,
            error: data.error || undefined,
            docId: data.doc_id,
          } : fs
        ));

        if (data.status === 'done' || data.status === 'error') {
          pollingRef.current.delete(jobId);
          return; // 停止轮询
        }

        // 继续轮询
        setTimeout(poll, POLL_INTERVAL);
      } catch {
        pollingRef.current.delete(jobId);
        setFileStates(prev => prev.map(fs =>
          fs.id === fileId ? { ...fs, status: 'error', error: '获取进度失败' } : fs
        ));
      }
    };

    setTimeout(poll, POLL_INTERVAL);
  }, []);

  // ── 开始上传（不再自动执行，需用户点击） ──
  const handleStartUpload = useCallback(async () => {
    if (started) return;
    setStarted(true);

    for (const df of initialFiles) {
      setFileStates(prev => prev.map(fs =>
        fs.id === df.id ? { ...fs, status: 'uploading' as const, percent: 0 } : fs
      ));

      try {
        const formData = new FormData();
        formData.append('file', df.file);
        // 设置分类为 "其他" 以便小e使用
        formData.append('doc_category', 'other');

        const resp = await teacherApi.documents.uploadAsync(formData);
        setFileStates(prev => prev.map(fs =>
          fs.id === df.id ? { ...fs, jobId: resp.job_id, docId: resp.doc_id, status: 'processing' as const } : fs
        ));

        pollProgress(resp.job_id, df.id);
      } catch (err: any) {
        setFileStates(prev => prev.map(fs =>
          fs.id === df.id ? { ...fs, status: 'error' as const, error: err.message || '上传失败' } : fs
        ));
      }
    }
  }, [initialFiles, started, pollProgress]);

  const allDone = fileStates.every(fs => fs.status === 'done');
  const totalPercent = fileStates.length > 0
    ? Math.round(fileStates.reduce((s, fs) => s + fs.percent, 0) / fileStates.length)
    : 0;

  // ── 所有轮询完成后才通知父组件 ──
  useEffect(() => {
    if (started && allDone && !notifiedRef.current) {
      notifiedRef.current = true;
      const successResults = fileStates
        .filter(fs => fs.status === 'done')
        .map(fs => ({ fileUrl: `doc_${fs.docId}`, fileName: fs.fileName }));
      onUploadSuccess(successResults);
    }
  }, [started, allDone, fileStates, onUploadSuccess]);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getFileIcon = (name: string) => {
    const ext = name.split('.').pop()?.toLowerCase();
    const iconMap: Record<string, string> = {
      pdf: '📄', doc: '📝', docx: '📝',
      ppt: '📊', pptx: '📊',
      png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', webp: '🖼️',
    };
    return iconMap[ext || ''] || '📁';
  };

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 10000,
        background: 'rgba(0,0,0,0.5)',
        display: visible ? 'flex' : 'none',
        alignItems: 'center',
        justifyContent: 'center',
        animation: 'fadeIn 150ms ease-out',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        width: 480,
        maxWidth: 'calc(100vw - 48px)',
        background: '#fff',
        borderRadius: 16,
        padding: 0,
        boxShadow: '0 16px 48px rgba(0,0,0,0.2)',
        display: 'flex',
        flexDirection: 'column',
        animation: 'scaleIn 200ms cubic-bezier(0.34, 1.56, 0.64, 1)',
      }}>
        {/* 头部 */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 20px', borderBottom: '1px solid #f0f0f0',
        }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: '#1a2e1a' }}>
            上传文件
          </span>
          <div
            onClick={!started || allDone ? onClose : undefined}
            style={{ cursor: !started || allDone ? 'pointer' : 'default', display: 'flex', opacity: !started || allDone ? 1 : 0.4 }}
          >
            <IconX size={18} color="#6b7280" />
          </div>
        </div>

        {/* 内容 */}
        <div style={{ padding: '16px 20px', maxHeight: '60vh', overflow: 'auto' }}>
          {/* 模式标题 */}
          {!started ? (
            <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#2d7d46" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              <span>已选择 <strong style={{ color: '#1a2e1a' }}>{fileStates.length}</strong> 个文件，点击"开始上传"后系统将解析并入库</span>
            </div>
          ) : (
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                <span>总体进度</span>
                <span>{totalPercent}%</span>
              </div>
              <div style={{ height: 6, background: '#f0f0f0', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${totalPercent}%`, background: '#2d7d46', borderRadius: 3, transition: 'width 0.5s ease' }} />
              </div>
            </div>
          )}

          {/* 文件列表 */}
          {fileStates.map(fs => (
            <div key={fs.id} style={{
              marginBottom: 12, padding: '10px 12px',
              background: '#f9fafb', borderRadius: 10,
              border: '1px solid #f0f0f0',
            }}>
              {/* 文件头部 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: fs.status === 'processing' && Object.keys(fs.steps).length > 0 ? 8 : 0 }}>
                <span style={{ fontSize: 20 }}>{getFileIcon(fs.fileName)}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: '#1a2e1a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {fs.fileName}
                  </div>
                  <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 1 }}>
                    {formatSize(fs.fileSize)}
                    {fs.status === 'done' && <span style={{ color: '#2d7d46', marginLeft: 6 }}>✓ 完成</span>}
                    {fs.status === 'error' && <span style={{ color: '#e53935', marginLeft: 6 }}>✗ 失败</span>}
                    {fs.status === 'processing' && <span style={{ color: '#1976d2', marginLeft: 6 }}>{fs.percent}%</span>}
                    {fs.status === 'uploading' && <span style={{ color: '#1976d2', marginLeft: 6 }}>上传中...</span>}
                    {fs.status === 'pending' && <span style={{ color: '#999', marginLeft: 6 }}>等待中</span>}
                  </div>
                </div>
                {fs.status === 'done' && <IconCheck size={18} color="#2d7d46" />}
              </div>

              {/* 错误信息 */}
              {fs.status === 'error' && fs.error && (
                <div style={{ fontSize: 11, color: '#e53935', marginTop: 4, padding: '4px 8px', background: '#fff0f0', borderRadius: 6 }}>
                  {fs.error}
                </div>
              )}

              {/* 步骤进度 */}
              {fs.status === 'processing' && Object.keys(fs.steps).length > 0 && (
                <div style={{ marginTop: 8, borderTop: '1px solid #e8e8e8', paddingTop: 8 }}>
                  {STEP_KEYS.map(key => {
                    const step = fs.steps[key];
                    if (!step) return null;
                    const isActive = step.status === 'running';
                    const isDone = step.status === 'done';
                    const isError = step.status === 'error';
                    return (
                      <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, fontSize: 11 }}>
                        {/* 状态点 */}
                        <div style={{
                          width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                          background: isDone ? '#2d7d46' : isError ? '#e53935' : isActive ? '#1976d2' : '#ddd',
                          boxShadow: isActive ? '0 0 0 3px rgba(25,118,210,0.2)' : 'none',
                          animation: isActive ? 'none' : undefined,
                          transition: 'background 0.3s',
                        }} />
                        <span style={{ color: '#4a5568', flex: 1 }}>{step.label}</span>
                        <span style={{ color: isDone ? '#2d7d46' : isError ? '#e53935' : '#6b7280' }}>
                          {isDone ? '完成' : isError ? '失败' : isActive ? `${step.percent}%` : ''}
                        </span>
                        {/* 活跃时的迷你进度条 */}
                        {isActive && (
                          <div style={{ width: 60, height: 4, background: '#f0f0f0', borderRadius: 2, overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${step.percent}%`, background: '#1976d2', borderRadius: 2, transition: 'width 0.3s' }} />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* 简单进度条（上传中/待处理） */}
              {(fs.status === 'uploading' || fs.status === 'pending') && (
                <div style={{ height: 4, background: '#f0f0f0', borderRadius: 2, overflow: 'hidden', marginTop: 8 }}>
                  <div style={{
                    height: '100%',
                    width: fs.status === 'pending' ? '0%' : '100%',
                    background: '#1976d2',
                    borderRadius: 2,
                    transition: 'width 0.3s',
                    animation: fs.status === 'pending' ? 'none' : undefined,
                    position: 'relative',
                    overflow: 'hidden',
                  }}>
                    {fs.status === 'uploading' && (
                      <div style={{
                        position: 'absolute', inset: 0,
                        background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent)',
                        animation: 'barSlide 1.2s ease-in-out infinite',
                      }} />
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* 底部按钮 */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 10,
          padding: '12px 20px', borderTop: '1px solid #f0f0f0',
        }}>
          {!started ? (
            <>
              <button
                onClick={onClose}
                style={{
                  padding: '8px 20px', borderRadius: 50,
                  border: '1px solid #e2e8f0', background: '#fff',
                  color: '#6b7280', fontSize: 13, cursor: 'pointer',
                }}
              >
                取消
              </button>
              <button
                onClick={handleStartUpload}
                style={{
                  padding: '8px 24px', borderRadius: 50, border: 'none',
                  background: '#2d7d46', color: '#fff', fontSize: 13, fontWeight: 500,
                  cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                开始上传
              </button>
            </>
          ) : allDone ? (
            <button
              onClick={onClose}
              style={{
                padding: '8px 24px', borderRadius: 50, border: 'none',
                background: '#2d7d46', color: '#fff', fontSize: 13, fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              完成
            </button>
          ) : (
            <>
              <button
                onClick={onClose}
                style={{
                  padding: '8px 20px', borderRadius: 50,
                  border: '1px solid #e2e8f0', background: '#fff',
                  color: '#6b7280', fontSize: 13, cursor: 'pointer',
                }}
              >
                取消
              </button>
              <button
                onClick={onBackground}
                style={{
                  padding: '8px 24px', borderRadius: 50, border: 'none',
                  background: '#2d7d46', color: '#fff', fontSize: 13, fontWeight: 500,
                  cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M6 4h12a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2z" />
                  <path d="M9 12h6" />
                </svg>
                后台进行
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
