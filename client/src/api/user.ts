// 用户 API — 资料读写
import client from './client';

export interface UserProfile {
  id: number;
  username: string;
  account: string;
  nickname: string | null;
  avatar_url: string | null;
  email: string | null;
  role: string;
  stage: number | null;
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await client.put('/auth/password', { old_password: oldPassword, new_password: newPassword });
}

export async function getProfile(): Promise<UserProfile> {
  const res = await client.get('/auth/profile');
  return res.data?.data ?? res.data;
}

export async function updateProfile(data: {
  nickname?: string;
  avatar_url?: string | null;
}): Promise<UserProfile> {
  const res = await client.put('/auth/profile', data);
  return res.data?.data ?? res.data;
}
