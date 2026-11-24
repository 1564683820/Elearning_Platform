#!/usr/bin/env node
'use strict';

/**
 * 自动导入脚本：从 SQLite 读取数据，生成 JSON 批次，输出到 stdout 供 MCP 调用
 * 
 * 用法: 
 *   node import-batch.js --phase phase1 --batch-index 0
 *   输出 JSON 格式的 rows 数组，可直接传给云函数
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
  let batchIndex = -1; // -1 means output all batch info
  let batchSize = 20;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--phase' && args[i + 1]) { phase = args[i + 1]; i++; }
    else if (args[i] === '--batch-index' && args[i + 1]) { batchIndex = parseInt(args[i + 1], 10); i++; }
    else if (args[i] === '--batch-size' && args[i + 1]) { batchSize = parseInt(args[i + 1], 10); i++; }
  }

  if (!PHASE_QUERIES[phase]) {
    console.error(JSON.stringify({ error: `Unknown phase: ${phase}` }));
    process.exit(1);
  }

  const phaseConfig = PHASE_QUERIES[phase];

  if (!fs.existsSync(DB_PATH)) {
    console.error(JSON.stringify({ error: `SQLite DB not found: ${DB_PATH}` }));
    process.exit(1);
  }

  const db = new Database(DB_PATH, { readonly: true });
  const sql = `SELECT word, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange FROM stardict WHERE ${phaseConfig.where} ORDER BY ${phaseConfig.orderBy}`;
  const rows = db.prepare(sql).all();
  db.close();

  const totalBatches = Math.ceil(rows.length / batchSize);

  // 如果没有指定 batch-index，输出批次信息
  if (batchIndex === -1) {
    console.log(JSON.stringify({ phase, totalRecords: rows.length, batchSize, totalBatches }));
    return;
  }

  if (batchIndex < 0 || batchIndex >= totalBatches) {
    console.error(JSON.stringify({ error: `batch-index ${batchIndex} out of range [0, ${totalBatches})` }));
    process.exit(1);
  }

  // 获取指定批次
  const start = batchIndex * batchSize;
  const batch = rows.slice(start, start + batchSize);

  const importRows = batch.map(row => ({
    word: (row.word || '').substring(0, 128),
    sw: generateSW(row.word),
    phonetic: (row.phonetic || '').substring(0, 128),
    definition: row.definition || '',
    translation: row.translation || '',
    pos: (row.pos || '').substring(0, 64),
    collins: parseInt(row.collins, 10) || 0,
    oxford: parseInt(row.oxford, 10) || 0,
    tag: (row.tag || '').substring(0, 128),
    bnc: parseFloat(row.bnc) || 0,
    frq: parseFloat(row.frq) || 0,
    exchange: row.exchange || '',
  }));

  // 输出 JSON
  console.log(JSON.stringify(importRows));
}

main();
