import { useEffect, useState } from 'react';
import { teacherApi, type ExamSource } from '../../api/teacher';
import { Icon, errorText } from '../mobileControls';
import './examSources.css';

function sizeLabel(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function SourceCard({ source, onClick, onRemove, locked }: {
  source: ExamSource;
  onClick: () => void;
  onRemove?: () => void;
  locked?: boolean;
}) {
  const kind = source.kind === 'image' ? '图片' : source.kind === 'word' ? 'DOCX' : 'PDF';
  return <div className="source-card">
    <button type="button" onClick={onClick} aria-label={`预览 ${source.name}`}>
      <span className="source-icon"><Icon name={source.kind === 'image' ? 'image' : 'files'} size={19} /></span>
      <span><strong>{source.name}</strong><small>{kind} · {sizeLabel(source.size)}</small></span>
      {!onRemove && <Icon name="right" size={17} />}
    </button>
    {onRemove && <button type="button" className="source-remove" aria-label={`移除 ${source.name}`} disabled={locked} onClick={onRemove}>×</button>}
  </div>;
}

export function ExamSourcePreview({ examId, source, close }: {
  examId: string;
  source: ExamSource;
  close: () => void;
}) {
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [preview, setPreview] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (source.kind === 'word') return;
    const controller = new AbortController();
    let url = '';
    setError('');
    setPreview('');
    async function load() {
      try {
        const result = source.kind === 'pdf'
          ? await teacherApi.previewExamSource(examId, source.id, page, controller.signal)
          : { blob: await teacherApi.downloadExamSource(examId, source.id, controller.signal), pages: 1 };
        if (controller.signal.aborted) return;
        url = URL.createObjectURL(result.blob);
        setPreview(url);
        setPages(result.pages);
      } catch (failure) {
        if (!controller.signal.aborted) setError(errorText(failure));
      }
    }
    void load();
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [examId, page, source.id, source.kind]);

  async function download() {
    if (saving) return;
    setSaving(true);
    setError('');
    try {
      const blob = await teacherApi.downloadExamSource(examId, source.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = source.name;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setSaving(false);
    }
  }

  return <section className="exam-source-preview" aria-label="原件预览" role="dialog" aria-modal="true">
    <header className="heading"><button className="round" type="button" onClick={close} aria-label="返回"><Icon name="left" /></button><h1>原件预览</h1>
      <button type="button" className="round" onClick={() => void download()} disabled={saving} aria-label="下载原件"><Icon name="down" /></button>
    </header>
    {source.kind === 'word' ? <SourceCard source={source} onClick={() => void download()} /> : <>
      <strong className="source-preview-name">{source.name}</strong>
      <small className="source-preview-meta">{source.kind === 'pdf' ? 'PDF' : '图片'} · {sizeLabel(source.size)}</small>
    </>}
    {error ? <div className="notice failure" role="alert">{error}</div> : source.kind === 'word' ? <div className="source-preview-empty">
      <span className="source-icon"><Icon name="files" size={25} /></span><strong>当前浏览器无法预览</strong>
    </div> : preview ? <figure className="source-preview-document">
      <img src={preview} alt={source.kind === 'pdf' ? `原件第 ${page} 页` : source.name} />
      {source.kind === 'pdf' && <figcaption>
        <button type="button" className="plain" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="上一页"><Icon name="left" size={17} /></button>
        {page} / {pages}
        <button type="button" className="plain" disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="下一页"><Icon name="right" size={17} /></button>
      </figcaption>}
    </figure> : <p className="notice" aria-live="polite">正在加载原件…</p>}
    <button type="button" className="primary wide source-download" disabled={saving} onClick={() => void download()}>{saving ? '正在下载…' : '下载原件'}</button>
  </section>;
}
