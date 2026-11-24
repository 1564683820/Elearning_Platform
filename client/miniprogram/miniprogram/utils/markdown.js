/**
 * Markdown 转 HTML 工具 — 用于小程序 rich-text 渲染
 * 支持：标题 / 粗体 / 斜体 / 行内代码 / 代码块 / 无序列表 / 有序列表 / 分隔线 / 链接
 * 注意：Markdown 表格会转为非表格格式（键值对列表），避免长单词显示问题
 */

// 转义 HTML 特殊字符，防止 XSS
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * 将 Markdown 文本转换为 HTML 字符串（兼容微信 rich-text nodes 属性）
 * @param {string} md - 原始 Markdown 文本
 * @returns {string} - 转换后的 HTML 字符串
 */
function markdownToHtml(md) {
  if (!md) return '';

  // ---------- 第 1 步：提取并保护代码块 ----------
  const codeBlocks = [];
  let processed = md.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push({ lang, code: code.replace(/\n$/, '') });
    return `\x00CODEBLOCK_${idx}\x00`;
  });

  // ---------- 第 2 步：转义 HTML ----------
  processed = escapeHtml(processed);

  // ---------- 第 3 步：行内样式 ----------
  // 粗体 **text**
  processed = processed.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // 斜体 *text*（非粗体部分）
  processed = processed.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // 行内代码 `code`
  processed = processed.replace(/`([^`]+)`/g, '<code>$1</code>');
  // 链接 [text](url)
  processed = processed.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

  // ---------- 第 4 步：分行处理块级元素 ----------
  const lines = processed.split('\n');
  const out = [];
  let inUl = false;
  let inOl = false;
  let orderedListCounter = 1;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // ---- 分隔线 ----
    if (/^[-*_]{3,}$/.test(trimmed)) {
      closeOpenList(out, inUl, inOl);
      inUl = false; inOl = false;
      out.push('<hr />');
      continue;
    }

    // ---- 标题 ----
    const hMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (hMatch) {
      closeOpenList(out, inUl, inOl);
      inUl = false; inOl = false;
      const level = hMatch[1].length;
      out.push(`<h${level}>${hMatch[2]}</h${level}>`);
      continue;
    }

    // ---- 空行 ----
    if (trimmed === '') {
      closeOpenList(out, inUl, inOl);
      inUl = false; inOl = false;
      continue;
    }

    // ---- 无序列表 ----
    const ulMatch = trimmed.match(/^[-*+]\s+(.+)$/);
    if (ulMatch) {
      if (!inUl) {
        if (inOl) { out.push('</ol>'); inOl = false; }
        out.push('<ul>');
        inUl = true;
      }
      out.push(`<li>${ulMatch[1]}</li>`);
      continue;
    }

    // ---- 有序列表 ----
    const olMatch = trimmed.match(/^(\d+)\.\s+(.+)$/);
    if (olMatch) {
      if (!inOl) {
        if (inUl) { out.push('</ul>'); inUl = false; }
        out.push('<ol>');
        inOl = true;
        orderedListCounter = 1;
      }
      out.push(`<li>${olMatch[2]}</li>`);
      continue;
    }

    // ---- 表格转为键值对列表（避免 table 在 rich-text 中的长单词显示问题）----
    if (/^\|.+\|$/.test(trimmed)) {
      closeOpenList(out, inUl, inOl);
      inUl = false; inOl = false;
      // 收集连续的所有表格行
      const tableLines = [];
      while (i < lines.length && /^\|.+\|$/.test(lines[i].trim())) {
        const raw = lines[i];
        // 判断是否是分隔行（|---|---|），跳过
        if (!/^\|[-:\s|]+\|$/.test(raw.trim())) {
          tableLines.push(raw.trim());
        }
        i++;
      }
      i--; // for 循环会自增
      // tableLines[0] = 表头行, tableLines[1..] = 数据行
      if (tableLines.length > 0) {
        const headerCells = parseTableRow(tableLines[0]);
        // 对每条数据行，生成键值对列表
        for (let ri = 1; ri < tableLines.length; ri++) {
          const cells = parseTableRow(tableLines[ri]);
          out.push('<div class="table-row">');
          cells.forEach((cell, ci) => {
            const label = headerCells[ci] ? headerCells[ci].trim() : '';
            if (label) {
              out.push(`<div class="kv-item"><span class="kv-label">${label}：</span><span class="kv-value">${cell.trim()}</span></div>`);
            } else {
              out.push(`<div class="kv-item">${cell.trim()}</div>`);
            }
          });
          out.push('</div>');
        }
      }
      continue;
    }

    // ---- 普通段落 ----
    closeOpenList(out, inUl, inOl);
    inUl = false; inOl = false;
    out.push(`<p>${line}</p>`);
  }

  // 关闭最后可能未关闭的列表
  closeOpenList(out, inUl, inOl);

  // ---------- 第 5 步：恢复代码块 ----------
  let html = out.join('\n');
  html = html.replace(/\x00CODEBLOCK_(\d+)\x00/g, (_, idx) => {
    const block = codeBlocks[parseInt(idx)];
    const langClass = block.lang ? ` class="lang-${block.lang}"` : '';
    return `<pre><code${langClass}>${block.code}</code></pre>`;
  });

  return html;
}

// 解析表格行，按 | 分割单元格
function parseTableRow(row) {
  // 去掉首尾的 |
  const inner = row.replace(/^\|/, '').replace(/\|$/, '');
  return inner.split('|');
}

function closeOpenList(out, inUl, inOl) {
  if (inUl) out.push('</ul>');
  if (inOl) out.push('</ol>');
}

/**
 * 带换行保留的 markdown 转 HTML（适用于打字机效果中的部分文本）
 * 与 markdownToHtml 相同，仅作别名以便语义区分
 */
function markdownToHtmlPartial(md) {
  return markdownToHtml(md);
}

module.exports = { markdownToHtml, markdownToHtmlPartial };
