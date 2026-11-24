/* 题库管理 — 查看各题型题目数量、题目列表、AI 生成更多题目 */
import { useState, useEffect } from 'react';
import { questionBankApi, QuestionBankItem, QuestionBankStats } from '../../api/teacher';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary, chipStyle,
  inputStyle,
  IconPlus, IconTrash, IconRefresh, IconBook, IconGrid,
} from '../../design-system';

// ===== 题型名称映射 =====
const TYPE_NAMES: Record<number, string> = {
  1: '选择填空（词汇）',
  2: '选择翻译',
  3: '听力选择',
  4: '短语语法',
  5: '句子翻译',
  6: '阅读理解',
  7: '听力训练',
  8: '句子翻译（填空）',
  9: '作文写作',
};

const TYPE_COLORS: Record<number, string> = {
  1: green.strong,
  2: green.mid,
  3: '#2563EB',
  4: '#7C3AED',
  5: '#D97706',
  6: '#0891B2',
  7: '#2563EB',
  8: '#D97706',
  9: '#DC2626',
};

const CATEGORY_NAMES: Record<string, string> = {
  vocabulary: '单词词汇',
  grammar: '短语语法',
  reading: '阅读理解',
  translation: '句子翻译',
  writing: '作文写作',
  listening: '听力训练',
};

// 训练分类对应的题型（用于AI生成）
const CATEGORY_QTYPES: Record<string, { qtype: string; label: string }> = {
  vocabulary: { qtype: 'vocabulary', label: '单词词汇' },
  grammar: { qtype: 'grammar', label: '短语语法' },
  reading: { qtype: 'reading', label: '阅读理解' },
  translation: { qtype: 'translation', label: '句子翻译' },
  essay: { qtype: 'essay', label: '作文写作' },
};

// 阶段选项（四阶段体系）
const STAGE_OPTIONS = [
  { value: 0, label: '全部阶段' },
  { value: 1, label: '小学' },
  { value: 2, label: '初中' },
  { value: 3, label: '高中' },
  { value: 4, label: '四六级' },
];

