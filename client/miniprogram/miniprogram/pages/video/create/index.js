// 视频演绎创建页 — 三步流程：选课文 → 选角色 → 生成
const api = require('../../../utils/api.js');

Page({
  data: {
    currentStep: 1,
    // 课文选择
    versions: [],
    grades: [],
    semesters: [],
    units: [],
    selectedVersion: '',
    selectedGrade: '',
    selectedSemester: '',
    selectedUnitId: null,
    selectedUnitName: '',
    textContent: '',
    // 角色选择
    characters: [],
    selectedCharacter: '',
    characterImageUrl: '',
    // 生成预览
    videoTitle: '',
    scriptScenes: [],
    generating: false,
  },

  onLoad() {
    this.loadVersions();
    this.loadCharacters();
  },

  // ========== 教材数据加载 ==========

  async loadVersions() {
    try {
      const data = await api.getTextbookVersions();
      this.setData({ versions: data || [] });
    } catch (err) {
      console.error('加载教材版本失败', err);
    }
  },

  async loadGrades(version) {
    try {
      const data = await api.getTextbookGrades(version);
      this.setData({ grades: data || [] });
    } catch (err) { console.error(err); }
  },

  async loadSemesters(version, grade) {
    try {
      const data = await api.getTextbookSemesters(version, grade);
      this.setData({ semesters: data || [] });
    } catch (err) { console.error(err); }
  },

  async loadUnits(version, grade, semester) {
    try {
      const data = await api.getTextbookUnits(version, grade, semester);
      this.setData({ units: (data || []).map(u => u.unit_name || u) });
    } catch (err) { console.error(err); }
  },

  async loadUnitDetail(version, grade, semester, unit) {
    try {
      const pages = await api.getTextbookPages(version, grade, semester, unit);
      const text = (pages || []).map(p => p.text_content || '').filter(Boolean).join('\n');
      this.setData({ textContent: text });
    } catch (err) { console.error('加载课文内容失败', err); }
  },

  // ========== 教材选择事件 ==========

  onVersionChange(e) {
    const idx = e.detail.value;
    const version = this.data.versions[idx];
    this.setData({
      selectedVersion: version, selectedGrade: '', selectedSemester: '',
      selectedUnitId: null, selectedUnitName: '', textContent: '',
      grades: [], semesters: [], units: [],
    });
    this.loadGrades(version);
  },

  onGradeChange(e) {
    if (!this.data.selectedVersion) return;
    const idx = e.detail.value;
    const grade = this.data.grades[idx];
    this.setData({
      selectedGrade: grade, selectedSemester: '',
      selectedUnitId: null, selectedUnitName: '', textContent: '',
      semesters: [], units: [],
    });
    this.loadSemesters(this.data.selectedVersion, grade);
  },

  onSemesterChange(e) {
    if (!this.data.selectedGrade) return;
    const idx = e.detail.value;
    const semester = this.data.semesters[idx];
    this.setData({
      selectedSemester: semester,
      selectedUnitId: null, selectedUnitName: '', textContent: '',
      units: [],
    });
    this.loadUnits(this.data.selectedVersion, this.data.selectedGrade, semester);
  },

  onUnitChange(e) {
    if (!this.data.selectedSemester) return;
    const idx = e.detail.value;
    const unitName = this.data.units[idx];
    // 单元索引从1开始
    const unitIndex = idx + 1;
    this.setData({
      selectedUnitId: unitIndex,
      selectedUnitName: unitName,
    });
    this.loadUnitDetail(
      this.data.selectedVersion,
      this.data.selectedGrade,
      this.data.selectedSemester,
      unitIndex,
    );
  },

  // ========== 角色选择 ==========

  async loadCharacters() {
    try {
      const data = await api.getVideoCharacters();
      this.setData({ characters: data || [] });
      if (data && data.length > 0) {
        this.setData({ selectedCharacter: data[0].character_key });
      }
    } catch (err) {
      console.error('加载角色失败', err);
      // 使用默认角色
      this.setData({
        characters: [
          { character_key: 'cat_teacher', name: '小猫老师', description: '可爱温柔的猫咪老师', image_url: '' },
          { character_key: 'kevin', name: 'Kevin', description: '活力阳光的小男孩', image_url: '' },
          { character_key: 'emma', name: 'Emma', description: '甜美可爱的小女孩', image_url: '' },
          { character_key: 'owl_professor', name: '博士猫头鹰', description: '博学稳重的猫头鹰教授', image_url: '' },
        ],
        selectedCharacter: 'cat_teacher',
      });
    }
  },

  onSelectCharacter(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ selectedCharacter: key, characterImageUrl: '' });
  },

  onUploadCharacter() {
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const tempFilePath = res.tempFilePaths[0];
        // 上传到云存储
        wx.cloud.uploadFile({
          cloudPath: `character/${Date.now()}_${Math.random().toString(36).slice(2)}.jpg`,
          filePath: tempFilePath,
          success: (uploadRes) => {
            this.setData({
              characterImageUrl: uploadRes.fileID,
              selectedCharacter: 'custom',
            });
            wx.showToast({ title: '上传成功', icon: 'success' });
          },
          fail: (err) => {
            console.error('上传失败', err);
            wx.showToast({ title: '上传失败', icon: 'none' });
          },
        });
      },
    });
  },

  // ========== 步骤切换 ==========

  onGoStep1() {
    this.setData({ currentStep: 1 });
  },

  onGoStep2() {
    this.setData({ currentStep: 2 });
  },

  async onGoStep3() {
    // 切换到第三步后，发起 AI 分镜脚本生成
    this.setData({ currentStep: 3 });
    await this.generateScript();
  },

  async generateScript() {
    const name = this.data.characters.find(c => c.character_key === this.data.selectedCharacter)?.name || this.data.selectedCharacter;
    try {
      const data = await api.generateVideoScript({
        text_content: this.data.textContent,
        character_name: name,
      });
      this.setData({
        scriptScenes: data.scenes || [],
      });
    } catch (err) {
      console.error('生成分镜脚本失败', err);
    }
  },

  onTitleInput(e) {
    this.setData({ videoTitle: e.detail.value });
  },

  // ========== 视频生成 ==========

  async onGenerate() {
    if (!this.data.selectedUnitId) {
      wx.showToast({ title: '请选择课文', icon: 'none' });
      return;
    }
    if (!this.data.textContent) {
      wx.showToast({ title: '课文内容为空', icon: 'none' });
      return;
    }

    this.setData({ generating: true });

    try {
      const result = await api.createVideo({
        title: this.data.videoTitle || `${this.data.selectedUnitName} · ${this.data.selectedCharacterName || ''}演绎`,
        textbook_version: this.data.selectedVersion,
        textbook_grade: this.data.selectedGrade,
        textbook_semester: this.data.selectedSemester,
        unit_id: this.data.selectedUnitId,
        unit_name: this.data.selectedUnitName,
        page_ids: [],
        text_content: this.data.textContent,
        character_type: this.data.selectedCharacter,
        character_image_url: this.data.characterImageUrl || undefined,
      });

      wx.showToast({ title: '视频生成任务已提交', icon: 'success' });

      // 跳转到观看页
      wx.redirectTo({
        url: `/pages/video/watch/index?videoId=${result.id}`,
      });
    } catch (err) {
      console.error('创建视频失败', err);
      wx.showToast({ title: '创建失败，请重试', icon: 'none' });
    } finally {
      this.setData({ generating: false });
    }
  },

  // ========== 计算属性 ==========

  get selectedCharacterName() {
    const char = this.data.characters.find(c => c.character_key === this.data.selectedCharacter);
    return char ? char.name : '';
  },

  get characterPreviewUrl() {
    if (this.data.characterImageUrl) return this.data.characterImageUrl;
    const char = this.data.characters.find(c => c.character_key === this.data.selectedCharacter);
    return char ? char.image_url : '';
  },

  get textContent() {
    return this.data.textContent;
  },
});
