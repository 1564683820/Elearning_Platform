export async function* readEventStream(response: Response) {
  if (!response.ok) {
    const error: { detail?: unknown } = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : `请求失败（${response.status}）`);
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error('无法读取响应流');

  const decoder = new TextDecoder();
  let buffer = '';
  let name = '';
  let lines: string[] = [];
  try {
    for (;;) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() + '\n\n' : decoder.decode(value, { stream: true });
      let end = buffer.indexOf('\n');
      while (end !== -1) {
        const line = buffer.slice(0, end).replace(/\r$/, '');
        buffer = buffer.slice(end + 1);
        if (!line) {
          if (lines.length) yield { name, data: lines.join('\n') };
          lines = [];
          name = '';
        } else if (line.startsWith('event:')) {
          name = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          lines.push(line.slice(5).replace(/^ /, ''));
        }
        end = buffer.indexOf('\n');
      }
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
