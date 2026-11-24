#!/usr/bin/env node
/**
 * ECDICT 数据导入脚本
 * 
 * 功能：
 * 1. 下载 ECDICT SQLite 数据库
 * 2. 从 SQLite 读取词典数据
 * 3. 批量导入到 CloudBase MySQL dict_word 表
 * 4. 生成 sw 字段（去特殊字符转小写）
 * 5. 根据 tag 字段生成 stage_word 映射
 * 
 * 用法：
 *   node import-ecdict.js [--skip-download] [--skip-import] [--skip-stage]
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

// ============ 配置 ============
const ECDICT_URL = 'https://github.com/skywind3000/ECDICT/releases/download/1.0.28/ecdict-sqlite-28.zip';
const SQLITE_FILE = 'stardict.db'; // 解压后的 SQLite 文件名
const SCRIPT_DIR = __dirname;
const ZIP_FILE = path.join(SCRIPT_DIR, 'ecdict-data', 'ecdict-sqlite-28.zip');
const DB_FILE = path.join(SCRIPT_DIR, 'ecdict-data', SQLITE_FILE);
const BATCH_SIZE = 500; // 每批插入的条数
const ENV_ID = 'cloud1-d0g0f3q7g8d2bb58f';

// ============ 命令行参数 ============
const args = process.argv.slice(2);
const skipDownload = args.includes('--skip-download');
const skipImport = args.includes('--skip-import');
const skipStage = args.includes('--skip-stage');

// ============ 工具函数 ============
function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    let redirectCount = 0;
    
    function doRequest(requestUrl) {
      if (redirectCount++ > 10) {
        reject(new Error('Too many redirects'));
        return;
      }
      
      const mod = requestUrl.startsWith('https') ? https : http;
      mod.get(requestUrl, { timeout: 300000 }, (response) => {
        if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
          doRequest(response.headers.location);
          return;
        }
        if (response.statusCode !== 200) {
          reject(new Error(`HTTP ${response.statusCode}`));
          return;
        }
        const totalSize = parseInt(response.headers['content-length'], 10);
        let downloaded = 0;
        response.on('data', (chunk) => {
          downloaded += chunk.length;
          if (totalSize) {
            const pct = ((downloaded / totalSize) * 100).toFixed(1);
            process.stdout.write(`\r下载进度: ${pct}% (${(downloaded / 1024 / 1024).toFixed(1)}MB / ${(totalSize / 1024 / 1024).toFixed(1)}MB)`);
          }
        });
        response.pipe(file);
        file.on('finish', () => {
          console.log('');
          file.close(resolve);
        });
      }).on('error', (err) => {
        fs.unlink(dest, () => {});
        reject(err);
      });
    }
    
    doRequest(url);
  });
}

function escapeSql(str) {
  if (str === null || str === undefined) return "''";
  return "'" + String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\0/g, '\\0') + "'";
}

// ============ 步骤 1：下载 & 解压 ============
async function step1_download() {
  if (skipDownload) {
    log('跳过下载 (--skip-download)');
    if (!fs.existsSync(DB_FILE)) {
      log(`错误：SQLite 文件不存在: ${DB_FILE}`);
      log('请先下载 ecdict-sqlite-28.zip 并解压到 scripts/ 目录');
      process.exit(1);
    }
    return;
  }
  
  if (fs.existsSync(DB_FILE)) {
    log(`SQLite 文件已存在: ${DB_FILE}，跳过下载`);
    return;
  }
  
  // 下载 zip
  if (!fs.existsSync(ZIP_FILE)) {
    log(`下载 ECDICT SQLite 数据库...`);
    log(`URL: ${ECDICT_URL}`);
    await downloadFile(ECDICT_URL, ZIP_FILE);
    log(`下载完成: ${ZIP_FILE}`);
  }
  
  // 解压
  log('解压中...');
  try {
    // 尝试用 PowerShell 解压
    execSync(`powershell -Command "Expand-Archive -Path '${ZIP_FILE}' -DestinationPath '${SCRIPT_DIR}' -Force"`, { stdio: 'inherit' });
    log('解压完成');
  } catch (e) {
    log('PowerShell 解压失败，尝试其他方式...');
    try {
      execSync(`tar -xf "${ZIP_FILE}" -C "${SCRIPT_DIR}"`, { stdio: 'inherit' });
      log('解压完成');
    } catch (e2) {
      log('自动解压失败，请手动解压 ecdict-sqlite-28.zip 到 scripts/ 目录');
      process.exit(1);
    }
  }
  
  if (!fs.existsSync(DB_FILE)) {
    log(`错误：解压后未找到 ${SQLITE_FILE}`);
    log('请检查解压后的文件名，可能需要重命名');
    process.exit(1);
  }
}

// ============ 步骤 2：使用 CloudBase SQL API 批量导入 ============
async function step2_import() {
  if (skipImport) {
    log('跳过导入 (--skip-import)');
    return;
  }
  
  log('安装依赖 better-sqlite3...');
  try {
    require('better-sqlite3');
  } catch (e) {
    execSync('npm install better-sqlite3', { cwd: SCRIPT_DIR, stdio: 'inherit' });
  }
  
  const Database = require('better-sqlite3');
  const db = new Database(DB_FILE, { readonly: true });
  
  // 查询总行数
  const countRow = db.prepare('SELECT COUNT(*) as cnt FROM stardict').get();
  const totalRows = countRow.cnt;
  log(`ECDICT 总词条数: ${totalRows}`);
  
  // 使用 CloudBase Node SDK
  log('安装 @cloudbase/node-sdk...');
  try {
    require('@cloudbase/node-sdk');
  } catch (e) {
    execSync('npm install @cloudbase/node-sdk', { cwd: SCRIPT_DIR, stdio: 'inherit' });
  }
  
  const cloudbase = require('@cloudbase/node-sdk');
  const app = cloudbase.init({
    env: ENV_ID,
  });
  
  const dbCloud = app.database();
  
  let imported = 0;
  let errors = 0;
  const startTime = Date.now();
  
  // 生成 sw 字段：去特殊字符转小写
  function generateSw(word) {
    return word.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
  }
  
  // tag 到 stage 的映射逻辑
  function tagToStages(tag, bnc, frq, collins) {
    const stages = new Set();
    
    // 基于 bnc 词频的基础阶段映射（高频优先）
    if (bnc > 0) {
      if (bnc <= 500) stages.add(1);    // 启蒙
      else if (bnc <= 1000) stages.add(2); // 小三
      else if (bnc <= 1500) stages.add(3); // 小四
      else if (bnc <= 2000) stages.add(4); // 小五
    }
    
    // 基于 tag 的考试阶段映射
    if (tag) {
      if (tag.includes('zk') || tag.includes('中考')) {
        stages.add(5); stages.add(6); stages.add(7); // 初一到初三
      }
      if (tag.includes('gk') || tag.includes('高考')) {
        stages.add(7); // 初三/高中
      }
      if (tag.includes('cet4')) {
        stages.add(8); // 四级
      }
      if (tag.includes('cet6')) {
        stages.add(9); // 六级
      }
      if (tag.includes('ielts')) {
        stages.add(10); // 雅思
      }
      if (tag.includes('toefl') || tag.includes('gre')) {
        stages.add(10); // 也映射到雅思阶段
      }
    }
    
    // 如果没有任何阶段（无 tag 且无 bnc），根据 collins 星级分配
    if (stages.size === 0 && collins >= 1) {
      stages.add(8); // 默认放到四级阶段
    }
    
    return Array.from(stages);
  }
  
  // 批量插入 dict_word 并收集 stage_word 数据
  const allStageWords = [];
  let batchCount = 0;
  
  // 使用 iterator 逐行读取
  const stmt = db.prepare('SELECT * FROM stardict ORDER BY id');
  
  log('开始导入数据...');
  
  let batchValues = [];
  
  for (const row of stmt.iterate()) {
    const sw = generateSw(row.word || '');
    const word = (row.word || '').trim();
    
    if (!word) continue; // 跳过空单词
    
    const values = [
      '',                           // _openid（公共数据为空）
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
      "''"                          // audio_url（暂空）
    ];
    
    batchValues.push(`(${values.join(',')})`);
    
    // 收集 stage_word 映射
    const stages = tagToStages(row.tag || '', row.bnc || 0, row.frq || 0, row.collins || 0);
    for (const stage of stages) {
      allStageWords.push({ word, stage, bnc: row.bnc || 0, frq: row.frq || 0 });
    }
    
    // 批量执行
    if (batchValues.length >= BATCH_SIZE) {
      batchCount++;
      const sql = `INSERT IGNORE INTO dict_word (_openid, word, sw, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange, audio_url) VALUES ${batchValues.join(',')};`;
      
      try {
        await dbCloud.executeSql(sql);
        imported += batchValues.length;
      } catch (e) {
        errors += batchValues.length;
        log(`批次 ${batchCount} 插入失败: ${e.message}`);
        // 尝试逐条插入
        for (const val of batchValues) {
          try {
            const singleSql = `INSERT IGNORE INTO dict_word (_openid, word, sw, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange, audio_url) VALUES ${val};`;
            await dbCloud.executeSql(singleSql);
            imported++;
          } catch (e2) {
            // 忽略单条失败
          }
        }
      }
      
      batchValues = [];
      
      // 进度
      const elapsed = (Date.now() - startTime) / 1000;
      const rate = imported / elapsed;
      const remaining = ((totalRows - imported) / rate).toFixed(0);
      process.stdout.write(`\r已导入: ${imported}/${totalRows} (${(imported/totalRows*100).toFixed(1)}%) 速度: ${rate.toFixed(0)}条/秒 剩余: ${remaining}s`);
      
      // 短暂休息避免限流
      await new Promise(r => setTimeout(r, 100));
    }
  }
  
  // 处理剩余的
  if (batchValues.length > 0) {
    const sql = `INSERT IGNORE INTO dict_word (_openid, word, sw, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange, audio_url) VALUES ${batchValues.join(',')};`;
    try {
      await dbCloud.executeSql(sql);
      imported += batchValues.length;
    } catch (e) {
      log(`最后批次插入失败: ${e.message}`);
    }
  }
  
  console.log('');
  log(`dict_word 导入完成: 成功 ${imported}, 失败 ${errors}, 耗时 ${((Date.now() - startTime) / 1000).toFixed(1)}s`);
  
  // ============ 步骤 3：生成 stage_word 映射 ============
  if (!skipStage && allStageWords.length > 0) {
    log(`开始生成 stage_word 映射，共 ${allStageWords.length} 条...`);
    
    // 先查所有 word_id 映射
    log('查询 word -> id 映射...');
    let wordIdMap = {};
    let offset = 0;
    const mapBatchSize = 5000;
    
    while (true) {
      try {
        const result = await dbCloud.executeSql(`SELECT id, word FROM dict_word LIMIT ${mapBatchSize} OFFSET ${offset}`);
        if (!result || result.length === 0) break;
        for (const row of result) {
          wordIdMap[row.word] = row.id;
        }
        offset += mapBatchSize;
        if (result.length < mapBatchSize) break;
      } catch (e) {
        log(`查询 word 映射失败: ${e.message}`);
        break;
      }
    }
    
    log(`word -> id 映射完成，共 ${Object.keys(wordIdMap).length} 条`);
    
    // 批量插入 stage_word
    let stageBatchValues = [];
    let stageImported = 0;
    let masteryOrder = {};
    
    for (const item of allStageWords) {
      const wordId = wordIdMap[item.word];
      if (!wordId) continue;
      
      const stageKey = `stage_${item.stage}`;
      if (!masteryOrder[stageKey]) masteryOrder[stageKey] = 0;
      masteryOrder[stageKey]++;
      
      stageBatchValues.push(`('', ${wordId}, ${item.stage}, ${masteryOrder[stageKey]})`);
      
      if (stageBatchValues.length >= BATCH_SIZE) {
        const sql = `INSERT IGNORE INTO stage_word (_openid, word_id, stage, mastery_order) VALUES ${stageBatchValues.join(',')};`;
        try {
          await dbCloud.executeSql(sql);
          stageImported += stageBatchValues.length;
        } catch (e) {
          log(`stage_word 批次插入失败: ${e.message}`);
        }
        stageBatchValues = [];
        process.stdout.write(`\rstage_word 已导入: ${stageImported}/${allStageWords.length}`);
        await new Promise(r => setTimeout(r, 100));
      }
    }
    
    if (stageBatchValues.length > 0) {
      const sql = `INSERT IGNORE INTO stage_word (_openid, word_id, stage, mastery_order) VALUES ${stageBatchValues.join(',')};`;
      try {
        await dbCloud.executeSql(sql);
        stageImported += stageBatchValues.length;
      } catch (e) {
        log(`stage_word 最后批次插入失败: ${e.message}`);
      }
    }
    
    console.log('');
    log(`stage_word 导入完成: ${stageImported} 条`);
  }
  
  db.close();
  log('全部完成!');
}

// ============ 主流程 ============
async function main() {
  log('=== ECDICT 数据导入工具 ===');
  log(`CloudBase 环境: ${ENV_ID}`);
  log(`参数: skipDownload=${skipDownload}, skipImport=${skipImport}, skipStage=${skipStage}`);
  
  try {
    await step1_download();
    await step2_import();
  } catch (e) {
    log(`错误: ${e.message}`);
    console.error(e);
    process.exit(1);
  }
}

main();
