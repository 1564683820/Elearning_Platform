#!/usr/bin/env node
'use strict';

/**
 * 从 SQLite (ECDICT) 提取数据，生成可被 MCP executeWriteSQL 执行的 SQL 批次文件
 * 
 * 用法: node generate-sql-batches.js [--phase phase1] [--batch-size 100] [--limit N]
 * 
 * 阶段定义:
 *   phase1: BNC 前2000高频词
 *   phase2: Collins 5星
 *   phase3: CET4
 *   phase4: CET6
 *   phase5: IELTS
 *   phase6: 高考
 *   phase7: Collins 3-4星
 *   all: 全部词条
 */

const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');

const DB_PATH = path.join(__dirname, 'ecdict-data', 'stardict.db');
const OUTPUT_DIR = path.join(__dirname, 'sql-import-batches');

// MySQL 字符串转义
function escapeSql(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/\0/g, '\\0')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r')
    .replace(/\t/g, '\\t')
    .replace(/\x1a/g, '\\Z');
}

// 生成 sw (search word) - 去除非字母数字字符并转小写
function generateSW(word) {
  return (word || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
}

// 阶段查询条件
const PHASE_QUERIES = {
  phase1: {
    name: 'BNC前2000高频词',
    where: "bnc != '' AND CAST(bnc AS INTEGER) > 0 AND CAST(bnc AS INTEGER) <= 2000",
    orderBy: 'CAST(bnc AS INTEGER) ASC',
    limit: null
  },
  phase2: {
    name: 'Collins 5星',
    where: "collins = 5",
    orderBy: 'word ASC',
    limit: null
  },
  phase3: {
    name: 'CET4',
    where: "tag LIKE '%cet4%'",
    orderBy: 'word ASC',
    limit: null
  },
  phase4: {
    name: 'CET6',
    where: "tag LIKE '%cet6%'",
    orderBy: 'word ASC',
    limit: null
  },
  phase5: {
    name: 'IELTS',
    where: "tag LIKE '%ielts%'",
    orderBy: 'word ASC',
    limit: null
  },
  phase6: {
    name: '高考',
    where: "tag LIKE '%gk%'",
    orderBy: 'word ASC',
    limit: null
  },
  phase7: {
    name: 'Collins 3-4星',
    where: "collins IN (3, 4)",
    orderBy: 'word ASC',
    limit: null
  },
  all: {
    name: '全部词条',
    where: "1=1",
    orderBy: 'word ASC',
    limit: null
  }
};

function main() {
  const args = process.argv.slice(2);
  let phase = 'phase1';
  let batchSize = 50;
  let limitOverride = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--phase' && args[i + 1]) {
      phase = args[i + 1];
      i++;
    } else if (args[i] === '--batch-size' && args[i + 1]) {
      batchSize = parseInt(args[i + 1], 10);
      i++;
    } else if (args[i] === '--limit' && args[i + 1]) {
      limitOverride = parseInt(args[i + 1], 10);
      i++;
    }
  }

  if (!PHASE_QUERIES[phase]) {
    console.error(`Unknown phase: ${phase}. Available: ${Object.keys(PHASE_QUERIES).join(', ')}`);
    process.exit(1);
  }

  const phaseConfig = PHASE_QUERIES[phase];
  console.log(`Phase: ${phase} (${phaseConfig.name})`);
  console.log(`Batch size: ${batchSize}`);

  // 确保输出目录存在
  const phaseDir = path.join(OUTPUT_DIR, phase);
  fs.mkdirSync(phaseDir, { recursive: true });

  // 打开 SQLite
  if (!fs.existsSync(DB_PATH)) {
    console.error(`SQLite DB not found: ${DB_PATH}`);
    console.error('Please place stardict.db in scripts/ecdict-data/');
    process.exit(1);
  }

  const db = new Database(DB_PATH, { readonly: true });

  // 查询数据
  let sql = `SELECT word, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange FROM stardict WHERE ${phaseConfig.where} ORDER BY ${phaseConfig.orderBy}`;
  if (limitOverride) {
    sql += ` LIMIT ${limitOverride}`;
  }

  console.log(`Executing: ${sql.substring(0, 200)}...`);

  const rows = db.prepare(sql).all();
  console.log(`Found ${rows.length} records`);

  if (rows.length === 0) {
    console.log('No records to import.');
    db.close();
    return;
  }

  // 生成批次文件
  let batchIndex = 0;
  let totalGenerated = 0;

  for (let i = 0; i < rows.length; i += batchSize) {
    const batch = rows.slice(i, i + batchSize);
    const values = batch.map(row => {
      const word = escapeSql(row.word);
      const sw = escapeSql(generateSW(row.word));
      const phonetic = escapeSql(row.phonetic);
      const definition = escapeSql(row.definition);
      const translation = escapeSql(row.translation);
      const pos = escapeSql(row.pos);
      const collins = parseInt(row.collins, 10) || 0;
      const oxford = parseInt(row.oxford, 10) || 0;
      const tag = escapeSql(row.tag);
      const bnc = parseFloat(row.bnc) || 0;
      const frq = parseFloat(row.frq) || 0;
      const exchange = escapeSql(row.exchange);

      return `('${word}', '${sw}', '${phonetic}', '${definition}', '${translation}', '${pos}', ${collins}, ${oxford}, '${tag}', ${bnc}, ${frq}, '${exchange}', '')`;
    });

    const insertSql = `INSERT INTO dict_word (word, sw, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange, audio_url) VALUES\n${values.join(',\n')};`;

    const fileName = `batch_${String(batchIndex).padStart(5, '0')}.sql`;
    const filePath = path.join(phaseDir, fileName);
    fs.writeFileSync(filePath, insertSql, 'utf-8');

    totalGenerated += batch.length;
    batchIndex++;
  }

  console.log(`\nGenerated ${batchIndex} batch files in ${phaseDir}`);
  console.log(`Total records: ${totalGenerated}`);
  console.log(`\nTo import, execute each batch file via MCP executeWriteSQL tool.`);

  db.close();
}

main();
