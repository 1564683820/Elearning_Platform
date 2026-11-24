// 文件上传弹窗 — 支持文件预览、移除、追加、上传
import { useState, useCallback } from 'react';
import { teachingAssistantApi } from '../../api/teachingAssistant';
import { DragFile } from './useFileDrop';
import { IconX, IconFile, IconCheck } from '../../design-system';

interface UploadModalProps {
  files: DragFile[];
  onClose: () => void;
  onUploadSuccess: (results: { fileUrl: string; fileName: string }[]) => void;
}

export default function UploadModal({ files: initialFiles, onClose, onUploadSuccess }: UploadModalProps) {
  const [fileList, setFileList] = useState<DragFile[]>(initialFiles);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const handleRemoveFile = useCallback((id: string) => {
    setFileList(prev => prev.filter(f => f.id !== id));
  }, []);

  const handleUpload = useCallback(async () => {
    if (fileList.length === 0 || uploading) return;
    setUploading(true);
    const results: { fileUrl: string; fileName: string }[] = [];
    let completed = 0;

    for (const df of fileList) {
      try {
        const result = await teachingAssistantApi.uploadFile(df.file);
        results.push({ fileUrl: result.file_url, fileName: df.file.name });
      } catch (err: any) {
        results.push({ fileUrl: '', fileName: `${df.file.name} (上传失败：${err.message || '未知错误'})` });
      }
      completed++;
      setUploadProgress(Math.round((completed / fileList.length) * 100));
    }

    setUploading(false);
    setUploadProgress(0);
    onUploadSuccess(results.filter(r => r.fileUrl));
    onClose();
  }, [fileList, uploading, onUploadSuccess, onClose]);

  // 遮罩点击关闭
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget && !uploading) onClose();
  };

  // Esc 关闭
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && !uploading) onClose();
  };

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
      onClick={handleOverlayClick}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
      style={{
        position: 'fixed', inset: 0, zIndex: 10000,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        animation: 'fadeIn 150ms ease-out',
      }}
    >
      <div style={{
        width: 420,
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
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px',
          borderBottom: '1px solid #f0f0f0',
        }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: '#1a2e1a' }}>
            上传文件
          </span>
          <div
            onClick={onClose}
            style={{ cursor: uploading ? 'default' : 'pointer', display: 'flex', opacity: uploading ? 0.4 : 1 }}
          >
            <IconX size={18} color="#6b7280" />
          </div>
        </div>

        {/* 内容 */}
        <div style={{ padding: '16px 20px' }}>
          <p style={{
            margin: '0 0 12px', fontSize: 13, color: '#6b7280',
          }}>
            支持图片、PDF、Word、PPT 格式，单个文件不超过 50MB
          </p>

          {/* 文件列表 */}
          {fileList.length === 0 ? (
            <div style={{
              padding: '32px 16px',
              textAlign: 'center',
              color: '#9ca3af',
              fontSize: 13,
            }}>
              没有要上传的文件
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
              {fileList.map(df => (
                <div
                  key={df.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '8px 12px',
                    background: '#f9fafb',
                    borderRadius: 8,
                    border: '1px solid #f0f0f0',
                  }}
                >
                  <span style={{ fontSize: 20 }}>{getFileIcon(df.file.name)}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: 13, fontWeight: 500, color: '#1a2e1a',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {df.file.name}
                    </div>
                    <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 1 }}>
                      {formatSize(df.file.size)}
                    </div>
                  </div>
                  {!uploading && (
                    <div
                      onClick={() => handleRemoveFile(df.id)}
                      style={{ cursor: 'pointer', display: 'flex', flexShrink: 0 }}
                    >
                      <IconX size={14} color="#9ca3af" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* 进度条 */}
          {uploading && (
            <div style={{
              height: 6,
              background: '#f0f0f0',
              borderRadius: 3,
              overflow: 'hidden',
              marginBottom: 12,
            }}>
              <div style={{
                height: '100%',
                width: `${uploadProgress}%`,
                background: '#2d7d46',
                borderRadius: 3,
                transition: 'width 0.3s ease',
              }} />
            </div>
          )}
        </div>

        {/* 底部按钮 */}
        <div style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 10,
          padding: '12px 20px',
          borderTop: '1px solid #f0f0f0',
        }}>
          <button
            onClick={onClose}
            disabled={uploading}
            style={{
              padding: '8px 20px',
              borderRadius: 50,
              border: '1px solid #e2e8f0',
              background: '#fff',
              color: '#6b7280',
              fontSize: 13,
              cursor: uploading ? 'default' : 'pointer',
              opacity: uploading ? 0.5 : 1,
            }}
          >
            取消
          </button>
          <button
            onClick={handleUpload}
            disabled={fileList.length === 0 || uploading}
            style={{
              padding: '8px 24px',
              borderRadius: 50,
              border: 'none',
              background: fileList.length === 0 || uploading ? '#d4edda' : '#2d7d46',
              color: fileList.length === 0 || uploading ? '#88c8a0' : '#fff',
              fontSize: 13,
              fontWeight: 500,
              cursor: fileList.length === 0 || uploading ? 'default' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            {uploading ? `上传中 ${uploadProgress}%` : `上传 (${fileList.length})`}
          </button>
        </div>
      </div>
    </div>
  );
}
