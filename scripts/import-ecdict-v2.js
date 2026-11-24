#!/usr/bin/env node
/**
 * ECDICT 数据导入脚本 v2
 * 
 * 高效版本：使用 CloudBase Node SDK 的 executeSql 方法批量导入
 * 每批 500 条 INSERT，自动限流重试
 * 
 * 用法：
 *   node import-ecdict-v2.js [--batch-size=500] [--max-rows=0] [--offset=0]
 * 
 * 参数：
 *   --batch-size=N   每批插入条数（默认 500）
 *   --max-rows=N     最多导入 N 条（0=全部，默认 0）
 *   --offset=N       从第 N 条开始（默认 0）
 * 
 * 示例：
 *   node import-ecdict-v2.js                    # 导入全部
 *   node import-ecdict-v2.js --max-rows=1000     # 先导入1000条测试
 *   node import-ecdict-v2.js --offset=1000       # 从第1000条继续
 */

const fs = require('fs');
const path = require('path');

// ============ 配置 ============
const SCRIPT_DIR = __dirname;
const DB_FILE = path.join(SCRIPT_DIR, 'ecdict-data', 'stardict.db');
const ENV_ID = 'cloud1-d0g0f3q7g8d2bb58f';
const DEFAULT_BATCH_SIZE = 500;

// 解析命令行参数
function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { batchSize: DEFAULT_BATCH_SIZE, maxRows: 0, offset: 0 };
  for (const arg of args) {
    const [key, val] = arg.replace(/^--/, '').split('=');
    if (key === 'batch-size') opts.batchSize = parseInt(val, 10) || DEFAULT_BATCH_SIZE;
    if (key === 'max-rows') opts.maxRows = parseInt(val, 10) || 0;
    if (key === 'offset') opts.offset = parseInt(val, 10) || 0;
  }
  return opts;
}

// ============ 工具函数 ============
function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

function escapeSql(str) {
  if (str === null || str === undefined) return "''";
  return "'" + String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\0/g, '\\0') + "'";
}

