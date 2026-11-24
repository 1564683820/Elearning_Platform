#!/usr/bin/env node
/**
 * ECDICT 数据导入脚本 v3
 * 
 * 使用 CloudBase Node SDK 的 rdb() ORM API 批量导入
 * 
 * 用法：
 *   node import-ecdict-v3.js [--max-rows=0] [--offset=0] [--batch-size=100]
 */

const fs = require('fs');
const path = require('path');

// ============ 配置 ============
const SCRIPT_DIR = __dirname;
const DB_FILE = path.join(SCRIPT_DIR, 'ecdict-data', 'stardict.db');
const ENV_ID = 'cloud1-d0g0f3q7g8d2bb58f';
const DEFAULT_BATCH_SIZE = 100; // rdb insert 批量不宜太大

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

function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

function generateSw(word) {
  return (word || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
}

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

async function main() {
  const opts = parseArgs();
  log('=== ECDICT 导入 v3 (rdb ORM) ===');
  log(`环境: ${ENV_ID}, batchSize=${opts.batchSize}, maxRows=${opts.maxRows}, offset=${opts.offset}`);

  if (!fs.existsSync(DB_FILE)) {
    log(`错误: SQLite 文件不存在: ${DB_FILE}`);
    process.exit(1);
  }

  // 初始化 CloudBase SDK
  const cloudbase = require('@cloudbase/node-sdk');
  const app = cloudbase.init({ env: ENV_ID });
  const db = app.rdb();

  // 打开 SQLite
  const Database = require('better-sqlite3');
  const sqlite = new Database(DB_FILE, { readonly: true });

  const countRow = sqlite.prepare('SELECT COUNT(*) as cnt FROM stardict').get();
  const totalRows = countRow.cnt;
  log(`ECDICT 总词条数: ${totalRows}`);

  const limitRows = opts.maxRows > 0 ? Math.min(opts.maxRows, totalRows) : totalRows;
  log(`计划导入: ${limitRows} 条`);

  // 进度文件
  const progressFile = path.join(SCRIPT_DIR, 'import-progress.json');
  let progress = { imported: 0, errors: 0, lastOffset: opts.offset };
  if (fs.existsSync(progressFile) && opts.offset === 0) {
    try {
      progress = JSON.parse(fs.readFileSync(progressFile, 'utf8'));
      log(`恢复进度: 已导入 ${progress.imported}, 偏移 ${progress.lastOffset}`);
      opts.offset = progress.lastOffset;
    } catch (e) { /* 忽略 */ }
  }

  let imported = progress.imported;
  let errors = progress.errors;
  const startTime = Date.now();
  const stageWordBuffer = [];

  const stmt = sqlite.prepare(`SELECT * FROM stardict ORDER BY id LIMIT ${limitRows} OFFSET ${opts.offset}`);
  let batchRows = [];
  let currentOffset = opts.offset;

  for (const row of stmt.iterate()) {
    const word = (row.word || '').trim();
    if (!word) continue;

    const sw = generateSw(word);
    
    batchRows.push({
      _openid: '',
      word: word,
      sw: sw,
      phonetic: row.phonetic || '',
      definition: row.definition || null,
      translation: row.translation || null,
      pos: row.pos || '',
      collins: row.collins || 0,
      oxford: row.oxford || 0,
      tag: row.tag || '',
      bnc: row.bnc || 0,
      frq: row.frq || 0,
      exchange: row.exchange || '',
      audio_url: ''
    });

    // 收集 stage 映射
    const stages = tagToStages(row.tag || '', row.bnc || 0, row.collins || 0);
    for (const stage of stages) {
      stageWordBuffer.push({ word, stage, bnc: row.bnc || 0 });
    }

    if (batchRows.length >= opts.batchSize) {
      currentOffset += batchRows.length;
      
      let retries = 3;
      while (retries > 0) {
        try {
          const { error } = await db.from('dict_word').insert(batchRows);
          if (error) throw error;
          imported += batchRows.length;
          break;
        } catch (e) {
          retries--;
          if (retries <= 0) {
            errors += batchRows.length;
            log(`批次失败 (offset ${currentOffset}): ${e.message || JSON.stringify(e)}`);
          } else {
            log(`重试 (${retries} left): ${e.message || 'unknown error'}`);
            await new Promise(r => setTimeout(r, 2000));
          }
        }
      }

      batchRows = [];
      
      // 保存进度
      progress = { imported, errors, lastOffset: currentOffset };
      fs.writeFileSync(progressFile, JSON.stringify(progress, null, 2));

      const elapsed = (Date.now() - startTime) / 1000;
      const rate = imported / (elapsed || 1);
      const pct = (imported / limitRows * 100).toFixed(1);
      process.stdout.write(`\r进度: ${imported}/${limitRows} (${pct}%) ${rate.toFixed(0)}条/秒 错误:${errors}`);

      await new Promise(r => setTimeout(r, 100));
    }
  }

  // 处理剩余
  if (batchRows.length > 0) {
    try {
      const { error } = await db.from('dict_word').insert(batchRows);
      if (error) throw error;
      imported += batchRows.length;
    } catch (e) {
      errors += batchRows.length;
      log(`最后批次失败: ${e.message || JSON.stringify(e)}`);
    }
  }

  console.log('');
  log(`dict_word 完成: 成功 ${imported}, 失败 ${errors}, 耗时 ${((Date.now() - startTime) / 1000).toFixed(1)}s`);

  // ============ stage_word ============
  if (stageWordBuffer.length > 0) {
    log(`生成 stage_word 映射 (${stageWordBuffer.length} 条)...`);

    // 查 word -> id 映射
    const wordIdMap = {};
    let mapOffset = 0;
    const mapBatch = 5000;
    while (true) {
      try {
        const { data, error } = await db.from('dict_word').select('id, word').range(mapOffset, mapOffset + mapBatch - 1);
        if (error || !data || data.length === 0) break;
        for (const row of data) {
          wordIdMap[row.word] = row.id;
        }
        mapOffset += mapBatch;
        if (data.length < mapBatch) break;
      } catch (e) {
        log(`查询映射失败: ${e.message}`);
        break;
      }
    }
    log(`映射完成: ${Object.keys(wordIdMap).length} 条`);

    let stageBatchValues = [];
    let stageImported = 0;
    const masteryOrder = {};

    for (const item of stageWordBuffer) {
      const wordId = wordIdMap[item.word];
      if (!wordId) continue;

      const stageKey = `s${item.stage}`;
      if (!masteryOrder[stageKey]) masteryOrder[stageKey] = 0;
      masteryOrder[stageKey]++;

      stageBatchValues.push({
        _openid: '',
        word_id: wordId,
        stage: item.stage,
        mastery_order: masteryOrder[stageKey]
      });

      if (stageBatchValues.length >= opts.batchSize) {
        try {
          const { error } = await db.from('stage_word').insert(stageBatchValues);
          if (error) throw error;
          stageImported += stageBatchValues.length;
        } catch (e) {
          log(`stage_word 批次失败: ${e.message || JSON.stringify(e)}`);
        }
        stageBatchValues = [];
        process.stdout.write(`\rstage_word: ${stageImported}/${stageWordBuffer.length}`);
        await new Promise(r => setTimeout(r, 100));
      }
    }

    if (stageBatchValues.length > 0) {
      try {
        const { error } = await db.from('stage_word').insert(stageBatchValues);
        if (error) throw error;
        stageImported += stageBatchValues.length;
      } catch (e) {
        log(`stage_word 最后批次失败: ${e.message || JSON.stringify(e)}`);
      }
    }

    console.log('');
    log(`stage_word 完成: ${stageImported} 条`);
  }

  sqlite.close();
  try { fs.unlinkSync(progressFile); } catch (e) {}
  log('全部完成!');
}

main().catch(e => {
  log(`错误: ${e.message}`);
  console.error(e);
  process.exit(1);
});