// 格式化时间
function fmtTime(s: string): string {
  if (!s) return '-';
  const d = new Date(s);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// 获取内容摘要
function getContentSummary(item: QuestionBankItem): string {
  const c = item.content || {};
  if (item.type === 6) return c.article_title || c.article_content?.slice(0, 60) || '';
  if (item.type === 8 || item.type === 9) return c.topic || c.stem?.slice(0, 60) || '';
  return c.stem?.slice(0, 80) || c.question?.slice(0, 80) || JSON.stringify(c).slice(0, 80);
}

export default function QuestionBank() {
  const [stats, setStats] = useState<QuestionBankStats | null>(null);
  const [questions, setQuestions] = useState<QuestionBankItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);

  // 筛选
  const [filterType, setFilterType] = useState(0);
  const [filterStage, setFilterStage] = useState(0);
  const [keyword, setKeyword] = useState('');

  // 分页
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const pageSize = 15;

  // 展开的题目
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // AI 生成弹窗
  const [showGenerate, setShowGenerate] = useState(false);
  const [genQtype, setGenQtype] = useState('vocabulary');
  const [genCount, setGenCount] = useState(5);
  const [genStage, setGenStage] = useState(5);
  const [genLoading, setGenLoading] = useState(false);
  const [genResult, setGenResult] = useState<string>('');

  // 加载统计
  const fetchStats = async () => {
    try {
      const s = await questionBankApi.getStats(filterStage || undefined);
      setStats(s);
    } catch { /* ignore */ }
  };

  // 加载列表
  const fetchList = async (p: number) => {
    setLoading(true);
    try {
      const res = await questionBankApi.list({
        page: p,
        page_size: pageSize,
        type_id: filterType || undefined,
        stage: filterStage || undefined,
        keyword: keyword || undefined,
      });
      setQuestions(res.items);
      setTotal(res.total);
      setTotalPages(res.total_pages);
    } catch { /* ignore */ }
    setLoading(false);
  };

  // 初始加载 & 筛选变化
  useEffect(() => {
    fetchStats();
  }, [filterStage]);

  useEffect(() => {
    setPage(1);
  }, [filterType, filterStage, keyword]);

  useEffect(() => {
    fetchList(page);
  }, [page, filterType, filterStage]);

  // 搜索
  const handleSearch = () => {
    setPage(1);
    fetchList(1);
  };

  // 删除题目
  const handleDelete = async (id: number) => {
    if (!confirm('确定要删除这道题目吗？')) return;
    try {
      await questionBankApi.delete(id);
      fetchList(page);
      fetchStats();
    } catch (e: any) {
      alert('删除失败: ' + (e.message || ''));
    }
  };

  // AI 批量生成
  const handleAiGenerate = async () => {
    setGenLoading(true);
    setGenResult('');
    try {
      const res = await questionBankApi.aiGenerate({
        qtype: genQtype,
        stage: genStage,
        count: genCount,
      });
      setGenResult(`生成完成：成功 ${res.generated_count} / 请求 ${res.requested_count} 道`);
      fetchList(1);
      setTimeout(() => fetchStats(), 500);
    } catch (e: any) {
      setGenResult('生成失败: ' + (e.message || ''));
    }
    setGenLoading(false);
  };

  // 统计卡片数据
  const catStats = stats?.by_category || [];

  return (
    <div>
      {/* ===== 标题栏 ===== */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: space.xl }}>
        <div>
          <h1 style={{ ...typography.headline, margin: 0, color: colors['text-primary'] }}>题库管理</h1>
          <p style={{ ...typography['body-sm'], color: colors['text-tertiary'], marginTop: 4, marginBottom: 0 }}>
            共 {stats?.total ?? '-'} 道题目
          </p>
        </div>
        <button
          onClick={() => setShowGenerate(true)}
          style={{ ...btnPrimary, display: 'flex', alignItems: 'center', gap: 6 }}
        >
          <IconPlus size={14} color="#fff" /> AI 生成题目
        </button>
      </div>

      {/* ===== 统计卡片（按训练分类） ===== */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
        gap: space.md,
        marginBottom: space.xl,
      }}>
        {catStats.map((cat) => (
          <div key={cat.category} style={{
            ...cardStyle,
            padding: space.md,
            textAlign: 'center',
            borderTop: `3px solid ${green.strong}`,
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: green.strong }}>
              {cat.count}
            </div>
            <div style={{ fontSize: 13, color: colors['text-tertiary'], marginTop: 4 }}>
              {cat.name}
            </div>
          </div>
        ))}
        {/* 全部 */}
        <div style={{
          ...cardStyle,
          padding: space.md,
          textAlign: 'center',
          borderTop: `3px solid ${green.mid}`,
        }}>
          <div style={{ fontSize: 28, fontWeight: 700, color: green.mid }}>
            {stats?.total ?? 0}
          </div>
          <div style={{ fontSize: 13, color: colors['text-tertiary'], marginTop: 4 }}>
            全部
          </div>
        </div>
      </div>

      {/* ===== 筛选栏 ===== */}
      <div style={{
        display: 'flex', gap: space.sm, alignItems: 'center',
        marginBottom: space.lg, flexWrap: 'wrap',
      }}>
        {/* 题型筛选 */}
        <select
          value={filterType}
          onChange={(e) => setFilterType(Number(e.target.value))}
          style={{ ...inputStyle, width: 160 }}
        >
          <option value={0}>全部题型</option>
          {Object.entries(TYPE_NAMES).map(([id, name]) => (
            <option key={id} value={id}>{name}</option>
          ))}
        </select>

        {/* 阶段筛选 */}
        <select
          value={filterStage}
          onChange={(e) => setFilterStage(Number(e.target.value))}
          style={{ ...inputStyle, width: 120 }}
        >
          {STAGE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        {/* 搜索框 */}
        <div style={{ display: 'flex', gap: 6, flex: 1, maxWidth: 320 }}>
          <input
            type="text"
            placeholder="搜索题目内容..."
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            style={{ ...inputStyle, flex: 1 }}
          />
          <button onClick={handleSearch} style={{ ...btnSmallSecondary, whiteSpace: 'nowrap' }}>
            搜索
          </button>
        </div>
      </div>

      {/* ===== 题目列表 ===== */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: colors['text-tertiary'] }}>加载中...</div>
      ) : questions.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: colors['text-tertiary'] }}>
          <IconBook size={32} color={colors['text-tertiary']} />
          <p style={{ marginTop: 8 }}>暂无题目，点击「AI 生成题目」创建</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: space.sm }}>
          {questions.map((q) => {
            const expanded = expandedId === q.id;
            const summary = getContentSummary(q);
            return (
              <div
                key={q.id}
                style={{
                  ...cardStyle,
                  padding: space.md,
                  cursor: 'pointer',
                  transition: 'box-shadow 0.15s',
                }}
                onClick={() => setExpandedId(expanded ? null : q.id)}
              >
                {/* 列表行 */}
                <div style={{ display: 'flex', alignItems: 'center', gap: space.sm }}>
                  {/* 题型标签 */}
                  <span style={{
                    display: 'inline-block',
                    padding: '2px 10px',
                    borderRadius: radius.pill,
                    background: TYPE_COLORS[q.type] + '18',
                    color: TYPE_COLORS[q.type],
                    fontSize: 11,
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                    minWidth: 70,
                    textAlign: 'center',
                  }}>
                    {TYPE_NAMES[q.type]?.split('（')[0] || `类型${q.type}`}
                  </span>

                  {/* 内容摘要 */}
                  <span style={{
                    flex: 1,
                    fontSize: 14,
                    color: colors['text-primary'],
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {summary || '(空)'}
                  </span>

                  {/* 阶段 */}
                  <span style={{ fontSize: 12, color: colors['text-tertiary'], whiteSpace: 'nowrap' }}>
                    阶段{q.stage}
                  </span>

                  {/* 时间 */}
                  <span style={{ fontSize: 12, color: colors['text-tertiary'], whiteSpace: 'nowrap', minWidth: 130 }}>
                    {fmtTime(q.created_at)}
                  </span>

                  {/* 删除按钮 */}
                  <span
                    onClick={(e) => { e.stopPropagation(); handleDelete(q.id); }}
                    style={{ cursor: 'pointer', padding: '4px', opacity: 0.5 }}
                    title="删除"
                  >
                    <IconTrash size={14} color={colors.danger} />
                  </span>
                </div>

                {/* 展开详情 */}
                {expanded && (
                  <div style={{
                    marginTop: space.sm,
                    paddingTop: space.sm,
                    borderTop: `1px solid ${colors.hairline}`,
                    fontSize: 13,
                    color: colors['text-secondary'],
                    lineHeight: 1.6,
                    maxHeight: 400,
                    overflowY: 'auto',
                  }}>
                    <JsonViewer data={q.content} type={q.type} />
                    <div style={{ marginTop: 8, fontSize: 12, color: colors['text-tertiary'] }}>
                      来源: {q.source || '-'} | 难度: {q.difficulty} | ID: {q.id}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ===== 分页 ===== */}
      {totalPages > 1 && (
        <div style={{
          display: 'flex', justifyContent: 'center', alignItems: 'center',
          gap: space.sm, marginTop: space.xl,
        }}>
          <button
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            style={{ ...btnSmallSecondary, opacity: page <= 1 ? 0.4 : 1 }}
          >
            上一页
          </button>
          <span style={{ fontSize: 13, color: colors['text-tertiary'] }}>
            {page} / {totalPages}（共 {total} 道）
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
            style={{ ...btnSmallSecondary, opacity: page >= totalPages ? 0.4 : 1 }}
          >
            下一页
          </button>
        </div>
      )}

      {/* ===== AI 生成弹窗 ===== */}
      {showGenerate && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000,
        }} onClick={() => { if (!genLoading) setShowGenerate(false); }}>
          <div style={{
            background: '#fff', borderRadius: radius.lg,
            padding: space.xl, width: 420, maxWidth: '90vw',
            boxShadow: '0 8px 40px rgba(0,0,0,0.15)',
          }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 space.md', fontSize: 16, fontWeight: 600 }}>
              AI 生成题目
            </h3>

            <div style={{ marginBottom: space.md }}>
              <label style={{ display: 'block', fontSize: 13, color: colors['text-secondary'], marginBottom: 4 }}>
                题目类型
              </label>
              <select
                value={genQtype}
                onChange={(e) => setGenQtype(e.target.value)}
                style={{ ...inputStyle, width: '100%' }}
              >
                {Object.entries(CATEGORY_QTYPES).map(([key, v]) => (
                  <option key={key} value={key}>{v.label}</option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: space.md }}>
              <label style={{ display: 'block', fontSize: 13, color: colors['text-secondary'], marginBottom: 4 }}>
                学习阶段
              </label>
              <select
                value={genStage}
                onChange={(e) => setGenStage(Number(e.target.value))}
                style={{ ...inputStyle, width: '100%' }}
              >
                {STAGE_OPTIONS.filter((o) => o.value > 0).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: space.xl }}>
              <label style={{ display: 'block', fontSize: 13, color: colors['text-secondary'], marginBottom: 4 }}>
                生成数量
              </label>
              <input
                type="number"
                min={1}
                max={20}
                value={genCount}
                onChange={(e) => setGenCount(Math.min(20, Math.max(1, Number(e.target.value))))}
                style={{ ...inputStyle, width: 100 }}
              />
              <span style={{ fontSize: 12, color: colors['text-tertiary'], marginLeft: 8 }}>
                建议 1~10 道/次
              </span>
            </div>

            {genResult && (
              <div style={{
                padding: '8px 12px', borderRadius: radius.md,
                background: genResult.includes('失败') ? '#FEF2F2' : '#ECFDF5',
                color: genResult.includes('失败') ? colors.danger : green.strong,
                fontSize: 13, marginBottom: space.md,
              }}>
                {genResult}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: space.sm }}>
              <button
                onClick={() => setShowGenerate(false)}
                disabled={genLoading}
                style={{ ...btnSmallSecondary }}
              >
                关闭
              </button>
              <button
                onClick={handleAiGenerate}
                disabled={genLoading}
                style={{
                  ...btnPrimary,
                  opacity: genLoading ? 0.6 : 1,
                  display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                {genLoading ? '生成中...' : <>
                  <IconPlus size={14} color="#fff" /> 开始生成
                </>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ===== 简易 JSON 内容查看器 =====
function JsonViewer({ data, type }: { data: Record<string, any>; type: number }) {
  if (!data || Object.keys(data).length === 0) {
    return <span style={{ color: '#999', fontStyle: 'italic' }}>无内容</span>;
  }

  // 阅读理解特殊渲染
  if (type === 6) {
    return (
      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{data.article_title || '(无标题)'}</div>
        <div style={{ marginBottom: 6, whiteSpace: 'pre-wrap' }}>
          {data.article_content?.slice(0, 300)}
          {(data.article_content?.length || 0) > 300 ? '...' : ''}
        </div>
        {data.content_cn && (
          <details>
            <summary style={{ cursor: 'pointer', color: colors.info, fontSize: 12 }}>查看中文翻译</summary>
            <div style={{ marginTop: 4, whiteSpace: 'pre-wrap', color: colors['text-tertiary'] }}>
              {data.content_cn}
            </div>
          </details>
        )}
        {data.questions && data.questions.length > 0 && (
          <details>
            <summary style={{ cursor: 'pointer', color: colors.info, fontSize: 12, marginTop: 4 }}>
              查看 {data.questions.length} 道选择题
            </summary>
            <div style={{ marginTop: 4 }}>
              {data.questions.map((q: any, i: number) => (
                <div key={i} style={{ fontSize: 12, marginBottom: 4, padding: '4px 8px', background: '#f9f9f9', borderRadius: 4 }}>
                  <div>{i + 1}. {q.stem || q.question || ''}</div>
                  {q.options && <div style={{ color: '#666' }}>选项: {JSON.stringify(q.options)}</div>}
                  <div style={{ color: green.strong }}>答案: {q.correct ?? q.answer ?? '-'}</div>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    );
  }

  // 翻译/作文
  if (type === 8 || type === 9) {
    return (
      <div>
        <div style={{ marginBottom: 4 }}>
          <span style={{ fontWeight: 600 }}>题目：</span>{data.stem || data.topic || '-'}
        </div>
        {data.reference && (
          <details>
            <summary style={{ cursor: 'pointer', color: colors.info, fontSize: 12 }}>查看参考答案</summary>
            <div style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>{data.reference}</div>
          </details>
        )}
        {data.key_vocab && data.key_vocab.length > 0 && (
          <div style={{ marginTop: 4, fontSize: 12, color: colors['text-tertiary'] }}>
            关键词汇: {data.key_vocab.join(', ')}
          </div>
        )}
        {data.hints && (
          <div style={{ marginTop: 4, fontSize: 12, color: colors['text-tertiary'] }}>
            提示: {data.hints}
          </div>
        )}
        {data.key_points && data.key_points.length > 0 && (
          <div style={{ marginTop: 4, fontSize: 12, color: colors['text-tertiary'] }}>
            要点: {data.key_points.join(', ')}
          </div>
        )}
        {data.word_limit && (
          <div style={{ marginTop: 4, fontSize: 12, color: colors['text-tertiary'] }}>
            字数限制: {data.word_limit}
          </div>
        )}
      </div>
    );
  }

  // 默认：JSON 展示
  return (
    <pre style={{
      fontSize: 12, lineHeight: 1.5,
      whiteSpace: 'pre-wrap', wordBreak: 'break-all',
      margin: 0, color: colors['text-secondary'],
    }}>
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
