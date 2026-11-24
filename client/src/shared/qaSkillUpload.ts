import { useRef, useState } from 'react';
import { teachingAssistantApi } from '../api/teachingAssistant';

export const SKILL_FILE_ACCEPT = '.md,.markdown';
const MAX_QA_SKILL_BYTES = 48 * 1024;

function checkFile(file?: File) {
  if (!file) return '';
  if (!/\.(?:md|markdown)$/i.test(file.name)) return '文件格式不支持。请选择 .md 或 .markdown。';
  if (!file.size) return '文件内容为空';
  if (file.size > MAX_QA_SKILL_BYTES) return 'Skill 文件不能超过 48 KB';
  return '';
}

export function useQASkillUpload() {
  const [file, setFile] = useState<File>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const invalid = checkFile(file);

  function select(next?: File) {
    if (pending.current) return;
    setFile(next);
    setError('');
  }

  async function submit() {
    if (!file || invalid || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      const saved = await teachingAssistantApi.uploadSkill(file, 'qa');
      setFile(undefined);
      return saved;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : '上传失败，请重试');
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return { file, select, submit, busy, invalid, error: invalid || error };
}
