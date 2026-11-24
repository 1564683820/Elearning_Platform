// 知识图谱章节列表组件 — 展示所有章节，支持增删
import React from 'react';
import GraphSection, { KGSectionData } from './GraphSection';
import { KGNodeData } from './GraphNode';
export type { KGSectionData };

interface Props {
  sections: KGSectionData[];
  onUpdateSections: (sections: KGSectionData[]) => void;
  status: string;
}

export function generateSectionId(): string {
  return `sec-${Math.random().toString(36).substring(2, 10)}`;
}

export function generateNodeId(): string {
  return `node-${Math.random().toString(36).substring(2, 10)}`;
}

export { generateNodeId as genNodeId };

export default function GraphSectionList({ sections, onUpdateSections, status }: Props) {
  const readonly = status === 'confirmed';

  // 更新章节
  const handleUpdateSection = (sectionId: string, updates: Partial<KGSectionData>) => {
    if (readonly) return;
    onUpdateSections(sections.map((s) => (s.id === sectionId ? { ...s, ...updates } : s)));
  };

  // 更新知识点
  const handleUpdateNode = (sectionId: string, nodeId: string, updates: Partial<KGNodeData>) => {
    if (readonly) return;
    onUpdateSections(
      sections.map((s) =>
        s.id === sectionId
          ? { ...s, children: s.children.map((n) => (n.id === nodeId ? { ...n, ...updates } : n)) }
          : s
      )
    );
  };

  // 删除章节
  const handleDeleteSection = (sectionId: string) => {
    if (readonly) return;
    if (!window.confirm('确定删除该章节吗？')) return;
    onUpdateSections(sections.filter((s) => s.id !== sectionId));
  };

  // 删除知识点
  const handleDeleteNode = (sectionId: string, nodeId: string) => {
    if (readonly) return;
    if (!window.confirm('确定删除该知识点吗？')) return;
    onUpdateSections(
      sections.map((s) =>
        s.id === sectionId
          ? { ...s, children: s.children.filter((n) => n.id !== nodeId) }
          : s
      )
    );
  };

  // 在章节下添加知识点
  const handleAddNode = (sectionId: string) => {
    if (readonly) return;
    onUpdateSections(
      sections.map((s) => {
        if (s.id !== sectionId) return s;
        const children = [...s.children];
        children.push({
          id: generateNodeId(),
          title: `新知识点 ${children.length + 1}`,
          description: '',
          order: children.length + 1,
          suggested_page_type: '',
        });
        return { ...s, children };
      })
    );
  };

  // 添加章节
  const handleAddSection = () => {
    if (readonly) return;
    const newSection: KGSectionData = {
      id: generateSectionId(),
      title: `新章节 ${sections.length + 1}`,
      order: sections.length + 1,
      children: [],
    };
    onUpdateSections([...sections, newSection]);
  };

  if (!sections || sections.length === 0) {
    return (
      <div>
        <div className="kg-empty">暂无章节内容</div>
        {!readonly && (
          <button className="kg-add-btn kg-add-section" onClick={handleAddSection}>
            + 添加章节
          </button>
        )}
      </div>
    );
  }

  return (
    <div>
      {sections.map((section) => (
        <GraphSection
          key={section.id}
          section={section}
          onUpdateSection={handleUpdateSection}
          onUpdateNode={handleUpdateNode}
          onDeleteSection={handleDeleteSection}
          onDeleteNode={handleDeleteNode}
          onAddNode={handleAddNode}
        />
      ))}
      {!readonly && (
        <button className="kg-add-btn kg-add-section" onClick={handleAddSection}>
          + 添加章节
        </button>
      )}
    </div>
  );
}
