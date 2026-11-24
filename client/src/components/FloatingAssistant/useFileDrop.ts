// 文件拖放 hook — 检测桌面文件拖入悬浮球区域
import { useCallback, useEffect, useRef, useState } from 'react';

export type DropState = 'idle' | 'drop_zone';

const ALLOWED_TYPES = new Set([
  'image/png', 'image/jpeg', 'image/gif', 'image/webp',
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
]);

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

export interface DragFile {
  file: File;
  id: string;
}

interface UseFileDropOptions {
  onFilesDropped: (files: DragFile[]) => void;
  onInvalidFile?: (reason: string) => void;
}

export function useFileDrop({ onFilesDropped, onInvalidFile }: UseFileDropOptions) {
  const [dropState, setDropState] = useState<DropState>('idle');
  const dropCounterRef = useRef(0);

  const handleDragEnter = useCallback((e: DragEvent) => {
    if (!e.dataTransfer?.types.includes('Files')) return;
    dropCounterRef.current++;
    // 根据文档规格：当文件拖入悬浮球区域时，状态切换
  }, []);

  const handleDragOver = useCallback((e: DragEvent) => {
    if (!e.dataTransfer?.types.includes('Files')) return;
    // 检查是否有文件
    setDropState('drop_zone');
  }, []);

  const handleDragLeave = useCallback((e: DragEvent) => {
    dropCounterRef.current--;
    if (dropCounterRef.current <= 0) {
      dropCounterRef.current = 0;
      setDropState('idle');
    }
  }, []);

  const handleDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dropCounterRef.current = 0;
    setDropState('idle');

    const items = e.dataTransfer?.files;
    if (!items || items.length === 0) return;

    const valid: DragFile[] = [];
    for (let i = 0; i < items.length; i++) {
      const f = items[i];
      // 检查类型
      if (!ALLOWED_TYPES.has(f.type)) {
        onInvalidFile?.(`不支持的文件类型：${f.name} (${f.type || '未知格式'})`);
        continue;
      }
      // 检查大小
      if (f.size > MAX_FILE_SIZE) {
        onInvalidFile?.(`文件超过 50MB 限制：${f.name}`);
        continue;
      }
      valid.push({ file: f, id: `${Date.now()}-${i}-${f.name}` });
    }
    if (valid.length > 0) {
      onFilesDropped(valid);
    }
  }, [onFilesDropped, onInvalidFile]);

  // 全局阻止浏览器默认拖放行为
  useEffect(() => {
    const preventDefaults = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };
    const events = ['dragenter', 'dragover', 'dragleave', 'drop'] as const;
    events.forEach(ev => document.addEventListener(ev, preventDefaults, false));
    // 监听 document 级别的拖入，检测是否有文件从桌面拖入
    document.addEventListener('dragenter', handleDragEnter);
    document.addEventListener('dragover', handleDragOver);
    document.addEventListener('dragleave', handleDragLeave);
    document.addEventListener('drop', handleDrop);

    return () => {
      events.forEach(ev => document.removeEventListener(ev, preventDefaults, false));
      document.removeEventListener('dragenter', handleDragEnter);
      document.removeEventListener('dragover', handleDragOver);
      document.removeEventListener('dragleave', handleDragLeave);
      document.removeEventListener('drop', handleDrop);
    };
  }, [handleDragEnter, handleDragOver, handleDragLeave, handleDrop]);

  return { dropState, setDropState };
}