// 生成 sw 字段
function generateSw(word) {
  return (word || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
}

// tag 到 stage 的映射
function tagToStages(tag, bnc, collins) {
  const stages = new Set();
  if (bnc > 0) {
    if (bnc <= 500) stages.add(1);
    else if (bnc <= 1000) stages.add(2);
    else if (bnc <= 1500) stages.add(3);
    else if (bnc <= 2000) stages.add(4);
  }
  if (tag) {
    if (tag.includes('zk') || tag.includes('中考')) { stages.add(5); stages.add(6); stages.add(7); }
    if (tag.includes('gk') || tag.includes('高考')) stages.add(7);
    if (tag.includes('cet4')) stages.add(8);
    if (tag.includes('cet6')) stages.add(9);
    if (tag.includes('ielts')) stages.add(10);
    if (tag.includes('toefl') || tag.includes('gre')) stages.add(10);
  }
  if (stages.size === 0 && collins >= 1) stages.add(8);
  return Array.from(stages);
}

// ============ 主流程 ============
async function main() {
  const opts = parseArgs();
  log('=== ECDICT 导入 v2 ===');
  log(`CloudBase 环境: ${ENV_ID}`);
  log(`参数: batchSize=${opts.batchSize}, maxRows=${opts.maxRows}, offset=${opts.offset}`);

  // 检查 SQLite 文件
  if (!fs.existsSync(DB_FILE)) {
    log(`错误: SQLite 文件不存在: ${DB_FILE}`);
    process.exit(1);
  }
  const dbStat = fs.statSync(DB_FILE);
  log(`SQLite 文件: ${(dbStat.size / 1024 / 1024).toFixed(1)}MB`);

  // 初始化 CloudBase SDK
  const cloudbase = require('@cloudbase/node-sdk');
  const app = cloudbase.init({ env: ENV_ID });
  const dbCloud = app.database();

  // 打开 SQLite
  const Database = require('better-sqlite3');
  const db = new Database(DB_FILE, { readonly: true });

  // 查总行数
  const countRow = db.prepare('SELECT COUNT(*) as cnt FROM stardict').get();
  const totalRows = countRow.cnt;
  log(`ECDICT 总词条数: ${totalRows}`);

  const limitRows = opts.maxRows > 0 ? Math.min(opts.maxRows, totalRows) : totalRows;
  log(`计划导入: ${limitRows} 条 (从 offset ${opts.offset} 开始)`);

  // 进度文件
  const progressFile = path.join(SCRIPT_DIR, 'import-progress.json');
  let progress = { imported: 0, errors: 0, lastOffset: opts.offset };
  if (fs.existsSync(progressFile) && opts.offset === 0) {
    try {
      progress = JSON.parse(fs.readFileSync(progressFile, 'utf8'));
      log(`从进度文件恢复: 已导入 ${progress.imported}, 上次偏移 ${progress.lastOffset}`);
      opts.offset = progress.lastOffset;
    } catch (e) { /* 忽略 */ }
  }

  let imported = progress.imported;
  let errors = progress.errors;
  let batchCount = 0;
  const startTime = Date.now();

  // 收集所有 stage_word 数据（在导入 dict_word 时收集）
  const stageWordBuffer = [];

  // 使用 iterator 逐行读取
  const stmt = db.prepare(`SELECT * FROM stardict ORDER BY id LIMIT ${limitRows} OFFSET ${opts.offset}`);

  let batchValues = [];
  let currentOffset = opts.offset;

  for (const row of stmt.iterate()) {
    const word = (row.word || '').trim();
    if (!word) continue;

    const sw = generateSw(word);
    const values = [
      '',                           // _openid
      escapeSql(word),              // word
      escapeSql(sw),                // sw
      escapeSql(row.phonetic),      // phonetic
      escapeSql(row.definition),    // definition
      escapeSql(row.translation),   // translation
      escapeSql(row.pos),           // pos
      row.collins || 0,             // collins
      row.oxford || 0,              // oxford
      escapeSql(row.tag),           // tag
      row.bnc || 0,                 // bnc
      row.frq || 0,                 // frq
      escapeSql(row.exchange),      // exchange
      "''"                          // audio_url
    ];

    batchValues.push(`(${values.join(',')})`);

    // 收集 stage 映射
    const stages = tagToStages(row.tag || '', row.bnc || 0, row.collins || 0);
    for (const stage of stages) {
      stageWordBuffer.push({ word, stage, bnc: row.bnc || 0 });
    }

    // 批量执行
    if (batchValues.length >= opts.batchSize) {
      batchCount++;
      currentOffset += batchValues.length;
      
      const sql = `INSERT IGNORE INTO dict_word (_openid, word, sw, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange, audio_url) VALUES ${batchValues.join(',')};`;
      
      let retries = 3;
      while (retries > 0) {
        try {
          await dbCloud.executeSql(sql);
          imported += batchValues.length;
          break;
        } catch (e) {
          retries--;
          if (retries <= 0) {
            errors += batchValues.length;
            log(`批次 ${batchCount} 失败: ${e.message}`);
          } else {
            log(`批次 ${batchCount} 重试 (${retries} left): ${e.message}`);
            await new Promise(r => setTimeout(r, 2000));
          }
        }
      }

      batchValues = [];

      // 保存进度
      progress = { imported, errors, lastOffset: currentOffset };
      fs.writeFileSync(progressFile, JSON.stringify(progress, null, 2));

      // 显示进度
      const elapsed = (Date.now() - startTime) / 1000;
      const rate = imported / (elapsed || 1);
      const pct = (imported / limitRows * 100).toFixed(1);
      process.stdout.write(`\r进度: ${imported}/${limitRows} (${pct}%) 速度: ${rate.toFixed(0)}条/秒 错误: ${errors}`);

      // 限流
      await new Promise(r => setTimeout(r, 200));
    }
  }

  // 处理剩余的
  if (batchValues.length > 0) {
    const sql = `INSERT IGNORE INTO dict_word (_openid, word, sw, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange, audio_url) VALUES ${batchValues.join(',')};`;
    try {
      await dbCloud.executeSql(sql);
      imported += batchValues.length;
    } catch (e) {
      errors += batchValues.length;
      log(`最后批次失败: ${e.message}`);
    }
  }

  console.log('');
  log(`dict_word 导入完成: 成功 ${imported}, 失败 ${errors}, 耗时 ${((Date.now() - startTime) / 1000).toFixed(1)}s`);

  // ============ 生成 stage_word ============
  if (stageWordBuffer.length > 0) {
    log(`开始生成 stage_word 映射，共 ${stageWordBuffer.length} 条...`);

    // 查询 word -> id 映射
    log('查询 word -> id 映射...');
    const wordIdMap = {};
    let mapOffset = 0;
    const mapBatch = 5000;
    while (true) {
      try {
        const result = await dbCloud.executeSql(`SELECT id, word FROM dict_word LIMIT ${mapBatch} OFFSET ${mapOffset}`);
        if (!result || result.length === 0) break;
        for (const row of result) {
          wordIdMap[row.word] = row.id;
        }
        mapOffset += mapBatch;
        if (result.length < mapBatch) break;
      } catch (e) {
        log(`查询映射失败: ${e.message}`);
        break;
      }
    }
    log(`映射完成，共 ${Object.keys(wordIdMap).length} 条`);

    // 批量插入 stage_word
    let stageBatchValues = [];
    let stageImported = 0;
    const masteryOrder = {};

    for (const item of stageWordBuffer) {
      const wordId = wordIdMap[item.word];
      if (!wordId) continue;

      const stageKey = `s${item.stage}`;
      if (!masteryOrder[stageKey]) masteryOrder[stageKey] = 0;
      masteryOrder[stageKey]++;

      stageBatchValues.push(`('', ${wordId}, ${item.stage}, ${masteryOrder[stageKey]})`);

      if (stageBatchValues.length >= opts.batchSize) {
        const sql = `INSERT IGNORE INTO stage_word (_openid, word_id, stage, mastery_order) VALUES ${stageBatchValues.join(',')};`;
        try {
          await dbCloud.executeSql(sql);
          stageImported += stageBatchValues.length;
        } catch (e) {
          log(`stage_word 批次失败: ${e.message}`);
        }
        stageBatchValues = [];
        process.stdout.write(`\rstage_word: ${stageImported}/${stageWordBuffer.length}`);
        await new Promise(r => setTimeout(r, 200));
      }
    }

    if (stageBatchValues.length > 0) {
      const sql = `INSERT IGNORE INTO stage_word (_openid, word_id, stage, mastery_order) VALUES ${stageBatchValues.join(',')};`;
      try {
        await dbCloud.executeSql(sql);
        stageImported += stageBatchValues.length;
      } catch (e) {
        log(`stage_word 最后批次失败: ${e.message}`);
      }
    }

    console.log('');
    log(`stage_word 导入完成: ${stageImported} 条`);
  }

  db.close();

  // 清理进度文件
  try { fs.unlinkSync(progressFile); } catch (e) {}

  log('全部完成!');
}

main().catch(e => {
  log(`错误: ${e.message}`);
  console.error(e);
  process.exit(1);
});
