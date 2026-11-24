#!/usr/bin/env node
'use strict';

/**
 * 从 JSON 批次文件生成 MCP 可执行的 SQL 语句
 * 输出格式：每行一条 INSERT SQL，可直接通过 MCP executeWriteSQL 执行
 * 
 * 用法: node gen-insert-sql.js [--phase phase1] [--batch-size 10] [--limit N]
 */

const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');

const DB_PATH = path.join(__dirname, 'ecdict-data', 'stardict.db');
const OUTPUT_DIR = path.join(__dirname, 'sql-insert-batches');

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

function escapeSql(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/\0/g, '\\0')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r')
    .replace(/\t/g, '\\t');
}

function main() {
  const args = process.argv.slice(2);
  let phase = 'phase1';
  let batchSize = 10;
  let limitOverride = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--phase' && args[i + 1]) { phase = args[i + 1]; i++; }
    else if (args[i] === '--batch-size' && args[i + 1]) { batchSize = parseInt(args[i + 1], 10); i++; }
    else if (args[i] === '--limit' && args[i + 1]) { limitOverride = parseInt(args[i + 1], 10); i++; }
  }

  if (!PHASE_QUERIES[phase]) {
    console.error(`Unknown phase: ${phase}`);
    process.exit(1);
  }

  const phaseConfig = PHASE_QUERIES[phase];
  const phaseDir = path.join(OUTPUT_DIR, phase);
  fs.mkdirSync(phaseDir, { recursive: true });

  if (!fs.existsSync(DB_PATH)) {
    console.error(`SQLite DB not found: ${DB_PATH}`);
    process.exit(1);
  }

  const db = new Database(DB_PATH, { readonly: true });
  let sql = `SELECT word, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange FROM stardict WHERE ${phaseConfig.where} ORDER BY ${phaseConfig.orderBy}`;
  if (limitOverride) sql += ` LIMIT ${limitOverride}`;

  const rows = db.prepare(sql).all();
  db.close();
  console.log(`Phase ${phase}: ${rows.length} records, batch size ${batchSize}`);

  let batchIndex = 0;
  for (let i = 0; i < rows.length; i += batchSize) {
    const batch = rows.slice(i, i + batchSize);
    const values = batch.map(r => {
      const word = escapeSql(r.word);
      const sw = escapeSql(generateSW(r.word));
      const phonetic = escapeSql(r.phonetic);
      const definition = escapeSql(r.definition);
      const translation = escapeSql(r.translation);
      const pos = escapeSql(r.pos);
      const collins = parseInt(r.collins) || 0;
      const oxford = parseInt(r.oxford) || 0;
      const tag = escapeSql(r.tag);
      const bnc = parseFloat(r.bnc) || 0;
      const frq = parseFloat(r.frq) || 0;
      const exchange = escapeSql(r.exchange);
      return `('${word}','${sw}','${phonetic}','${definition}','${translation}','${pos}',${collins},${oxford},'${tag}',${bnc},${frq},'${exchange}','')`;
    });

    const insertSql = `INSERT INTO dict_word (word,sw,phonetic,definition,translation,pos,collins,oxford,tag,bnc,frq,exchange,audio_url) VALUES ${values.join(',')};`;
    
    const fileName = `batch_${String(batchIndex).padStart(4, '0')}.sql`;
    fs.writeFileSync(path.join(phaseDir, fileName), insertSql, 'utf-8');
    batchIndex++;
  }

  console.log(`Generated ${batchIndex} SQL batch files in ${phaseDir}`);
  
  // 输出统计信息
  const totalSize = fs.readdirSync(phaseDir)
    .filter(f => f.endsWith('.sql'))
    .reduce((sum, f) => sum + fs.statSync(path.join(phaseDir, f)).size, 0);
  console.log(`Total size: ${(totalSize / 1024).toFixed(1)} KB`);
}

main();
