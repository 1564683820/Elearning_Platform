// 学生端班级详情页 — 班级信息、通知、同学
const api = require('../../../utils/api.js');

Page({
  data: {
    classInfo: null,
    loading: true,
    exams: [],
  },

  onLoad(options) {
    const classId = options.classId || options.id;
    if (classId) {
      this.setData({ classId: String(classId) });
      this.loadData(String(classId));
    }
  },

  async loadData(classId) {
    try {
      wx.showLoading({ title: '加载中...' });
      const detail = await api.getMyClassDetail(classId);
      this.setData({
        classInfo: {
          id: detail.id,
          name: detail.name,
          description: detail.description || '暂无简介',
          studentCount: detail.student_count || 0,
          teacherName: detail.teacher_name || '未知教师',
          joinedAt: detail.joined_at || '',
        },
        loading: false,
      });
      wx.hideLoading();

      // 异步加载班级考试列表（可选）
      this.loadClassExams(classId);
    } catch (err) {
      wx.hideLoading();
      console.error('加载班级详情失败', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  async loadClassExams(classId) {
    try {
      const exams = await api.getExamList({ class_id: classId });
      if (exams && exams.length > 0) {
        this.setData({ exams });
      }
    } catch (err) {
      // 静默失败，班级考试列表为可选
    }
  },

  // 加入新班级模态框
  onJoinNewClass() {
    wx.showModal({
      title: '加入班级',
      content: '请输入老师提供的邀请码',
      editable: true,
      placeholderText: '请输入邀请码',
      success: async (res) => {
        if (res.confirm && res.content) {
          try {
            wx.showLoading({ title: '加入中...' });
            const result = await api.joinClass(res.content.trim());
            wx.hideLoading();
            wx.showToast({ title: '加入成功', icon: 'success' });
            // 如果是当前班级，重新加载
            if (result && result.class_id) {
              this.loadData(result.class_id);
            }
          } catch (err) {
            wx.hideLoading();
            wx.showToast({ title: '邀请码无效或已过期', icon: 'none' });
          }
        }
      },
    });
  },

  // 前往考试
  onExamTap(e) {
    const examId = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/exam/do-exam/index?examId=${examId}` });
  },
});
