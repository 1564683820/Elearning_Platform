// 登录/注册页 + 产品简介落地页 — 右偏登录卡片 + 杂志式滚动产品展示
import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import client, { loginReturnPath } from '../../api/client';
import './login.css';

export default function Login() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [form, setForm] = useState({
    account: '', username: '', password: '', inviteCode: '',
    role: 'teacher',
    loginRole: 'teacher',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(() => new URLSearchParams(location.search).get('expired') === '1'
    ? '登录会话已失效，请重新登录。' : '');
  const [navScrolled, setNavScrolled] = useState(false);
  const [showScrollTop, setShowScrollTop] = useState(false);

  // Intersection Observer 控制滚动渐入
  const revealRefs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const onScroll = () => {
      const scrollY = window.scrollY;
      setNavScrolled(scrollY > 60);
      setShowScrollTop(scrollY > window.innerHeight);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
          }
        });
      },
      { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
    );
    revealRefs.current.forEach((el) => {
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);

  const setRevealRef = useCallback((el: HTMLElement | null) => {
    if (el && !revealRefs.current.includes(el)) {
      revealRefs.current.push(el);
    }
  }, []);

  // 登录逻辑
  const getLoginEndpoint = (loginRole: string) => {
    if (loginRole === 'admin') return '/auth/admin/login';
    return '/auth/teacher/login';
  };

  const handleSubmit = async () => {
    setLoading(true);
    setError('');
    try {
      const endpoint = mode === 'login' ? getLoginEndpoint(form.loginRole) : '/auth/register';
      const payload = mode === 'login'
        ? { account: form.account, password: form.password }
        : {
            account: form.account,
            username: form.username,
            password: form.password,
            role: form.role,
            inviteCode: form.inviteCode,
          };
      const res = await client.post(endpoint, payload);
      const data = res.data.data;
      localStorage.setItem('token', data.token);
      localStorage.setItem('user', JSON.stringify(data.user));
      const userRole = data.user?.role || 'teacher';
      navigate(loginReturnPath(userRole) ?? (userRole === 'admin' ? '/admin/dashboard' : '/classes'), { replace: true });
    } catch (err: any) {
      setError(err.response?.data?.message || err.message || '操作失败');
    } finally {
      setLoading(false);
    }
  };

  const scrollTo = (id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <>
      {/* ===== 顶部透明导航栏 ===== */}
      <nav className={`navbar ${navScrolled ? 'scrolled' : ''}`}>
        <div className="logo">
          <i className="fa-solid fa-graduation-cap" />
          E-Learning
        </div>
        <div className="nav-links">
          <a onClick={() => scrollTo('login-section')}>
            <i className="fa-solid fa-right-to-bracket" />
            登录
          </a>
          <a onClick={() => scrollTo('product-intro')}>
            <i className="fa-solid fa-book-open" />
            产品简介
          </a>
        </div>
      </nav>

      {/* ===== 第 1 屏：登录区 ===== */}
      <section id="login-section" className="login-section">
        {/* 左侧品牌文案 */}
        <div className="hero-left">
          <div className="hero-badge">
            <i className="fa-solid fa-leaf" /> 智慧教育平台
          </div>
          <h1>
            AI助力学习
            <br />
            让每一节课都
            <br />
            <span className="green">活起来</span>
          </h1>
          <p className="hero-tagline">
            从 AI 备课到课堂互动，从学情分析到个性化辅导，<br />
            E-Learning 为教师与学生打造全链路数字化教学体验。
          </p>
        </div>

        {/* 登录卡片 */}
        <div className="login-card">
          <div className="card-header">
            <h2 className="brand-title">
              <i className="fa-solid fa-leaf" />E-Learning
            </h2>
            <p className="card-subtitle">
              {mode === 'login' ? '使用账号密码登录' : '使用邀请码注册账号'}
            </p>
          </div>

          {/* 登录/注册切换 */}
          <div className="mode-tabs">
            {(['login', 'register'] as const).map((m) => (
              <button
                key={m}
                className={`mode-tab ${mode === m ? 'active' : ''}`}
                onClick={() => { setMode(m); setError(''); }}
              >
                {m === 'login' ? '登录' : '注册'}
              </button>
            ))}
          </div>

          {/* 账号 */}
          <div className="input-group">
            <i className="fa-solid fa-user" />
            <input
              placeholder="账号"
              value={form.account}
              onChange={(e) => setForm({ ...form, account: e.target.value })}
            />
          </div>

          {mode === 'register' && (
            <div className="input-group">
              <i className="fa-solid fa-id-card" />
              <input
                placeholder="用户名（显示用）"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
              />
            </div>
          )}

          {/* 密码 */}
          <div className="input-group">
            <i className="fa-solid fa-lock" />
            <input
              type="password"
              placeholder="密码"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            />
          </div>

          {/* 登录角色选择 */}
          {mode === 'login' && (
            <div className="role-selector">
              {[
                { value: 'teacher', label: '教师', icon: 'fa-solid fa-chalkboard-user', color: '#2d7d46' },
                { value: 'admin', label: '管理者', icon: 'fa-solid fa-shield-halved', color: '#5B9E6F' },
              ].map((r) => (
                <div
                  key={r.value}
                  className={`role-btn ${form.loginRole === r.value ? 'active-teacher' : ''}`}
                  onClick={() => setForm({ ...form, loginRole: r.value })}
                >
                  <i className={r.icon} />
                  {r.label}
                </div>
              ))}
            </div>
          )}

          {/* 注册角色选择 */}
          {mode === 'register' && (
            <div className="role-selector">
              {[
                { value: 'teacher', label: '教师', icon: 'fa-solid fa-chalkboard-user', color: '#2d7d46' },
                { value: 'student', label: '学生', icon: 'fa-solid fa-user-graduate', color: '#3b82f6' },
              ].map((r) => (
                <div
                  key={r.value}
                  className={`role-btn ${form.role === r.value ? 'active-teacher' : ''}`}
                  onClick={() => setForm({ ...form, role: r.value })}
                >
                  <i className={r.icon} />
                  {r.label}
                </div>
              ))}
            </div>
          )}

          {/* 注册 - 邀请码 */}
          {mode === 'register' && (
            <div className="input-group">
              <i className="fa-solid fa-ticket" />
              <input
                placeholder="邀请码"
                value={form.inviteCode}
                onChange={(e) => setForm({ ...form, inviteCode: e.target.value })}
              />
            </div>
          )}

          {error && <p className="error-msg"><i className="fa-solid fa-circle-exclamation" /> {error}</p>}

          <button className="submit-btn" onClick={handleSubmit} disabled={loading}>
            {loading ? <><i className="fa-solid fa-spinner fa-spin" /> 处理中...</> : mode === 'login' ? '登 录' : '注 册'}
          </button>

          <p style={{ textAlign: 'center', color: '#b0bcc8', fontSize: 12, marginTop: 16, fontFamily: "'Noto Sans SC', sans-serif" }}>
            {mode === 'login'
              ? '教师/管理者使用账号密码登录'
              : '请选择注册角色并输入对应类型的邀请码'}
          </p>
        </div>
      </section>

      {/* ===== 第 2 屏起：产品简介 ===== */}
      <section id="product-intro">
        {/* ---- 产品名称 ---- */}
        <div className="product-section product-title-section">
          <div className="section-content">
            <div
              ref={setRevealRef}
              className="reveal-item"
              style={{ textAlign: 'center' }}
            >
              <div className="product-title-main">
                <span className="green">E-Learning</span> 智慧教育
              </div>
              <p className="product-title-sub">
                AI 驱动的全场景数字化教学平台
              </p>
              <div className="product-title-divider" />
            </div>

            <div
              ref={setRevealRef}
              className="reveal-item delay-2"
              style={{
                maxWidth: 700,
                margin: '48px auto 0',
                textAlign: 'center',
                fontFamily: "'Noto Sans SC', sans-serif",
                fontSize: 15,
                color: 'rgba(255,255,255,0.5)',
                lineHeight: 1.9,
              }}
            >
              深度融合人工智能、大数据分析与云计算技术，
              为 K12 及高等教育机构提供覆盖<span style={{ color: '#5B9E6F', fontWeight: 500 }}>备课、授课、练习、测评、管理</span>
              全环节的一站式智慧教育解决方案。
            </div>
          </div>
        </div>

        {/* ---- 产品应用场景 ---- */}
        <div className="product-section scenarios-bg">
          <div className="section-content">
            <div
              ref={setRevealRef}
              className="reveal-item"
              style={{ textAlign: 'center', marginBottom: 16 }}
            >
              <p style={{
                fontFamily: "'Noto Sans SC', sans-serif",
                fontSize: 13,
                color: '#5B9E6F',
                letterSpacing: 3,
                textTransform: 'uppercase',
                margin: '0 0 8px 0',
              }}>
                <i className="fa-solid fa-compass" /> 应用场景
              </p>
              <h2 style={{
                fontFamily: "'Playfair Display', serif",
                fontSize: 40,
                fontWeight: 700,
                color: '#fff',
                margin: 0,
              }}>
                覆盖教学全流程
              </h2>
            </div>

            <div className="scenario-grid">
              {[
                {
                  icon: 'fa-solid fa-chalkboard',
                  color: '#5B9E6F',
                  bg: 'rgba(91,158,111,0.12)',
                  title: 'AI 智能备课',
                  desc: '基于知识图谱与大语言模型，自动生成教案、PPT 课件与课后练习，将备课时间从数小时缩短至分钟级。',
                },
                {
                  icon: 'fa-solid fa-people-group',
                  color: '#5B9E6F',
                  bg: 'rgba(91,158,111,0.12)',
                  title: '互动课堂教学',
                  desc: '实时弹幕互动、随堂测验、即时投票，搭配智能白板与多屏同步，让每一节课都充满参与感。',
                },
                {
                  icon: 'fa-solid fa-chart-line',
                  color: '#5B9E6F',
                  bg: 'rgba(91,158,111,0.12)',
                  title: '精准学情分析',
                  desc: '多维度学习数据追踪，AI 自动生成学生能力画像与薄弱点诊断，为个性化辅导提供科学依据。',
                },
              ].map((item, i) => (
                <div
                  key={i}
                  ref={setRevealRef}
                  className={`reveal-item delay-${i + 1}`}
                >
                  <div className="scenario-card">
                    <div className="scenario-icon" style={{ background: item.bg, color: item.color }}>
                      <i className={item.icon} />
                    </div>
                    <h3>{item.title}</h3>
                    <p>{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ---- 学生端功能 ---- */}
        <div className="product-section">
          <div className="section-content">
            <div
              ref={setRevealRef}
              className="reveal-item feature-header"
            >
              <h2><i className="fa-solid fa-user-graduate" /> 学生端功能</h2>
              <p>沉浸式学习体验，让自主学习更高效、更有趣</p>
            </div>

            <div className="prototype-grid">
              {[
                {
                  ref: setRevealRef,
                  delay: 1,
                  theme: 'theme-green',
                  title: 'AI 课程学习',
                  desc: '自适应学习路径 + 多模态课件',
                  statusColor: '#5B9E6F',
                  headerBg: 'rgba(91,158,111,0.2)',
                },
                {
                  ref: setRevealRef,
                  delay: 2,
                  theme: 'theme-blue',
                  title: '智能题库练习',
                  desc: 'AI 错题分析 + 薄弱点专项训练',
                  statusColor: '#4a80d0',
                  headerBg: 'rgba(74,128,208,0.2)',
                },
                {
                  ref: setRevealRef,
                  delay: 3,
                  theme: 'theme-amber',
                  title: '直播互动课堂',
                  desc: '实时弹幕 + 举手答题 + 小组讨论',
                  statusColor: '#d0a04a',
                  headerBg: 'rgba(208,160,74,0.2)',
                },
                {
                  ref: setRevealRef,
                  delay: 4,
                  theme: 'theme-teal',
                  title: '学习成长报告',
                  desc: '可视化数据看板 + 进步曲线',
                  statusColor: '#4a9d9d',
                  headerBg: 'rgba(74,157,157,0.2)',
                },
              ].map((item, i) => (
                <div
                  key={i}
                  ref={item.ref}
                  className={`reveal-item delay-${item.delay}`}
                >
                  <div className="prototype-card">
                    <div className={`mockup-phone ${item.theme}`}>
                      <div className="mockup-status">
                        <span>9:41</span>
                        <span><i className="fa-solid fa-signal" /> <i className="fa-solid fa-wifi" /> <i className="fa-solid fa-battery-three-quarters" /></span>
                      </div>
                      <div className="mockup-header" style={{ background: item.headerBg }}>
                        <i className={[
                          'fa-solid fa-book-open',
                          'fa-solid fa-pen',
                          'fa-solid fa-comments',
                          'fa-solid fa-chart-simple',
                        ][i]} style={{ marginRight: 6 }} /> {['课程学习', '智能练习', '互动课堂', '学情报告'][i]}
                      </div>
                      <div className="mockup-body">
                        {i === 0 && (
                          <>
                            <div className="mock-line wide" />
                            <div className="mock-row">
                              <div className="mock-thumb" style={{ background: 'rgba(91,158,111,0.15)' }} />
                              <div className="mock-thumb" style={{ background: 'rgba(91,158,111,0.15)' }} />
                            </div>
                            <div className="mock-block" style={{ background: 'rgba(91,158,111,0.1)' }} />
                            <div className="mock-progress" />
                            <div className="mock-line medium" />
                            <div className="mock-line narrow" />
                          </>
                        )}
                        {i === 1 && (
                          <>
                            <div className="mock-line wide" />
                            <div className="mock-block" style={{ background: 'rgba(74,128,208,0.1)', height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: 20, fontFamily: 'serif' }}>?</span>
                            </div>
                            <div className="mock-line medium" />
                            <div className="mock-row">
                              <div style={{ flex: 1, padding: '6px 8px', background: 'rgba(74,128,208,0.12)', borderRadius: 6, textAlign: 'center' }}>
                                <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: 11 }}>A</span>
                              </div>
                              <div style={{ flex: 1, padding: '6px 8px', background: 'rgba(74,128,208,0.12)', borderRadius: 6, textAlign: 'center' }}>
                                <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: 11 }}>B</span>
                              </div>
                            </div>
                            <div className="mock-row">
                              <div style={{ flex: 1, padding: '6px 8px', background: 'rgba(74,128,208,0.12)', borderRadius: 6, textAlign: 'center' }}>
                                <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: 11 }}>C</span>
                              </div>
                              <div style={{ flex: 1, padding: '6px 8px', background: 'rgba(74,128,208,0.12)', borderRadius: 6, textAlign: 'center' }}>
                                <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: 11 }}>D</span>
                              </div>
                            </div>
                          </>
                        )}
                        {i === 2 && (
                          <>
                            <div className="mock-block" style={{ background: 'rgba(208,160,74,0.1)', height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 4 }}>
                              <i className="fa-solid fa-play" style={{ color: 'rgba(255,255,255,0.15)', fontSize: 28 }} />
                              <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: 10 }}>直播中</span>
                            </div>
                            <div className="mock-line wide" />
                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                              {['😊', '👍', '🔥', '💡'].map((e, j) => (
                                <span key={j} style={{ fontSize: 12, opacity: 0.15 }}>{e}</span>
                              ))}
                            </div>
                          </>
                        )}
                        {i === 3 && (
                          <>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                              <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: 10 }}>本周</span>
                              <span style={{ color: 'rgba(74,157,157,0.4)', fontSize: 10 }}>+12%</span>
                            </div>
                            <div className="mock-block" style={{ background: 'rgba(74,157,157,0.1)', height: 50 }} />
                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                              {['一', '二', '三', '四', '五'].map((d, j) => (
                                <div key={j} style={{
                                  width: 20, height: 20, borderRadius: 4,
                                  background: j === 3 ? 'rgba(74,157,157,0.25)' : 'rgba(255,255,255,0.05)',
                                }} />
                              ))}
                            </div>
                            <div className="mock-line medium" />
                            <div className="mock-line narrow" />
                          </>
                        )}
                      </div>
                    </div>
                    <p className="prototype-title">{item.title}</p>
                    <p className="prototype-desc">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ---- 教师端功能 ---- */}
        <div className="product-section">
          <div className="section-content">
            <div
              ref={setRevealRef}
              className="reveal-item feature-header"
            >
              <h2><i className="fa-solid fa-chalkboard-user" /> 教师端功能</h2>
              <p>强大高效的智慧教学工具，让教学管理轻而易举</p>
            </div>

            <div className="prototype-grid">
              {[
                {
                  delay: 1,
                  theme: 'theme-green',
                  title: 'AI PPT 课件生成',
                  desc: '输入主题，AI 自动生成精美课件',
                  headerBg: 'rgba(91,158,111,0.2)',
                },
                {
                  delay: 2,
                  theme: 'theme-blue',
                  title: '智能组卷阅卷',
                  desc: 'AI 出题 + 自动批改 + 成绩分析',
                  headerBg: 'rgba(74,128,208,0.2)',
                },
                {
                  delay: 3,
                  theme: 'theme-teal',
                  title: '课堂实时互动',
                  desc: '投票、测验、弹幕 — 掌控课堂节奏',
                  headerBg: 'rgba(74,157,157,0.2)',
                },
                {
                  delay: 4,
                  theme: 'theme-amber',
                  title: '学情数据看板',
                  desc: '全班学情一目了然，精准定位薄弱点',
                  headerBg: 'rgba(208,160,74,0.2)',
                },
              ].map((item, i) => (
                <div
                  key={i}
                  ref={setRevealRef}
                  className={`reveal-item delay-${item.delay}`}
                >
                  <div className="prototype-card">
                    <div className={`mockup-phone ${item.theme}`}>
                      <div className="mockup-status">
                        <span>9:41</span>
                        <span><i className="fa-solid fa-signal" /> <i className="fa-solid fa-wifi" /> <i className="fa-solid fa-battery-three-quarters" /></span>
                      </div>
                      <div className="mockup-header" style={{ background: item.headerBg }}>
                        <i className={[
                          'fa-solid fa-file-powerpoint',
                          'fa-solid fa-file-pen',
                          'fa-solid fa-presentation-screen',
                          'fa-solid fa-chart-pie',
                        ][i]} style={{ marginRight: 6 }} /> {['AI 备课', '智能阅卷', '互动课堂', '数据看板'][i]}
                      </div>
                      <div className="mockup-body">
                        {i === 0 && (
                          <>
                            <div className="mock-line wide" />
                            <div className="mock-block" style={{ background: 'rgba(91,158,111,0.08)', height: 80 }} />
                            <div style={{ display: 'flex', gap: 6 }}>
                              {['封面', '目录', '正文', '总结'].map((t, j) => (
                                <span key={j} style={{
                                  padding: '4px 8px', borderRadius: 4, fontSize: 9,
                                  background: j === 0 ? 'rgba(91,158,111,0.2)' : 'rgba(255,255,255,0.05)',
                                  color: 'rgba(255,255,255,0.3)',
                                }}>{t}</span>
                              ))}
                            </div>
                            <div className="mock-line medium" />
                            <div className="mock-line narrow" />
                          </>
                        )}
                        {i === 1 && (
                          <>
                            <div className="mock-block" style={{ background: 'rgba(74,128,208,0.08)', height: 60 }}>
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                                <span style={{ color: 'rgba(74,128,208,0.3)', fontSize: 22, fontWeight: 700 }}>92</span>
                                <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: 10, marginLeft: 4 }}>/100</span>
                              </div>
                            </div>
                            <div className="mock-line wide" />
                            <div className="mock-line medium" />
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <span style={{ color: 'rgba(255,255,255,0.1)', fontSize: 9 }}>客观题 ✓</span>
                              <span style={{ color: 'rgba(255,255,255,0.1)', fontSize: 9 }}>主观题 待批</span>
                            </div>
                            <div className="mock-progress" style={{ width: '90%' }} />
                          </>
                        )}
                        {i === 2 && (
                          <>
                            <div className="mock-block" style={{ background: 'rgba(74,157,157,0.08)', height: 70, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
                              <i className="fa-solid fa-chart-simple" style={{ color: 'rgba(74,157,157,0.2)', fontSize: 24 }} />
                            </div>
                            <div className="mock-row">
                              <div className="mock-thumb" style={{ background: 'rgba(74,157,157,0.1)' }} />
                              <div className="mock-thumb" style={{ background: 'rgba(74,157,157,0.1)' }} />
                              <div className="mock-thumb" style={{ background: 'rgba(74,157,157,0.1)' }} />
                            </div>
                            <div className="mock-line wide" />
                            <div className="mock-line medium" />
                            <div style={{ textAlign: 'center' }}>
                              <span style={{ color: 'rgba(255,255,255,0.08)', fontSize: 11 }}>📊 参与率 87%</span>
                            </div>
                          </>
                        )}
                        {i === 3 && (
                          <>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                              <span style={{ color: 'rgba(255,255,255,0.1)', fontSize: 9 }}>班级平均分</span>
                              <span style={{ color: 'rgba(208,160,74,0.4)', fontSize: 10, fontWeight: 600 }}>78.5</span>
                            </div>
                            <div className="mock-row">
                              <div className="mock-thumb" style={{ background: 'rgba(208,160,74,0.1)', height: 60 }} />
                              <div className="mock-thumb" style={{ background: 'rgba(208,160,74,0.06)', height: 40 }} />
                              <div className="mock-thumb" style={{ background: 'rgba(208,160,74,0.08)', height: 50 }} />
                            </div>
                            <div className="mock-line wide" />
                            <div className="mock-dot-grid">
                              {Array.from({ length: 9 }).map((_, j) => (
                                <div key={j} className="mock-dot" style={{
                                  background: j < 5 ? 'rgba(208,160,74,0.1)' : 'rgba(255,255,255,0.04)',
                                }} />
                              ))}
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                    <p className="prototype-title">{item.title}</p>
                    <p className="prototype-desc">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ---- 结束语 ---- */}
      <section className="closing-section">
        <div ref={setRevealRef} className="reveal-item">
          <h2 className="closing-title">
            开启 <span className="green">智慧教育</span> 之旅
          </h2>
          <p className="closing-text">
            无论您是学校管理者、一线教师还是学生，<br />
            E-Learning 都将为您带来前所未有的教学体验。
          </p>
          <div className="closing-cta">
            <button onClick={() => scrollTo('login-section')}>
              <i className="fa-solid fa-right-to-bracket" style={{ marginRight: 8 }} />
              立即体验
            </button>
          </div>
        </div>
      </section>

      {/* 回到顶部按钮 */}
      <button
        className={`scroll-top-btn ${showScrollTop ? 'visible' : ''}`}
        onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
        aria-label="回到顶部"
      >
        <i className="fa-solid fa-arrow-up" />
      </button>
    </>
  );
}
