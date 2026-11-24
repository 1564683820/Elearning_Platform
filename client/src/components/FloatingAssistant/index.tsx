// 教学助手小e悬浮窗 — 主容器，管理悬浮球 + 对话弹窗 + 文件上传 + 首次引导提示的生命周期
import { useState, useCallback, useRef } from 'react';
import { useMatch } from 'react-router-dom';
import FloatingBall from './FloatingBall';
import ChatDialog from './ChatDialog';
import UploadProgressDialog from './UploadProgressDialog';
import UploadBadge from './UploadBadge';
import WelcomeTip from './WelcomeTip';
import { useFileDrop, DragFile } from './useFileDrop';
import './floating-assistant.css';

type UploadPhase =
  | { type: 'none' }
  | { type: 'progress'; files: DragFile[]; showing: true }   // 全屏进度弹窗
  | { type: 'progress'; files: DragFile[]; showing: false }; // 后台迷你条态

export default function FloatingAssistant() {
  const onAssistantPage = Boolean(useMatch('/teaching-assistant/*'));
  const [dialogOpen, setDialogOpen] = useState(false);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>({ type: 'none' });
  const [showWelcome, setShowWelcome] = useState(true);
  const toastRef = useRef<HTMLDivElement>(null);

  // ── 文件拖放 ──
  const handleFilesDropped = useCallback((files: DragFile[]) => {
    setUploadPhase({ type: 'progress', files, showing: true });
  }, []);

  const handleInvalidFile = useCallback((reason: string) => {
    showToast(reason);
  }, []);

  const { dropState } = useFileDrop({
    onFilesDropped: handleFilesDropped,
    onInvalidFile: handleInvalidFile,
  });

  // ── 对话展开/收起（点击悬浮球切换） ──
  const handleBallClick = useCallback(() => {
    setDialogOpen(prev => !prev);
  }, []);

  const handleDialogClose = useCallback(() => {
    setDialogOpen(false);
  }, []);

  // ── 关闭引导气泡 ──
  const handleWelcomeDismiss = useCallback(() => {
    setShowWelcome(false);
  }, []);

  // ── 上传完成 ──
  const handleUploadSuccess = useCallback((results: { fileUrl: string; fileName: string }[]) => {
    const succeeded = results.filter(r => r.fileUrl);
    if (succeeded.length > 0) {
      const names = succeeded.map(r => r.fileName).join('、');
      showToast(`文档已上传完成：${names}`);
    }
  }, []);

  // ── 后台进行 ──
  const handleBackground = useCallback(() => {
    setUploadPhase(prev => {
      if (prev.type === 'progress') {
        return { ...prev, showing: false };
      }
      return prev;
    });
  }, []);

  // ── 点击 Badge 重新显示进度 ──
  const handleBadgeClick = useCallback(() => {
    setUploadPhase(prev => {
      if (prev.type === 'progress') {
        return { ...prev, showing: true };
      }
      return prev;
    });
  }, []);

  // ── 关闭上传（完成后或取消） ──
  const handleUploadClose = useCallback(() => {
    setUploadPhase({ type: 'none' });
  }, []);

  // ── Toast ──
  const showToast = (msg: string) => {
    if (!toastRef.current) return;
    const el = document.createElement('div');
    el.textContent = msg;
    el.style.cssText = `
      position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
      background: #1a2e1a; color: #fff; padding: 10px 24px;
      border-radius: 50px; font-size: 13px; z-index: 10001;
      box-shadow: 0 4px 16px rgba(0,0,0,0.2);
      animation: fadeIn 150ms ease-out;
    `;
    document.body.appendChild(el);
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transition = 'opacity 300ms';
      setTimeout(() => el.remove(), 300);
    }, 3000);
  };

  return (
    <>
      {/* 悬浮小球 */}
      {(!onAssistantPage || dropState === 'drop_zone') && (
        <FloatingBall
          onClick={handleBallClick}
          dropState={dropState}
        />
      )}

      {/* 首次进入引导气泡 */}
      {showWelcome && !onAssistantPage && (
        <WelcomeTip
          ballRect={null}
          onDismiss={handleWelcomeDismiss}
        />
      )}

      {/* 对话弹窗 */}
      {dialogOpen && (
        <ChatDialog onClose={handleDialogClose} />
      )}

      {/* 上传进度弹窗（始终挂载以保留内部 state，visible 控制显隐） */}
      {uploadPhase.type === 'progress' && (
        <UploadProgressDialog
          files={uploadPhase.files}
          visible={uploadPhase.showing}
          onClose={handleUploadClose}
          onBackground={handleBackground}
          onUploadSuccess={handleUploadSuccess}
        />
      )}

      {/* 后台上传迷你条 */}
      {uploadPhase.type === 'progress' && !uploadPhase.showing && (
        <UploadBadge
          fileCount={uploadPhase.files.length}
          onClick={handleBadgeClick}
        />
      )}

      <div ref={toastRef} style={{ display: 'none' }} />
    </>
  );
}
