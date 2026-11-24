// 知识图谱知识点节点组件 — 支持 inline editing 和删除
import React, { useState, useRef, useEffect } from 'react';

export interface KGNodeData {
  id: string;
  title: string;
  description?: string;
  order: number;
  suggested_page_type?: string;
}

interface Props {
  node: KGNodeData;
  onUpdate: (nodeId: string, updates: Partial<KGNodeData>) => void;
  onDelete: (nodeId: string) => void;
}

const PAGE_TYPE_MAP: Record<string, string> = {
  title: '标题', objective: '目标', vocabulary: '词汇',
  dialogue: '对话', grammar: '语法', practice: '练习',
  interactive: '互动', summary: '总结',
};

export default function GraphNode({ node, onUpdate, onDelete }: Props) {
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const handleSave = () => setEditing(false);

  return (
    <div className="kg-node">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#666" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
        <path d="M4 1h5l4 4v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1z" /><path d="M9 1v4h4" /><line x1="5" y1="8" x2="11" y2="8" /><line x1="5" y1="11" x2="9" y2="11" />
      </svg>
      {editing ? (
        <input
          ref={inputRef}
          className="kg-node-title"
          value={node.title}
          onChange={(e) => onUpdate(node.id, { title: e.target.value })}
          onBlur={handleSave}
          onKeyDown={(e) => e.key === 'Enter' && handleSave()}
        />
      ) : (
        <span className="kg-node-title" onClick={() => setEditing(true)} title="点击编辑">
          {node.title}
        </span>
      )}
      {node.suggested_page_type && (
        <span className="kg-node-type">{PAGE_TYPE_MAP[node.suggested_page_type] || node.suggested_page_type}</span>
      )}
      <div className="kg-node-actions">
        <button className="kg-small-btn edit" onClick={() => setEditing(true)} title="编辑">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M11 1l3 3-9 9H2v-3l9-9z" />
          </svg>
        </button>
        <button className="kg-small-btn delete" onClick={() => onDelete(node.id)} title="删除">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 4h12" /><path d="M5 4V2a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /><path d="M3 4v9a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4" />
          </svg>
        </button>
      </div>
    </div>
  );
}
