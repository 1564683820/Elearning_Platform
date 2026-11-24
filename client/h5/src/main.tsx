import { createRoot } from 'react-dom/client';
import { useEffect, useState, type FormEvent } from 'react';
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import client, { loginReturnPath } from '../../src/api/client';
import { getProfile } from '../../src/api/user';
import { clearTeacherChatDrafts } from '../../src/shared/ChatAttachments';
import { clearTeacherPaperCreations } from '../../src/shared/exams/paperCreationRecovery';
import { Home } from './Home';
import { Exams } from './Exams';
import { Icon, Sheet, errorText } from './ui';
import './styles.css';

interface Teacher {
  username?: string;
  account?: string;
  nickname?: string | null;
  email?: string | null;
  role: string;
}

const accountHintKey = 'elearning:h5:account-hint';

function savedTeacher(): Teacher | null {
  try {
    const user: Teacher | null = JSON.parse(localStorage.getItem('user') ?? 'null');
    return user?.role === 'teacher' && localStorage.getItem('token') ? user : null;
  } catch {
    return null;
  }
}

function Login({ loggedIn }: { loggedIn: (teacher: Teacher) => void }) {
  const navigate = useNavigate();
  const { search } = useLocation();
  const expired = new URLSearchParams(search).get('expired') === '1';
  const next = loginReturnPath('teacher');
  const resumeReview = expired && /^\/exams\/[^/]+\/scan\/reviews\/[^/?#]+(?:[?#]|$)/.test(next ?? '');
  const [account, setAccount] = useState(() => expired ? sessionStorage.getItem(accountHintKey) ?? '' : '');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const { data } = await client.post<{ data: { token: string; user: Teacher } }>('/auth/teacher/login', { account: account.trim(), password });
      const { token, user } = data.data;
      if (!token || user?.role !== 'teacher') throw new Error('请使用教师账号登录');
      localStorage.setItem('token', token);
      localStorage.setItem('user', JSON.stringify(user));
      loggedIn(user);
      navigate(loginReturnPath(user.role) ?? '/', { replace: true });
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  return <form className={expired ? 'login login-expired' : 'login'} onSubmit={submit}>
    {expired ? <>
      <h1>请重新登录</h1>
      <div className="login-expired-notice" role="status"><Icon name="warning" size={19} />会话已过期</div>
    </> : <div className="brand"><span><Icon name="scan" /></span>Elearning</div>}
    <label htmlFor="account">账号</label>
    <div className="field"><Icon name="user" size={18} /><input id="account" autoComplete="username" placeholder="请输入教师账号" value={account} onChange={event => setAccount(event.target.value)} required /></div>
    <label htmlFor="password">密码</label>
    <div className={`field ${error ? 'invalid' : ''}`}><Icon name="lock" size={18} /><input id="password" autoComplete="current-password" type={visible ? 'text' : 'password'} placeholder="请输入密码" value={password} onChange={event => setPassword(event.target.value)} aria-invalid={Boolean(error)} aria-describedby={error ? 'login-error' : undefined} required /><button type="button" className="plain" aria-label={visible ? '隐藏密码' : '显示密码'} onClick={() => setVisible(!visible)}><Icon name="eye" size={18} /></button></div>
    <div id="login-error" className="login-error" aria-live="polite">{error}</div>
    <button className="primary wide" disabled={busy}>{busy ? '登录中…' : expired ? '登录并继续' : '登录'}</button>
    {resumeReview && <p className="login-resume-note">登录后会核对成绩提交状态。</p>}
  </form>;
}

function Profile({ teacher, logout }: { teacher: Teacher; logout: () => void }) {
  const [confirm, setConfirm] = useState(false);
  const [profile, setProfile] = useState<Teacher>(teacher);
  useEffect(() => {
    let live = true;
    void getProfile().then(user => { if (live) setProfile(user); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  const name = profile.nickname || profile.username || profile.account || '教师';
  const email = profile.email?.replace(/^(.{1,2})[^@]*(@.+)$/, '$1***$2');
  return <main className="page profile">
    <header className="heading"><h1>我的</h1></header>
    <div className="identity"><span className="avatar">{name.slice(0, 1)}</span><div><strong>{name}</strong><small>{profile.account || profile.username}</small></div></div>
    <div className="details">
      <div><Icon name="shield" /><span>身份</span><strong>教师</strong></div>
      <div><Icon name="mail" /><span>邮箱</span><strong>{email || '未设置'}</strong></div>
    </div>
    <button className="secondary wide signout" onClick={() => setConfirm(true)}>退出登录</button>
    {confirm && <Sheet title="退出当前账号？" variant="logout" close={() => setConfirm(false)}><div className="actions"><button className="secondary" onClick={() => setConfirm(false)}>取消</button><button className="danger" onClick={logout}>退出登录</button></div></Sheet>}
  </main>;
}

function App() {
  const [teacher, setTeacher] = useState(savedTeacher);
  const navigate = useNavigate();
  const { pathname } = useLocation();
  useEffect(() => {
    if (!teacher) return;
    const account = teacher.account || teacher.username;
    if (account) sessionStorage.setItem(accountHintKey, account);
    else sessionStorage.removeItem(accountHintKey);
  }, [teacher]);
  const logout = () => {
    clearTeacherChatDrafts();
    clearTeacherPaperCreations();
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    sessionStorage.removeItem(accountHintKey);
    setTeacher(null);
    navigate('/login', { replace: true });
  };

  if (!teacher) return <div className="phone"><Routes><Route path="/login" element={<Login loggedIn={setTeacher} />} /><Route path="*" element={<Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />} /></Routes></div>;

  return <div className="phone">
    <Routes>
      <Route path="/me" element={<Profile teacher={teacher} logout={logout} />} />
      <Route path="/exams/*" element={<Exams />} />
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="/*" element={<Home />} />
    </Routes>
    {['/', '/exams', '/me'].includes(pathname) && <nav className="tabs" data-active={pathname === '/exams' ? 'exams' : pathname === '/me' ? 'me' : 'home'} aria-label="主导航">
      <NavLink to="/" end><Icon name="home" size={21} />首页</NavLink>
      <NavLink to="/exams"><Icon name="files" size={21} />试卷</NavLink>
      <NavLink to="/me"><Icon name="user" size={21} />我的</NavLink>
    </nav>}
  </div>;
}

createRoot(document.getElementById('root')!).render(<BrowserRouter basename={import.meta.env.BASE_URL}><App /></BrowserRouter>);
