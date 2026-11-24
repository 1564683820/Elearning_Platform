const api = require('../../utils/api.js');
const app = getApp();

Page({
  data: {
    // 登录
    mode: 'login',
    account: '',
    password: '',
    loginRole: 'student', // student/teacher
    loading: false,
    errorMsg: '',
    // 注册
    regAccount: '',
    regUsername: '',
    regPassword: '',
    regRole: 'student', // student/teacher
    inviteCode: '',
    regLoading: false,
    regErrorMsg: '',
  },

  // ─── 模式切换 ───
  switchMode(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({
      mode,
      errorMsg: '',
      regErrorMsg: '',
    });
  },

  // ─── 登录输入 ───
  onAccountInput(e) {
    this.setData({ account: e.detail.value, errorMsg: '' });
  },
  onPasswordInput(e) {
    this.setData({ password: e.detail.value, errorMsg: '' });
  },

  // ─── 注册输入 ───
  onRegAccountInput(e) {
    this.setData({ regAccount: e.detail.value, regErrorMsg: '' });
  },
  onRegUsernameInput(e) {
    this.setData({ regUsername: e.detail.value, regErrorMsg: '' });
  },
  onRegPasswordInput(e) {
    this.setData({ regPassword: e.detail.value, regErrorMsg: '' });
  },
  onInviteCodeInput(e) {
    this.setData({ inviteCode: e.detail.value, regErrorMsg: '' });
  },
  // 登录角色选择
  onLoginRoleSelect(e) {
    this.setData({ loginRole: e.currentTarget.dataset.role, errorMsg: '' });
  },
  // 注册角色选择
  onRegRoleSelect(e) {
    this.setData({ regRole: e.currentTarget.dataset.role, regErrorMsg: '' });
  },

  // ─── 登录 ───
  async onLogin() {
    const { account, password, loginRole } = this.data;
    if (!account.trim()) {
      this.setData({ errorMsg: '请输入账号' });
      return;
    }
    if (!password.trim()) {
      this.setData({ errorMsg: '请输入密码' });
      return;
    }

    this.setData({ loading: true, errorMsg: '' });

    try {
      // 根据所选角色调用不同后端接口
      const result = await api.loginWithPassword(account.trim(), password, loginRole);

      if (result && result.token) {
        wx.setStorageSync('auth_token', result.token);
        api.setAuthToken(result.token);

        try {
          const profile = await api.getUserProfile();
          if (profile) {
            app._applyProfile(profile);
            if (!profile.role || profile.role === '') {
              app.globalData.isNewUser = true;
              wx.redirectTo({ url: '/pages/auth/role-select/index' });
              return;
            }
          }
        } catch (err) {
          console.error('加载用户资料失败', err);
        }

        // 根据选择的角色跳转
        if (loginRole === 'teacher') {
          wx.redirectTo({ url: '/pages/teacher/class/index' });
        } else {
          wx.switchTab({ url: '/pages/home/index' });
        }
      } else {
        this.setData({ errorMsg: result?.message || '登录失败，请重试' });
      }
    } catch (err) {
      this.setData({ errorMsg: err.message || '网络错误，请重试' });
    } finally {
      this.setData({ loading: false });
    }
  },

  // ─── 注册 ───
  async onRegister() {
    const { regAccount, regUsername, regPassword, regRole, inviteCode } = this.data;
    if (!regAccount.trim()) {
      this.setData({ regErrorMsg: '请输入账号' });
      return;
    }
    if (!regUsername.trim()) {
      this.setData({ regErrorMsg: '请输入用户名' });
      return;
    }
    if (!regPassword.trim()) {
      this.setData({ regErrorMsg: '请输入密码' });
      return;
    }
    if (!inviteCode.trim()) {
      this.setData({ regErrorMsg: '请输入邀请码' });
      return;
    }

    this.setData({ regLoading: true, regErrorMsg: '' });

    try {
      const result = await api.registerWithInviteCode(
        regAccount.trim(),
        regUsername.trim(),
        regPassword,
        regRole,
        inviteCode.trim()
      );

      if (result && result.token) {
        wx.setStorageSync('auth_token', result.token);
        api.setAuthToken(result.token);

        // 加载用户资料
        try {
          const profile = await api.getUserProfile();
          if (profile) {
            app._applyProfile(profile);
          }
        } catch (err) {
          console.error('加载用户资料失败', err);
        }

        wx.showToast({ title: '注册成功', icon: 'success' });
        setTimeout(() => {
          if (regRole === 'teacher') {
            wx.redirectTo({ url: '/pages/teacher/class/index' });
          } else {
            wx.switchTab({ url: '/pages/home/index' });
          }
        }, 1000);
      } else {
        this.setData({ regErrorMsg: result?.message || '注册失败，请重试' });
      }
    } catch (err) {
      this.setData({ regErrorMsg: err.message || '网络错误，请重试' });
    } finally {
      this.setData({ regLoading: false });
    }
  },
});
