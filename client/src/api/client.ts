// Axios 封装 — 统一请求配置、Token 注入、错误处理
import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';

const client = axios.create({
  baseURL: '/Elearning/api/v1',
  timeout: 300000, // AI 生成试卷/PPT/知识图谱等操作较慢，设 5 分钟超时
  headers: { 'Content-Type': 'application/json' },
});

const basePath = import.meta.env.BASE_URL.replace(/\/$/, '');
const loginPath = `${basePath}/login`;

export function loginLink(expired = false): string {
  const params = new URLSearchParams({ next: location.pathname + location.search + location.hash });
  if (expired) params.set('expired', '1');
  return `/login?${params}`;
}

export function loginReturnPath(role: string): string | null {
  const next = new URLSearchParams(location.search).get('next');
  if (!next || !next.startsWith(`${basePath}/`)) return null;
  const target = new URL(next, location.origin);
  if (target.origin !== location.origin || !target.pathname.startsWith(`${basePath}/`)) return null;
  const path = target.pathname.slice(basePath.length);
  if (path === '/login' || path.startsWith('/login/')) return null;
  const adminPath = path === '/admin' || path.startsWith('/admin/');
  if (adminPath !== (role === 'admin')) return null;
  return path + target.search + target.hash;
}

export function handleSessionRejection(status: number, authorization: unknown) {
  if (status !== 401) return;
  const token = localStorage.getItem('token');
  // An older request must not clear a session established after it was sent.
  if (!token || authorization !== `Bearer ${token}`) return;
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  if (location.pathname !== loginPath) location.replace(basePath + loginLink(true));
}

export async function authenticatedFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem('token');
  const headers = new Headers(options.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(url, { ...options, headers });
  handleSessionRejection(response.status, headers.get('Authorization'));
  return response;
}

// 请求拦截：注入 JWT Token
client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('token');
  const isLogin = /^\/auth\/(?:teacher\/login|admin\/login|register)$/.test(config.url || '');
  if (!isLogin && token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截：统一处理错误
client.interceptors.response.use(
  (res) => res,
  (error: AxiosError<Record<string, unknown>>) => {
    if (error.response?.status === 401) {
      handleSessionRejection(401, error.config?.headers.get('Authorization'));
    }
    // FastAPI 返回的 detail 字段，兼容其他 message 字段
    const respData = error.response?.data as Record<string, unknown> | undefined;
    const detail = respData?.detail;
    let message = typeof detail === 'string' ? detail : '';
    if (Array.isArray(detail)) {
      message = detail.map((item: unknown) => {
        if (!item || typeof item !== 'object') return '';
        const validation = item as { loc?: unknown; msg?: unknown };
        if (typeof validation.msg !== 'string') return '';
        const location = Array.isArray(validation.loc)
          ? validation.loc.filter(part => typeof part === 'string' || typeof part === 'number').join('.')
          : '';
        return location ? `${location}: ${validation.msg}` : validation.msg;
      }).filter(Boolean).join('；');
    }
    if (!message && typeof respData?.message === 'string') message = respData.message;
    // 保留 status、response、code 和取消标记，调用方才能区分权限、校验和断网。
    error.message = message || error.message || '请求失败';
    return Promise.reject(error);
  }
);

// 获取 axios 实例的 base URL（供 SSE fetch 直接使用）
export function getBaseURL(): string {
  return client.defaults.baseURL || '';
}

export default client;
