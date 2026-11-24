// 知识图谱编辑器主组件 — 树形展示知识图谱，支持 inline editing 和增删改
import React, { useState } from 'react';
import GraphSectionList, { KGSectionData } from './GraphSectionList';
import './styles.css';

export interface KnowledgeGraphData {
  id?: string;  // Snowflake ID，SSE 返回时已转字符串
  title: string;
  lesson_type: string;
  subject: string;
  grade: string;
  sections: KGSectionData[];
  status: string;
}

interface Props {
  data: KnowledgeGraphData;
  onChange: (data: KnowledgeGraphData) => void;
  onRegenerate?: () => void;
  onConfirm?: () => void;
  generating?: boolean;
}

export default function KnowledgeGraphEditor({
  data, onChange, onRegenerate, onConfirm, generating,
}: Props) {
  const readonly = data.status === 'confirmed';

  const handleUpdateSections = (sections: KGSectionData[]) => {
    onChange({ ...data, sections });
  };

  const totalNodes = data.sections.reduce((sum, s) => sum + (s.children || []).length, 0);

  return (
    <div className="kg-editor">
      <div className="kg-header">
        <div>
          <div className="kg-title">{data.title || '知识图谱'}</div>
          <div style={{ fontSize: 13, color: '#888', marginTop: 4 }}>
            {data.sections.length} 个章节 · {totalNodes} 个知识点
            <span className={`kg-status-badge ${data.status}`} style={{ marginLeft: 8 }}>
              {data.status === 'confirmed' ? '已确认' : '草稿'}
            </span>
          </div>
        </div>
        <div className="kg-actions">
          {!readonly && onRegenerate && (
            <button
              onClick={onRegenerate}
              disabled={generating}
              style={{
                padding: '8px 16px', background: generating ? '#ccc' : '#e6f7e6',
                color: '#2d7d46', border: '1px solid #c8e6c9', borderRadius: 6,
                cursor: generating ? 'not-allowed' : 'pointer', fontSize: 13,
              }}
            >
              {generating ? '分析中...' : 'AI 重新分析'}
            </button>
          )}
          {!readonly && onConfirm && data.sections.length > 0 && (
            <button
              onClick={onConfirm}
              style={{
                padding: '8px 16px', background: '#2d7d46', color: '#fff',
                border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600,
              }}
            >
              确认图谱，生成 PPT
            </button>
          )}
        </div>
      </div>

      <GraphSectionList
        sections={data.sections}
        onUpdateSections={handleUpdateSections}
        status={data.status}
      />
    </div>
  );
}
