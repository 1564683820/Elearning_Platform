#!/usr/bin/env node
'use strict';

/**
 * 生成各阶段的完整 JSON 数据文件，上传到 CloudBase 静态托管后由云函数读取导入
 */

const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');

const DB_PATH = path.join(__dirname, 'ecdict-data', 'stardict.db');
const OUTPUT_DIR = path.join(__dirname, 'import-data');

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
  const phase = process.argv[2] || 'phase1';
  
  if (!PHASE_QUERIES[phase]) {
    console.error(`Unknown phase: ${phase}. Available: ${Object.keys(PHASE_QUERIES).join(', ')}`);
    process.exit(1);
  }

  const phaseConfig = PHASE_QUERIES[phase];

  if (!fs.existsSync(DB_PATH)) {
    console.error(`SQLite DB not found: ${DB_PATH}`);
    process.exit(1);
  }

  const db = new Database(DB_PATH, { readonly: true });
  const sql = `SELECT word, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange FROM stardict WHERE ${phaseConfig.where} ORDER BY ${phaseConfig.orderBy}`;
  const rows = db.prepare(sql).all();
  db.close();

  const importRows = rows.map(r => ({
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

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const outputPath = path.join(OUTPUT_DIR, `${phase}.json`);
  fs.writeFileSync(outputPath, JSON.stringify(importRows));
  
  const sizeKB = (fs.statSync(outputPath).size / 1024).toFixed(1);
  console.log(`${phase} (${phaseConfig.name}): ${importRows.length} records, ${sizeKB} KB`);
  console.log(`Output: ${outputPath}`);
}

main();
