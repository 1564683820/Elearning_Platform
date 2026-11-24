// 权限管理页 — 助教授权/撤销、多教师管理、角色权限可视化
import { useState, useEffect } from 'react';
import { teacherApi, ClassData } from '../../api/teacher';
import { collaborationApi, AssistantData } from '../../api/collaboration';
import {
  colors, green, radius, typography, space, cardStyle,
  btnPrimary, btnSmall, btnSmallSecondary, chipStyle,
  inputStyle, labelStyle,
  IconPlus, IconX, IconUsers, IconEdit, IconShield,
} from '../../design-system';

const XS = 8;

export default function PermissionManage() {
  const [classes, setClasses] = useState<ClassData[]>([]);
  const [selectedClass, setSelectedClass] = useState<string | null>(null);
  const [assistants, setAssistants] = useState<AssistantData[]>([]);
  const [loading, setLoading] = useState(true);

  const [addStudentId, setAddStudentId] = useState('');
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    teacherApi.listClasses()
      .then(setClasses)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedClass) {
      collaborationApi.listAssistants(selectedClass).then(setAssistants);
    }
  }, [selectedClass]);

  const handleAddAssistant = async () => {
    if (!selectedClass || !addStudentId) return;
    setAdding(true);
    try {
      await collaborationApi.addAssistant({
        class_id: selectedClass,
        student_id: addStudentId,
      });
      setAddStudentId('');
      const list = await collaborationApi.listAssistants(selectedClass);
      setAssistants(list);
    } catch (e: any) {
      alert(e.message || '添加失败');
    }
    setAdding(false);
  };

  const handleRemoveAssistant = async (assistantId: string | number) => {
    if (!selectedClass) return;
    if (!confirm('确定移除该助教？')) return;
    try {
      await collaborationApi.removeAssistant(selectedClass, assistantId);
      setAssistants(a => a.filter(x => x.teacher_id !== assistantId));
    } catch (e: any) {
      alert(e.message || '移除失败');
    }
  };

  const selectedClassData = classes.find(c => String(c.id) === selectedClass);

  if (loading) return <div style={{ padding: 60, textAlign: 'center', color: colors['text-tertiary'] }}>加载中...</div>;

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      {/* 顶栏 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: space.sm,
        marginBottom: space.xl,
      }}>
        <IconShield size={28} color={colors['text-primary']} />
        <h1 style={{
          margin: 0, fontSize: typography['display-lg'].fontSize,
          fontWeight: typography['display-lg'].fontWeight,
          letterSpacing: typography['display-lg'].letterSpacing,
          color: colors['text-primary'],
        }}>权限管理</h1>
      </div>

      {/* 班级选择 */}
      <div style={{
        ...cardStyle, marginBottom: space.xl,
        background: colors['block-lilac'],
      }}>
        <span style={{
          ...labelStyle, marginBottom: space.sm, display: 'block',
        }}>选择班级</span>
        <select
          value={selectedClass || ''}
          onChange={e => setSelectedClass(e.target.value || null)}
          style={{ ...inputStyle, maxWidth: 320 }}
        >
          <option value="">请选择班级</option>
          {classes.map(c => (
            <option key={c.id} value={c.id}>{c.name} ({c.student_count}人)</option>
          ))}
        </select>
        {selectedClassData && (
          <p style={{ margin: 'xs 0 0', fontSize: typography['body-sm'].fontSize, color: colors['text-secondary'] }}>
            {selectedClassData.name} - {selectedClassData.student_count} 名学生
            {selectedClassData.description ? ' | ' + selectedClassData.description : ''}
          </p>
        )}
      </div>

      {selectedClass && (
        <>
          {/* 添加助教 */}
          <div style={{
            ...cardStyle, marginBottom: space.xl,
            background: colors['block-lime'],
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: XS, marginBottom: space.md }}>
              <IconPlus size={16} color={colors['text-primary']} />
              <h3 style={{
                margin: 0, fontSize: typography.headline.fontSize,
                fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
              }}>添加助教 / 课代表</h3>
            </div>
            <div style={{ display: 'flex', gap: space.sm, alignItems: 'flex-end' }}>
              <div style={{ flex: 1, maxWidth: 300 }}>
                <span style={labelStyle}>学生用户 ID</span>
                <input
                  type="number"
                  value={addStudentId}
                  onChange={e => setAddStudentId(e.target.value)}
                  style={inputStyle}
                  placeholder="输入学生的用户 ID"
                />
              </div>
              <button onClick={handleAddAssistant} disabled={adding || !addStudentId} style={{
                ...btnPrimary,
                opacity: adding || !addStudentId ? 0.5 : 1,
              }}>
                {adding ? '添加中...' : '添加助教'}
              </button>
            </div>
          </div>

          {/* 助教列表 */}
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: XS, marginBottom: space.md }}>
              <IconUsers size={18} color={colors['text-primary']} />
              <h3 style={{
                margin: 0, fontSize: typography.headline.fontSize,
                fontWeight: typography.headline.fontWeight, color: colors['text-primary'],
              }}>助教 / 课代表列表</h3>
            </div>
            {assistants.length === 0 ? (
              <p style={{ color: colors['text-tertiary'], textAlign: 'center', padding: 40, margin: 0 }}>
                暂无助教
              </p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: typography['body-sm'].fontSize }}>
                  <thead>
                    <tr style={{
                      borderBottom: `1px solid ${colors.hairline}`,
                      color: colors['text-secondary'],
                      fontSize: typography.caption.fontSize,
                      fontWeight: 500, textTransform: 'uppercase',
                      letterSpacing: typography.eyebrow.letterSpacing,
                      textAlign: 'left',
                    }}>
                      <th style={{ padding: `10px ${XS}px` }}>用户 ID</th>
                      <th style={{ padding: `10px ${XS}px` }}>昵称</th>
                      <th style={{ padding: `10px ${XS}px` }}>角色</th>
                      <th style={{ padding: `10px ${XS}px` }}>加入时间</th>
                      <th style={{ padding: `10px ${XS}px` }} />
                    </tr>
                  </thead>
                  <tbody>
                    {assistants.map(a => (
                      <tr key={a.teacher_id} style={{ borderBottom: `1px solid ${colors['hairline-soft']}` }}>
                        <td style={{ padding: `10px ${XS}px`, color: colors['text-primary'] }}>{a.teacher_id}</td>
                        <td style={{ padding: `10px ${XS}px`, fontWeight: 500, color: colors['text-primary'] }}>{a.nickname}</td>
                        <td style={{ padding: `10px ${XS}px` }}>
                          <span style={{
                            display: 'inline-block', padding: '2px 12px', borderRadius: radius.pill,
                            fontSize: 12, fontWeight: 500,
                            background: colors['block-lilac'], color: green.strong,
                          }}>
                            助教
                          </span>
                        </td>
                        <td style={{ padding: `10px ${XS}px`, color: colors['text-secondary'] }}>
                          {new Date(a.joined_at).toLocaleDateString()}
                        </td>
                        <td style={{ padding: `10px ${XS}px` }}>
                          <button onClick={() => handleRemoveAssistant(a.teacher_id)} style={{
                            ...btnSmallSecondary,
                            color: colors.danger,
                            borderColor: colors.danger + '40',
                          }}>
                            <IconX size={12} color={colors.danger} /> 撤销
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
