const api = require('../../../utils/api.js');

Page({
  data: {
    loading: true,
    overall: 'ok',
    overallIcon: '',
    overallLabel: '所有服务运行正常',
    timestamp: '',
    services: [],
    expanded: [],
    // 状态标签映射
    statusLabel: {
      ok: '正常',
      degraded: '降级',
      warning: '警告',
      error: '异常'
    },
    // 整体状态配置
    overallConfig: {
      ok: { icon: '', label: '所有服务运行正常' },
      degraded: { icon: '', label: '部分服务降级运行' },
      warning: { icon: '', label: '部分服务存在警告' },
      error: { icon: '', label: '存在服务连接异常' }
    }
  },

  onLoad() {
    this.checkSystemStatus();
  },

  onShow() {
    if (!this.data.loading) {
      this.checkSystemStatus();
    }
  },

  async checkSystemStatus() {
    this.setData({ loading: true });
    try {
      // 获取后端系统状态
      const result = await this.callSystemStatusAPI();
      const services = this.processServices(result.services || []);

      const overall = result.overall || 'error';
      const oc = this.data.overallConfig[overall] || this.data.overallConfig.error;

      this.setData({
        loading: false,
        overall,
        overallIcon: '',
        overallLabel: oc.label,
        timestamp: result.timestamp || '',
        services,
        expanded: services.map(() => true) // 默认展开全部
      });
    } catch (err) {
      console.error('检测系统状态失败', err);
      this.setData({
        loading: false,
        overall: 'error',
        overallIcon: '',
        overallLabel: '无法连接后端服务',
        timestamp: '',
        services: [{
          name: '后端 API',
          status: 'error',
          statusLabel: '异常',
          latency_ms: null,
          latencyClass: '',
          detail: `连接失败: ${err.message || '未知错误'}`,
          configList: [{ key: '接口地址', val: api.BASE_URL + '/v1/system/status' }],
          extrasList: []
        }],
        expanded: [true]
      });
    }
  },

  /**
   * 调用后端系统状态接口
   */
  async callSystemStatusAPI() {
    return await api.getSystemStatus();
  },

  /**
   * 处理服务数据，添加图标、状态标签、配置列表等展示字段
   */
  processServices(rawServices) {
    return rawServices.map(svc => {
      const statusLabel = this.data.statusLabel[svc.status] || svc.status;
      const icon = '';

      // 延迟毫秒数 → 颜色类
      let latencyClass = '';
      if (svc.latency_ms != null) {
        if (svc.latency_ms < 200) latencyClass = 'green';
        else if (svc.latency_ms < 500) latencyClass = 'yellow';
        else latencyClass = 'red';
      }

      // 配置对象转 key-val 列表
      const configList = this.objToList(svc.config);

      // 额外信息转 key-val 列表
      const extrasList = this.objToList(svc.extras);

      return {
        ...svc,
        icon,
        statusLabel,
        latencyClass,
        configList,
        extrasList
      };
    });
  },

  /**
   * 对象转 [{key, val}] 列表
   */
  objToList(obj) {
    if (!obj) return [];
    const keyLabels = {
      host: '主机地址',
      port: '端口',
      user: '用户名',
      database: '数据库',
      api_base: 'API 地址',
      model: '模型',
      models: '可用模型数',
      model_available: '模型可用',
      active_db: '当前数据库',
      password: '密码'
    };
    return Object.entries(obj)
      .filter(([_, v]) => v !== null && v !== undefined && v !== '')
      .map(([k, v]) => ({
        key: keyLabels[k] || k,
        val: String(v)
      }));
  },

  /**
   * 切换某服务的详情展开/折叠
   */
  onToggleDetail(e) {
    const idx = e.currentTarget.dataset.index;
    const key = `expanded[${idx}]`;
    this.setData({ [key]: !this.data.expanded[idx] });
  },

  onRefresh() {
    this.checkSystemStatus();
  }
});
