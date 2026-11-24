#!/usr/bin/env node
'use strict';

/**
 * 本地脚本：从 SQLite (ECDICT) 读取数据，通过 CloudBase 云函数批量导入到 MySQL
 * 
 * 用法: node import-to-cloud.js [--phase phase1] [--batch-size 20] [--limit N] [--dry-run]
 * 
 * 阶段定义:
 *   phase1: BNC 前2000高频词
 *   phase2: Collins 5星
 *   phase3: CET4
 *   phase4: CET6
 *   phase5: IELTS
 *   phase6: 高考
 *   phase7: Collins 3-4星
 */

const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');
const http = require('https');

const DB_PATH = path.join(__dirname, 'ecdict-data', 'stardict.db');

// CloudBase 配置 - 从环境变量或硬编码
const ENV_ID = process.env.TCB_ENV_ID || 'cloud1-d0g0f3q7g8d2bb58f';
const FUNCTION_NAME = 'import-dict';

// 阶段查询条件
const PHASE_QUERIES = {
  phase1: {
    name: 'BNC前2000高频词',
    where: "bnc != '' AND CAST(bnc AS INTEGER) > 0 AND CAST(bnc AS INTEGER) <= 2000",
    orderBy: 'CAST(bnc AS INTEGER) ASC',
  },
  phase2: {
    name: 'Collins 5星',
    where: "collins = 5",
    orderBy: 'word ASC',
  },
  phase3: {
    name: 'CET4',
    where: "tag LIKE '%cet4%'",
    orderBy: 'word ASC',
  },
  phase4: {
    name: 'CET6',
    where: "tag LIKE '%cet6%'",
    orderBy: 'word ASC',
  },
  phase5: {
    name: 'IELTS',
    where: "tag LIKE '%ielts%'",
    orderBy: 'word ASC',
  },
  phase6: {
    name: '高考',
    where: "tag LIKE '%gk%'",
    orderBy: 'word ASC',
  },
  phase7: {
    name: 'Collins 3-4星',
    where: "collins IN (3, 4)",
    orderBy: 'word ASC',
  },
};

// 生成 sw (search word)
function generateSW(word) {
  return (word || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
}

// 调用云函数
function invokeCloudFunction(data) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(data);
    
    const options = {
      hostname: `${ENV_ID}.service.tcloudbase.com`,
      port: 443,
      path: `/cloudfunction/${FUNCTION_NAME}`,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
      timeout: 30000,
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          resolve({ error: 'Parse error', raw: data.substring(0, 500) });
        }
      });
    });

    req.on('error', (e) => reject(e));
    req.on('timeout', () => { req.destroy(); reject(new Error('Request timeout')); });
    req.write(body);
    req.end();
  });
}

// 通过 MCP 代理调用（需要通过 cloudbase CLI 或直接 HTTP API）
// 这里我们生成 JSON 批次文件，供外部调用使用
async function main() {
  const args = process.argv.slice(2);
  let phase = 'phase1';
  let batchSize = 20;
  let limitOverride = null;
  let dryRun = false;
  let mode = 'json'; // json: 生成JSON批次文件, invoke: 直接调用云函数

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--phase' && args[i + 1]) { phase = args[i + 1]; i++; }
    else if (args[i] === '--batch-size' && args[i + 1]) { batchSize = parseInt(args[i + 1], 10); i++; }
    else if (args[i] === '--limit' && args[i + 1]) { limitOverride = parseInt(args[i + 1], 10); i++; }
    else if (args[i] === '--dry-run') { dryRun = true; }
    else if (args[i] === '--mode' && args[i + 1]) { mode = args[i + 1]; i++; }
  }

  if (!PHASE_QUERIES[phase]) {
    console.error(`Unknown phase: ${phase}. Available: ${Object.keys(PHASE_QUERIES).join(', ')}`);
    process.exit(1);
  }

  const phaseConfig = PHASE_QUERIES[phase];
  console.log(`Phase: ${phase} (${phaseConfig.name})`);
  console.log(`Batch size: ${batchSize}`);
  console.log(`Mode: ${mode}`);

  // 打开 SQLite
  if (!fs.existsSync(DB_PATH)) {
    console.error(`SQLite DB not found: ${DB_PATH}`);
    process.exit(1);
  }

  const db = new Database(DB_PATH, { readonly: true });

  // 查询数据
  let sql = `SELECT word, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange FROM stardict WHERE ${phaseConfig.where} ORDER BY ${phaseConfig.orderBy}`;
  if (limitOverride) sql += ` LIMIT ${limitOverride}`;

  console.log(`Executing query...`);
  const rows = db.prepare(sql).all();
  console.log(`Found ${rows.length} records`);

  if (rows.length === 0) {
    console.log('No records to import.');
    db.close();
    return;
  }

  // 转换为导入格式
  const importRows = rows.map(row => ({
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

  if (dryRun) {
    console.log(`\n[Dry Run] Would import ${importRows.length} records in ${Math.ceil(importRows.length / batchSize)} batches`);
    console.log('Sample record:', JSON.stringify(importRows[0], null, 2));
    db.close();
    return;
  }

  if (mode === 'json') {
    // 生成 JSON 批次文件
    const outputDir = path.join(__dirname, 'json-batches', phase);
    fs.mkdirSync(outputDir, { recursive: true });

    let batchIndex = 0;
    for (let i = 0; i < importRows.length; i += batchSize) {
      const batch = importRows.slice(i, i + batchSize);
      const fileName = `batch_${String(batchIndex).padStart(5, '0')}.json`;
      const filePath = path.join(outputDir, fileName);
      fs.writeFileSync(filePath, JSON.stringify(batch, null, 2), 'utf-8');
      batchIndex++;
    }

    console.log(`\nGenerated ${batchIndex} JSON batch files in ${outputDir}`);
    console.log(`To import, use the cloud function with each batch file.`);
  }

  db.close();
}

main().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
