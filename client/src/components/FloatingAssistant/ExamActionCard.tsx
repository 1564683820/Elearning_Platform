// 试卷创建交互卡片 — AI 回复中嵌入可操作控件
import { useState, useCallback } from 'react';
import client from '../../api/client';

interface ExamCardData {
  action_type: 'exam';
  question_types: Record<string, number>;
  knowledge_points: string[];
  suggested_title: string;
  suggested_grade: string;
  suggested_difficulty: string;
}

interface ExamActionCardProps {
  data: ExamCardData;
}

const Q_TYPE_LABELS: Record<string, string> = {
  choice: '选择题',
  fill: '填空题',
  calculate: '计算题',
  answer: '解答题',
  judge: '判断题',
  blank: '填空题',
};

export default function ExamActionCard({ data }: ExamActionCardProps) {
  const [title, setTitle] = useState(data.suggested_title || '');
  const [knowledgePoints, setKnowledgePoints] = useState<string[]>(data.knowledge_points || []);
  const [questionTypes, setQuestionTypes] = useState<Record<string, number>>(data.question_types || {});
  const [grade, setGrade] = useState(data.suggested_grade || '');
  const [difficulty, setDifficulty] = useState(data.suggested_difficulty || '中等');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleQTypeChange = (key: string, val: string) => {
    const num = parseInt(val, 10);
    if (isNaN(num) || num < 0) return;
    setQuestionTypes(prev => ({ ...prev, [key]: num }));
  };

  const handleCreate = useCallback(async () => {
    if (!title.trim()) { setError('请输入试卷名称'); return; }
    setLoading(true);
    setError('');
    try {
      const resp = await client.post('/exams', {
        title: title.trim(),
        knowledge_points: knowledgePoints,
        grade: grade,
        difficulty: difficulty,
        question_types: questionTypes,
      });
      const examId = resp.data?.data?.id || resp.data?.id;
      if (examId) {
        window.open(`/exams/create?from=assistant&id=${examId}`, '_blank');
      }
    } catch (err: any) {
      setError(err.message || '创建试卷失败');
    } finally {
      setLoading(false);
    }
  }, [title, knowledgePoints, grade, difficulty, questionTypes]);

  const handleRegenerate = useCallback(() => {
    // 父组件处理重新生成
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

  // 计算总分
  const totalScore = Object.values(questionTypes).reduce((a, b) => a + b * 5, 0); // 每题 5 分

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
        <span style={{ fontSize: 18 }}>📝</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#1a2e1a' }}>
          为您生成试卷方案
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
        <div style={{ fontWeight: 500, marginBottom: 4, color: '#2d7d46' }}>
          名称：{title || data.suggested_title}
        </div>
        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>题型分布：</div>
        {Object.entries(questionTypes).map(([key, count]) => (
          <div key={key} style={{ paddingLeft: 12, fontSize: 12, color: '#4b5563' }}>
            {Q_TYPE_LABELS[key] || key} ×{count}
          </div>
        ))}
        <div style={{
          marginTop: 6, paddingTop: 6, borderTop: '1px solid #e8f0e8',
          fontSize: 12, color: '#6b7280',
        }}>
          总分：约 {totalScore} 分 &nbsp;|&nbsp; 难度：{difficulty}
        </div>
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
            placeholder="试卷名称"
          />
        </div>

        {/* 题型数量 */}
        <div>
          <label style={labelStyle}>题型</label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', marginTop: 4 }}>
            {Object.entries(questionTypes).map(([key, count]) => (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 12, color: '#4b5563', whiteSpace: 'nowrap', minWidth: 40 }}>
                  {Q_TYPE_LABELS[key] || key}
                </span>
                <input
                  type="number"
                  min="0"
                  max="50"
                  value={count}
                  onChange={e => handleQTypeChange(key, e.target.value)}
                  style={{
                    width: 40, padding: '2px 6px',
                    border: '1px solid #e2e8f0', borderRadius: 4,
                    fontSize: 12, textAlign: 'center',
                    outline: 'none',
                  }}
                />
              </div>
            ))}
          </div>
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

        {/* 难度 */}
        <div>
          <label style={labelStyle}>难度</label>
          <select
            value={difficulty}
            onChange={e => setDifficulty(e.target.value)}
            style={inputStyle}
          >
            <option value="简单">简单</option>
            <option value="中等">中等</option>
            <option value="较难">较难</option>
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
          {loading ? '创建中...' : '确认创建试卷'}
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
