// 产品介绍页 — 独立全屏页面，左上角有返回按钮
import { useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { IconBack } from '../../design-system';
import './product-intro.css';

export default function ProductIntro() {
  const navigate = useNavigate();
  const revealRefs = useRef<(HTMLElement | null)[]>([]);

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
    revealRefs.current.forEach((el) => { if (el) observer.observe(el); });
    return () => observer.disconnect();
  }, []);

  const setRevealRef = useCallback((el: HTMLElement | null) => {
    if (el && !revealRefs.current.includes(el)) revealRefs.current.push(el);
  }, []);

  return (
    <>
      {/* 左上角返回按钮 */}
      <button className="pi-back-btn" onClick={() => navigate(-1)} aria-label="返回">
        <IconBack size={20} color="#fff" />
        <span>返回</span>
      </button>

      {/* 产品名称 */}
      <section className="pi-section pi-title-section">
        <div className="pi-section-content">
          <div ref={setRevealRef} className="pi-reveal" style={{ textAlign: 'center' }}>
            <div className="pi-title-main"><span className="pi-green">E-Learning</span> 智慧教育</div>
            <p className="pi-title-sub">AI 驱动的全场景数字化教学平台</p>
            <div className="pi-title-divider" />
          </div>
          <div ref={setRevealRef} className="pi-reveal pi-delay-2" style={{ maxWidth: 700, margin: '48px auto 0', textAlign: 'center', fontFamily: "'Noto Sans SC', sans-serif", fontSize: 15, color: 'rgba(255,255,255,0.5)', lineHeight: 1.9 }}>
            深度融合人工智能、大数据分析与云计算技术，为 K12 及高等教育机构提供覆盖<span style={{ color: '#5B9E6F', fontWeight: 500 }}>备课、授课、练习、测评、管理</span>全环节的一站式智慧教育解决方案。
          </div>
        </div>
      </section>

      {/* 应用场景 */}
      <section className="pi-section pi-scenarios-bg">
        <div className="pi-section-content">
          <div ref={setRevealRef} className="pi-reveal" style={{ textAlign: 'center', marginBottom: 16 }}>
            <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: 13, color: '#5B9E6F', letterSpacing: 3, textTransform: 'uppercase', margin: '0 0 8px 0' }}>
              <i className="fa-solid fa-compass" /> 应用场景
            </p>
            <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: 40, fontWeight: 700, color: '#fff', margin: 0 }}>覆盖教学全流程</h2>
          </div>
          <div className="pi-scenario-grid">
            {[
              { icon: 'fa-solid fa-chalkboard', title: 'AI 智能备课', desc: '基于知识图谱与大语言模型，自动生成教案、PPT 课件与课后练习，将备课时间从数小时缩短至分钟级。' },
              { icon: 'fa-solid fa-people-group', title: '互动课堂教学', desc: '实时弹幕互动、随堂测验、即时投票，搭配智能白板与多屏同步，让每一节课都充满参与感。' },
              { icon: 'fa-solid fa-chart-line', title: '精准学情分析', desc: '多维度学习数据追踪，AI 自动生成学生能力画像与薄弱点诊断，为个性化辅导提供科学依据。' },
            ].map((item, i) => (
              <div key={i} ref={setRevealRef} className={`pi-reveal pi-delay-${i + 1}`}>
                <div className="pi-scenario-card">
                  <div className="pi-scenario-icon" style={{ background: 'rgba(91,158,111,0.12)', color: '#5B9E6F' }}>
                    <i className={item.icon} />
                  </div>
                  <h3>{item.title}</h3>
                  <p>{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 学生端功能 */}
      <section className="pi-section">
        <div className="pi-section-content">
          <div ref={setRevealRef} className="pi-reveal pi-feature-header">
            <h2><i className="fa-solid fa-user-graduate" /> 学生端功能</h2>
            <p>沉浸式学习体验，让自主学习更高效、更有趣</p>
          </div>
          <div className="pi-prototype-grid">
            {[
              { delay: 1, theme: 'pi-theme-green', title: 'AI 课程学习', desc: '自适应学习路径 + 多模态课件', headerBg: 'rgba(91,158,111,0.2)' },
              { delay: 2, theme: 'pi-theme-blue', title: '智能题库练习', desc: 'AI 错题分析 + 薄弱点专项训练', headerBg: 'rgba(74,128,208,0.2)' },
              { delay: 3, theme: 'pi-theme-amber', title: '直播互动课堂', desc: '实时弹幕 + 举手答题 + 小组讨论', headerBg: 'rgba(208,160,74,0.2)' },
              { delay: 4, theme: 'pi-theme-teal', title: '学习成长报告', desc: '可视化数据看板 + 进步曲线', headerBg: 'rgba(74,157,157,0.2)' },
            ].map((item, i) => (
              <div key={i} ref={setRevealRef} className={`pi-reveal pi-delay-${item.delay}`}>
                <div className="pi-prototype-card">
                  <div className={`pi-mockup-phone ${item.theme}`}>
                    <div className="pi-mockup-status"><span>9:41</span><span><i className="fa-solid fa-signal" /> <i className="fa-solid fa-wifi" /> <i className="fa-solid fa-battery-three-quarters" /></span></div>
                    <div className="pi-mockup-header" style={{ background: item.headerBg }}>
                      <i className={['fa-solid fa-book-open', 'fa-solid fa-pen', 'fa-solid fa-comments', 'fa-solid fa-chart-simple'][i]} style={{ marginRight: 6 }} />
                      {['课程学习', '智能练习', '互动课堂', '学情报告'][i]}
                    </div>
                    <div className="pi-mockup-body">{i === 0 && (<><div className="pi-mock-line pi-wide" /><div className="pi-mock-row"><div className="pi-mock-thumb" style={{ background: 'rgba(91,158,111,0.15)' }} /><div className="pi-mock-thumb" style={{ background: 'rgba(91,158,111,0.15)' }} /></div><div className="pi-mock-block" style={{ background: 'rgba(91,158,111,0.1)' }} /><div className="pi-mock-progress" /><div className="pi-mock-line pi-medium" /><div className="pi-mock-line pi-narrow" /></>)}
                    {i === 1 && (<><div className="pi-mock-line pi-wide" /><div className="pi-mock-block" style={{ background: 'rgba(74,128,208,0.1)', height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><span style={{ color: 'rgba(255,255,255,0.2)', fontSize: 20, fontFamily: 'serif' }}>?</span></div><div className="pi-mock-line pi-medium" /><div className="pi-mock-row"><div style={{ flex: 1, padding: '6px 8px', background: 'rgba(74,128,208,0.12)', borderRadius: 6, textAlign: 'center' }}><span style={{ color: 'rgba(255,255,255,0.2)', fontSize: 11 }}>A</span></div><div style={{ flex: 1, padding: '6px 8px', background: 'rgba(74,128,208,0.12)', borderRadius: 6, textAlign: 'center' }}><span style={{ color: 'rgba(255,255,255,0.2)', fontSize: 11 }}>B</span></div></div><div className="pi-mock-row"><div style={{ flex: 1, padding: '6px 8px', background: 'rgba(74,128,208,0.12)', borderRadius: 6, textAlign: 'center' }}><span style={{ color: 'rgba(255,255,255,0.2)', fontSize: 11 }}>C</span></div><div style={{ flex: 1, padding: '6px 8px', background: 'rgba(74,128,208,0.12)', borderRadius: 6, textAlign: 'center' }}><span style={{ color: 'rgba(255,255,255,0.2)', fontSize: 11 }}>D</span></div></div></>)}
                    {i === 2 && (<><div className="pi-mock-block" style={{ background: 'rgba(208,160,74,0.1)', height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 4 }}><i className="fa-solid fa-play" style={{ color: 'rgba(255,255,255,0.15)', fontSize: 28 }} /><span style={{ color: 'rgba(255,255,255,0.15)', fontSize: 10 }}>直播中</span></div><div className="pi-mock-line pi-wide" /><div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>{['😊','👍','🔥','💡'].map((e,j)=><span key={j} style={{ fontSize: 12, opacity: 0.15 }}>{e}</span>)}</div></>)}
                    {i === 3 && (<><div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}><span style={{ color: 'rgba(255,255,255,0.15)', fontSize: 10 }}>本周</span><span style={{ color: 'rgba(74,157,157,0.4)', fontSize: 10 }}>+12%</span></div><div className="pi-mock-block" style={{ background: 'rgba(74,157,157,0.1)', height: 50 }} /><div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>{['一','二','三','四','五'].map((d,j)=><div key={j} style={{ width: 20, height: 20, borderRadius: 4, background: j === 3 ? 'rgba(74,157,157,0.25)' : 'rgba(255,255,255,0.05)' }} />)}</div><div className="pi-mock-line pi-medium" /><div className="pi-mock-line pi-narrow" /></>)}
                    </div>
                  </div>
                  <p className="pi-prototype-title">{item.title}</p>
                  <p className="pi-prototype-desc">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 教师端功能 */}
      <section className="pi-section">
        <div className="pi-section-content">
          <div ref={setRevealRef} className="pi-reveal pi-feature-header">
            <h2><i className="fa-solid fa-chalkboard-user" /> 教师端功能</h2>
            <p>强大高效的智慧教学工具，让教学管理轻而易举</p>
          </div>
          <div className="pi-prototype-grid">
            {[
              { delay: 1, theme: 'pi-theme-green', title: 'AI PPT 课件生成', desc: '输入主题，AI 自动生成精美课件', headerBg: 'rgba(91,158,111,0.2)' },
              { delay: 2, theme: 'pi-theme-blue', title: '智能组卷阅卷', desc: 'AI 出题 + 自动批改 + 成绩分析', headerBg: 'rgba(74,128,208,0.2)' },
              { delay: 3, theme: 'pi-theme-teal', title: '课堂实时互动', desc: '投票、测验、弹幕 — 掌控课堂节奏', headerBg: 'rgba(74,157,157,0.2)' },
              { delay: 4, theme: 'pi-theme-amber', title: '学情数据看板', desc: '全班学情一目了然，精准定位薄弱点', headerBg: 'rgba(208,160,74,0.2)' },
            ].map((item, i) => (
              <div key={i} ref={setRevealRef} className={`pi-reveal pi-delay-${item.delay}`}>
                <div className="pi-prototype-card">
                  <div className={`pi-mockup-phone ${item.theme}`}>
                    <div className="pi-mockup-status"><span>9:41</span><span><i className="fa-solid fa-signal" /> <i className="fa-solid fa-wifi" /> <i className="fa-solid fa-battery-three-quarters" /></span></div>
                    <div className="pi-mockup-header" style={{ background: item.headerBg }}>
                      <i className={['fa-solid fa-file-powerpoint','fa-solid fa-file-pen','fa-solid fa-presentation-screen','fa-solid fa-chart-pie'][i]} style={{ marginRight: 6 }} />
                      {['AI 备课','智能阅卷','互动课堂','数据看板'][i]}
                    </div>
                    <div className="pi-mockup-body">{i === 0 && (<><div className="pi-mock-line pi-wide" /><div className="pi-mock-block" style={{ background: 'rgba(91,158,111,0.08)', height: 80 }} /><div style={{ display: 'flex', gap: 6 }}>{['封面','目录','正文','总结'].map((t,j)=><span key={j} style={{ padding: '4px 8px', borderRadius: 4, fontSize: 9, background: j===0?'rgba(91,158,111,0.2)':'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.3)' }}>{t}</span>)}</div><div className="pi-mock-line pi-medium" /><div className="pi-mock-line pi-narrow" /></>)}
                    {i === 1 && (<><div className="pi-mock-block" style={{ background: 'rgba(74,128,208,0.08)', height: 60 }}><div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}><span style={{ color: 'rgba(74,128,208,0.3)', fontSize: 22, fontWeight: 700 }}>92</span><span style={{ color: 'rgba(255,255,255,0.15)', fontSize: 10, marginLeft: 4 }}>/100</span></div></div><div className="pi-mock-line pi-wide" /><div className="pi-mock-line pi-medium" /><div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ color: 'rgba(255,255,255,0.1)', fontSize: 9 }}>客观题 ✓</span><span style={{ color: 'rgba(255,255,255,0.1)', fontSize: 9 }}>主观题 待批</span></div><div className="pi-mock-progress" style={{ width: '90%' }} /></>)}
                    {i === 2 && (<><div className="pi-mock-block" style={{ background: 'rgba(74,157,157,0.08)', height: 70, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}><i className="fa-solid fa-chart-simple" style={{ color: 'rgba(74,157,157,0.2)', fontSize: 24 }} /></div><div className="pi-mock-row"><div className="pi-mock-thumb" style={{ background: 'rgba(74,157,157,0.1)' }} /><div className="pi-mock-thumb" style={{ background: 'rgba(74,157,157,0.1)' }} /><div className="pi-mock-thumb" style={{ background: 'rgba(74,157,157,0.1)' }} /></div><div className="pi-mock-line pi-wide" /><div className="pi-mock-line pi-medium" /><div style={{ textAlign: 'center' }}><span style={{ color: 'rgba(255,255,255,0.08)', fontSize: 11 }}>📊 参与率 87%</span></div></>)}
                    {i === 3 && (<><div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}><span style={{ color: 'rgba(255,255,255,0.1)', fontSize: 9 }}>班级平均分</span><span style={{ color: 'rgba(208,160,74,0.4)', fontSize: 10, fontWeight: 600 }}>78.5</span></div><div className="pi-mock-row"><div className="pi-mock-thumb" style={{ background: 'rgba(208,160,74,0.1)', height: 60 }} /><div className="pi-mock-thumb" style={{ background: 'rgba(208,160,74,0.06)', height: 40 }} /><div className="pi-mock-thumb" style={{ background: 'rgba(208,160,74,0.08)', height: 50 }} /></div><div className="pi-mock-line pi-wide" /><div className="pi-mock-dot-grid">{Array.from({length:9}).map((_,j)=><div key={j} className="pi-mock-dot" style={{ background: j<5?'rgba(208,160,74,0.1)':'rgba(255,255,255,0.04)' }} />)}</div></>)}
                    </div>
                  </div>
                  <p className="pi-prototype-title">{item.title}</p>
                  <p className="pi-prototype-desc">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 结束语 */}
      <section className="pi-closing-section">
        <div ref={setRevealRef} className="pi-reveal">
          <h2 className="pi-closing-title">开启 <span className="pi-green">智慧教育</span> 之旅</h2>
          <p className="pi-closing-text">无论您是学校管理者、一线教师还是学生，<br />E-Learning 都将为您带来前所未有的教学体验。</p>
          <div className="pi-closing-cta">
            <button onClick={() => navigate(-1)}>
              <i className="fa-solid fa-arrow-left" style={{ marginRight: 8 }} />
              返回平台
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
