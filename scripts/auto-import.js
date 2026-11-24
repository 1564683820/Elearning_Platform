#!/usr/bin/env node
'use strict';

/**
 * 自动导入：读取 SQLite 数据，通过云函数分批导入到 MySQL
 * 生成可供 MCP 调用的输出
 * 
 * 用法:
 *   node auto-import.js --phase phase1 --info          # 查看批次信息
 *   node auto-import.js --phase phase1 --batch 0       # 输出第0批的JSON数据
 */

const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');

const DB_PATH = path.join(__dirname, 'ecdict-data', 'stardict.db');

const PHASE_QUERIES = {
  phase1: { name: 'BNC前2000', where: "bnc != '' AND CAST(bnc AS INTEGER) > 0 AND CAST(bnc AS INTEGER) <= 2000", orderBy: 'CAST(bnc AS INTEGER) ASC' },
  phase2: { name: 'Collins5', where: "collins = 5", orderBy: 'word ASC' },
  phase3: { name: 'CET4', where: "tag LIKE '%cet4%'", orderBy: 'word ASC' },
  phase4: { name: 'CET6', where: "tag LIKE '%cet6%'", orderBy: 'word ASC' },
  phase5: { name: 'IELTS', where: "tag LIKE '%ielts%'", orderBy: 'word ASC' },
  phase6: { name: '高考', where: "tag LIKE '%gk%'", orderBy: 'word ASC' },
  phase7: { name: 'Collins3-4', where: "collins IN (3, 4)", orderBy: 'word ASC' },
};

function generateSW(word) {
  return (word || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
}

function main() {
  const args = process.argv.slice(2);
  let phase = 'phase1';
  let batchIdx = -1;
  let batchSize = 5;
  let infoOnly = false;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--phase' && args[i + 1]) { phase = args[i + 1]; i++; }
    else if (args[i] === '--batch' && args[i + 1]) { batchIdx = parseInt(args[i + 1], 10); i++; }
    else if (args[i] === '--batch-size' && args[i + 1]) { batchSize = parseInt(args[i + 1], 10); i++; }
    else if (args[i] === '--info') { infoOnly = true; }
  }

  if (!PHASE_QUERIES[phase]) {
    console.error(JSON.stringify({ error: `Unknown phase: ${phase}` }));
    process.exit(1);
  }

  const phaseConfig = PHASE_QUERIES[phase];

  if (!fs.existsSync(DB_PATH)) {
    console.error(JSON.stringify({ error: `SQLite DB not found` }));
    process.exit(1);
  }

  const db = new Database(DB_PATH, { readonly: true });
  const sql = `SELECT word, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange FROM stardict WHERE ${phaseConfig.where} ORDER BY ${phaseConfig.orderBy}`;
  const rows = db.prepare(sql).all();
  db.close();

  const totalBatches = Math.ceil(rows.length / batchSize);

  if (infoOnly) {
    console.log(JSON.stringify({ phase, totalRecords: rows.length, batchSize, totalBatches }));
    return;
  }

  if (batchIdx < 0 || batchIdx >= totalBatches) {
    console.error(JSON.stringify({ error: `batch ${batchIdx} out of range [0, ${totalBatches})` }));
    process.exit(1);
  }

  const start = batchIdx * batchSize;
  const batch = rows.slice(start, start + batchSize);

  const importRows = batch.map(r => ({
    word: (r.word || '').substring(0, 128),
    sw: generateSW(r.word),
    phonetic: (r.phonetic || '').substring(0, 128),
    definition: r.definition || '',
    translation: r.translation || '',
    pos: (r.pos || '').substring(0, 64),
    collins: parseInt(r.collins) || 0,
    oxford: parseInt(r.oxford) || 0,
    tag: (r.tag || '').substring(0, 128),
    bnc: parseFloat(r.bnc) || 0,
    frq: parseFloat(r.frq) || 0,
    exchange: r.exchange || '',
  }));

  // 直接输出 JSON，用于 MCP invokeFunction 的 params 参数
  process.stdout.write(JSON.stringify({ action: 'import', rows: importRows }));
}

main();
