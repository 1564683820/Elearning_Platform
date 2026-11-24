// PPT 创建交互卡片 — AI 回复中嵌入可操作控件
import { useState, useCallback } from 'react';
import client from '../../api/client';

interface PptCardData {
  action_type: 'ppt';
  outline: string[];
  knowledge_points: string[];
  suggested_title: string;
  suggested_grade: string;
  suggested_lesson_type: string;
}

interface PptActionCardProps {
  data: PptCardData;
}

export default function PptActionCard({ data }: PptActionCardProps) {
  const [title, setTitle] = useState(data.suggested_title || '');
  const [knowledgePoints, setKnowledgePoints] = useState<string[]>(data.knowledge_points || []);
  const [grade, setGrade] = useState(data.suggested_grade || '');
  const [lessonType, setLessonType] = useState(data.suggested_lesson_type || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleCreate = useCallback(async () => {
    if (!title.trim()) { setError('请输入PPT名称'); return; }
    setLoading(true);
    setError('');
    try {
      const resp = await client.post('/ppt', {
        title: title.trim(),
        knowledge_points: knowledgePoints,
        grade: grade,
        lesson_type: lessonType,
        outline: data.outline,
      });
      const pptId = resp.data?.data?.id || resp.data?.id;
      if (pptId) {
        // 新标签页跳转到编辑页面
        window.open(`/ppt/edit/${pptId}`, '_blank');
      }
    } catch (err: any) {
      setError(err.message || '创建PPT失败');
    } finally {
      setLoading(false);
    }
  }, [title, knowledgePoints, grade, lessonType, data.outline]);

  const handleRegenerate = useCallback(() => {
    // 重新生成：这个会被父组件通过发送消息处理
  }, []);

  const handleRemoveTag = (tag: string) => {
    setKnowledgePoints(prev => prev.filter(t => t !== tag));
  };

  const handleAddTag = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const val = (e.target as HTMLInputElement).value.trim();
      if (val && !knowledgePoints.includes(val)) {
        setKnowledgePoints(prev => [...prev, val]);
      }
      (e.target as HTMLInputElement).value = '';
    }
  };

  return (
    <div style={{
      background: '#fff',
      border: '1px solid #d4edda',
      borderRadius: 12,
      padding: 14,
      marginBottom: 8,
      boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
    }}>
      {/* 标题 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
      }}>
        <span style={{ fontSize: 18 }}>📊</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#1a2e1a' }}>
          为您生成PPT方案
        </span>
      </div>

      {/* 预览区 */}
      <div style={{
        background: '#f8faf8',
        borderRadius: 8,
        padding: 10,
        marginBottom: 12,
        fontSize: 13,
        color: '#374151',
        lineHeight: 1.6,
        border: '1px solid #e8f0e8',
      }}>
        <div style={{ fontWeight: 500, marginBottom: 6, color: '#2d7d46' }}>
          主题：{title || data.suggested_title}
        </div>
        <div style={{ color: '#6b7280', fontSize: 12, marginBottom: 4 }}>大纲：</div>
        {data.outline.map((item, i) => (
          <div key={i} style={{ paddingLeft: 12, fontSize: 12, color: '#4b5563' }}>
            {i + 1}. {item}
          </div>
        ))}
      </div>

      {/* 参数区 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
        {/* 知识点标签 */}
        <div>
          <label style={labelStyle}>知识点</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
            {knowledgePoints.map((kp) => (
              <span key={kp} style={{
                display: 'inline-flex', alignItems: 'center', gap: 3,
                padding: '2px 8px', borderRadius: 50,
                background: '#e6f7e6', color: '#2d7d46', fontSize: 11,
              }}>
                {kp}
                <span
                  onClick={() => handleRemoveTag(kp)}
                  style={{ cursor: 'pointer', opacity: 0.6, fontSize: 13, lineHeight: 1 }}
                >
                  ×
                </span>
              </span>
            ))}
            <input
              placeholder="+ 添加"
              onKeyDown={handleAddTag}
              style={{
                width: 60, border: 'none', outline: 'none',
                fontSize: 11, color: '#6b7280', background: 'transparent',
              }}
            />
          </div>
        </div>

        {/* 名称 */}
        <div>
          <label style={labelStyle}>名称</label>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            style={inputStyle}
            placeholder="PPT名称"
          />
        </div>

        {/* 年级 */}
        <div>
          <label style={labelStyle}>年级</label>
          <select
            value={grade}
            onChange={e => setGrade(e.target.value)}
            style={inputStyle}
          >
            <option value="">请选择</option>
            <option value="小学">小学</option>
            <option value="初中">初中</option>
            <option value="高中">高中</option>
          </select>
        </div>

        {/* 课型 */}
        <div>
          <label style={labelStyle}>课型</label>
          <select
            value={lessonType}
            onChange={e => setLessonType(e.target.value)}
            style={inputStyle}
          >
            <option value="">请选择</option>
            <option value="新授课">新授课</option>
            <option value="复习课">复习课</option>
            <option value="习题课">习题课</option>
            <option value="实验课">实验课</option>
          </select>
        </div>
      </div>

      {error && (
        <div style={{ fontSize: 12, color: '#dc2626', marginBottom: 8 }}>{error}</div>
      )}

      {/* 按钮 */}
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          onClick={handleRegenerate}
          style={{
            flex: 1, padding: '8px 0', borderRadius: 50,
            border: '1px solid #e2e8f0',
            background: '#fff', color: '#6b7280',
            fontSize: 12, cursor: 'pointer',
          }}
        >
          不满意，重新生成
        </button>
        <button
          onClick={handleCreate}
          disabled={loading}
          style={{
            flex: 1, padding: '8px 0', borderRadius: 50,
            border: 'none',
            background: loading ? '#d4edda' : '#2d7d46',
            color: loading ? '#88c8a0' : '#fff',
            fontSize: 12, fontWeight: 500,
            cursor: loading ? 'default' : 'pointer',
          }}
        >
          {loading ? '创建中...' : '确认创建PPT'}
        </button>
      </div>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  fontWeight: 500,
  color: '#6b7280',
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '6px 10px',
  border: '1px solid #e2e8f0',
  borderRadius: 6,
  fontSize: 12,
  color: '#1a2e1a',
  background: '#fff',
  outline: 'none',
  boxSizing: 'border-box',
  marginTop: 2,
};
