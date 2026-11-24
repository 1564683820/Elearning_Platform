export function teacherSessionPrefix(scope: string): string | undefined {
  try {
    if (!localStorage.getItem('token')) return undefined;
    const user = JSON.parse(localStorage.getItem('user') ?? 'null');
    if (user?.role !== 'teacher') return undefined;
    const owner = user.id ?? user.account ?? user.username;
    if (typeof owner === 'string' || typeof owner === 'number') {
      return `elearning:${scope}:${encodeURIComponent(String(owner))}:`;
    }
  } catch { /* Browser storage may be unavailable. */ }
  return undefined;
}
