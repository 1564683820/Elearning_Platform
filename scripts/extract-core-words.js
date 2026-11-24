#!/usr/bin/env node
/**
 * 从 ECDICT SQLite 提取核心词并生成 SQL INSERT 语句
 * 
 * 筛选条件：
 * - collins >= 3（柯林斯3星以上）
 * - 或 tag 包含 cet4/cet6/ielts/gk/zk
 * - 或 bnc <= 5000（高频词）
 * 
 * 输出：SQL 文件，可直接通过 CloudBase SQL API 执行
 */

const fs = require('fs');
const path = require('path');

const SCRIPT_DIR = __dirname;
const DB_FILE = path.join(SCRIPT_DIR, 'ecdict-data', 'stardict.db');
const OUTPUT_FILE = path.join(SCRIPT_DIR, 'core-words.sql');

function escapeSql(str) {
  if (str === null || str === undefined) return "''";
  return "'" + String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\0/g, '\\0') + "'";
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

function main() {
  const Database = require('better-sqlite3');
  const db = new Database(DB_FILE, { readonly: true });

  // 提取核心词
  const sql = `
    SELECT * FROM stardict 
    WHERE collins >= 3 
       OR tag LIKE '%cet4%' 
       OR tag LIKE '%cet6%' 
       OR tag LIKE '%ielts%'
       OR tag LIKE '%gk%'
       OR tag LIKE '%zk%'
       OR bnc <= 5000
    ORDER BY 
      CASE WHEN bnc > 0 THEN bnc ELSE 999999 END ASC,
      collins DESC
  `;

  const rows = db.prepare(sql).all();
  console.log(`筛选出核心词: ${rows.length} 条`);

  // 生成 dict_word INSERT
  const BATCH_SIZE = 50; // CloudBase SQL API 每批限制
  let dictInserts = [];
  let stageWordData = [];
  let output = [];

  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const word = (row.word || '').trim();
    if (!word) continue;

    const sw = generateSw(word);
    const values = [
      '',                           // _openid
      escapeSql(word),
      escapeSql(sw),
      escapeSql(row.phonetic),
      escapeSql(row.definition),
      escapeSql(row.translation),
      escapeSql(row.pos),
      row.collins || 0,
      row.oxford || 0,
      escapeSql(row.tag),
      row.bnc || 0,
      row.frq || 0,
      escapeSql(row.exchange),
      "''"
    ];

    dictInserts.push(`(${values.join(',')})`);

    const stages = tagToStages(row.tag || '', row.bnc || 0, row.collins || 0);
    for (const stage of stages) {
      stageWordData.push({ word, stage, bnc: row.bnc || 0 });
    }

    if (dictInserts.length >= BATCH_SIZE || i === rows.length - 1) {
      output.push(`INSERT IGNORE INTO dict_word (_openid, word, sw, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange, audio_url) VALUES ${dictInserts.join(',')};`);
      dictInserts = [];
    }
  }

  console.log(`dict_word INSERT 语句: ${output.length} 批`);

  // 生成 stage_word INSERT（需要在 dict_word 导入后执行）
  output.push('');
  output.push('-- stage_word 映射数据（需要在 dict_word 导入后执行）');
  
  // 先输出 word_id 查询
  output.push('-- 注意：stage_word 的 word_id 需要从 dict_word 查询获取');
  output.push('-- 以下使用子查询方式插入');

  let stageInserts = [];
  const masteryOrder = {};
  
  for (const item of stageWordData) {
    const stageKey = `s${item.stage}`;
    if (!masteryOrder[stageKey]) masteryOrder[stageKey] = 0;
    masteryOrder[stageKey]++;

    stageInserts.push(`('', (SELECT id FROM dict_word WHERE word = ${escapeSql(item.word)}), ${item.stage}, ${masteryOrder[stageKey]})`);

    if (stageInserts.length >= BATCH_SIZE) {
      output.push(`INSERT IGNORE INTO stage_word (_openid, word_id, stage, mastery_order) VALUES ${stageInserts.join(',')};`);
      stageInserts = [];
    }
  }
  if (stageInserts.length > 0) {
    output.push(`INSERT IGNORE INTO stage_word (_openid, word_id, stage, mastery_order) VALUES ${stageInserts.join(',')};`);
  }

  fs.writeFileSync(OUTPUT_FILE, output.join('\n'));
  console.log(`SQL 文件已写入: ${OUTPUT_FILE}`);
  console.log(`总行数: ${output.length}`);
  console.log(`文件大小: ${(fs.statSync(OUTPUT_FILE).size / 1024 / 1024).toFixed(1)}MB`);
  
  db.close();
}

main();
