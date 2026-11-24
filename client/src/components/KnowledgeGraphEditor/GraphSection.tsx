// 知识图谱章节组件 — 包含章节标题和知识点列表
import React, { useState, useRef, useEffect } from 'react';
import GraphNode, { KGNodeData } from './GraphNode';

export interface KGSectionData {
  id: string;
  title: string;
  order: number;
  children: KGNodeData[];
}

interface Props {
  section: KGSectionData;
  onUpdateSection: (sectionId: string, updates: Partial<KGSectionData>) => void;
  onUpdateNode: (sectionId: string, nodeId: string, updates: Partial<KGNodeData>) => void;
  onDeleteSection: (sectionId: string) => void;
  onDeleteNode: (sectionId: string, nodeId: string) => void;
  onAddNode: (sectionId: string) => void;
}

function generateNodeId(): string {
  return `node-${Math.random().toString(36).substring(2, 10)}`;
}

export default function GraphSection({
  section, onUpdateSection, onUpdateNode,
  onDeleteSection, onDeleteNode, onAddNode,
}: Props) {
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
    <div className="kg-section">
      <div className="kg-section-header">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#2d7d46" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
          <path d="M1 4a1 1 0 0 1 1-1h4l2 2h5a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V4z" />
        </svg>
        {editing ? (
          <input
            ref={inputRef}
            className="kg-section-title"
            value={section.title}
            onChange={(e) => onUpdateSection(section.id, { title: e.target.value })}
            onBlur={handleSave}
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
          />
        ) : (
          <span className="kg-section-title" onClick={() => setEditing(true)} title="点击编辑">
            {section.title}
          </span>
        )}
        <div className="kg-section-actions">
          <button className="kg-small-btn edit" onClick={() => setEditing(true)} title="编辑标题">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M11 1l3 3-9 9H2v-3l9-9z" />
            </svg>
          </button>
          <button className="kg-small-btn delete" onClick={() => onDeleteSection(section.id)} title="删除章节">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 4h12" /><path d="M5 4V2a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /><path d="M3 4v9a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4" />
            </svg>
          </button>
        </div>
      </div>
      {(section.children || []).map((node) => (
        <GraphNode
          key={node.id}
          node={node}
          onUpdate={(nodeId, updates) => onUpdateNode(section.id, nodeId, updates)}
          onDelete={(nodeId) => onDeleteNode(section.id, nodeId)}
        />
      ))}
      <button className="kg-add-btn kg-add-node" onClick={() => onAddNode(section.id)}>
        + 添加知识点
      </button>
    </div>
  );
}
