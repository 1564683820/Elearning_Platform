#!/usr/bin/env node
/**
 * 分批提取核心词并生成小 SQL 文件
 * 每个 SQL 文件包含 50 条 INSERT，便于通过 CloudBase SQL API 逐批执行
 * 
 * 同时生成一个 Node.js 执行脚本，可自动逐批调用 CloudBase MCP API
 */

const fs = require('fs');
const path = require('path');

const SCRIPT_DIR = __dirname;
const DB_FILE = path.join(SCRIPT_DIR, 'ecdict-data', 'stardict.db');
const OUTPUT_DIR = path.join(SCRIPT_DIR, 'sql-batches');
const BATCH_SIZE = 50; // 每批50条

function escapeSql(str) {
  if (str === null || str === undefined) return "''";
  return "'" + String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\0/g, '\\0') + "'";
}

function generateSw(word) {
  return (word || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
}

function main() {
  // 创建输出目录
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  const Database = require('better-sqlite3');
  const db = new Database(DB_FILE, { readonly: true });

  // 先导入最核心的词：collins >= 4 或 (cet4 且 bnc <= 10000)
  // 分阶段：
  // Phase 1: bnc <= 2000 的超高频词（约2000条）- 启蒙到小五
  // Phase 2: collins >= 5 的柯林斯5星词（约600条）- 核心词
  // Phase 3: tag 含 cet4 且 bnc <= 10000（约3000条）- 四级
  // Phase 4: tag 含 cet6（约2000条）- 六级
  // Phase 5: tag 含 ielts（约3000条）- 雅思

  const phases = [
    { name: 'phase1-bnc2000', sql: `SELECT * FROM stardict WHERE bnc > 0 AND bnc <= 2000 ORDER BY bnc ASC` },
    { name: 'phase2-collins5', sql: `SELECT * FROM stardict WHERE collins = 5 AND bnc > 2000 ORDER BY bnc ASC` },
    { name: 'phase3-cet4', sql: `SELECT * FROM stardict WHERE tag LIKE '%cet4%' AND bnc > 2000 ORDER BY bnc ASC` },
    { name: 'phase4-cet6', sql: `SELECT * FROM stardict WHERE tag LIKE '%cet6%' AND tag NOT LIKE '%cet4%' ORDER BY bnc ASC` },
    { name: 'phase5-ielts', sql: `SELECT * FROM stardict WHERE tag LIKE '%ielts%' AND tag NOT LIKE '%cet4%' AND tag NOT LIKE '%cet6%' ORDER BY bnc ASC` },
    { name: 'phase6-gk', sql: `SELECT * FROM stardict WHERE (tag LIKE '%gk%' OR tag LIKE '%zk%') AND tag NOT LIKE '%cet4%' AND tag NOT LIKE '%cet6%' AND bnc > 2000 ORDER BY bnc ASC` },
    { name: 'phase7-collins3-4', sql: `SELECT * FROM stardict WHERE collins IN (3, 4) AND bnc > 2000 AND tag NOT LIKE '%cet4%' AND tag NOT LIKE '%cet6%' AND tag NOT LIKE '%ielts%' ORDER BY collins DESC, bnc ASC` },
  ];

  const manifest = { phases: [], totalBatches: 0 };

  for (const phase of phases) {
    console.log(`处理 ${phase.name}...`);
    const rows = db.prepare(phase.sql).all();
    console.log(`  ${phase.name}: ${rows.length} 条`);

    if (rows.length === 0) continue;

    const phaseDir = path.join(OUTPUT_DIR, phase.name);
    if (!fs.existsSync(phaseDir)) {
      fs.mkdirSync(phaseDir, { recursive: true });
    }

    let batchIdx = 0;
    let batchValues = [];

    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const word = (row.word || '').trim();
      if (!word) continue;

      const sw = generateSw(word);
      const values = [
        escapeSql(''),
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

      batchValues.push(`(${values.join(',')})`);

      if (batchValues.length >= BATCH_SIZE || i === rows.length - 1) {
        const sql = `INSERT IGNORE INTO dict_word (_openid, word, sw, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange, audio_url) VALUES ${batchValues.join(',')};`;
        const batchFile = path.join(phaseDir, `batch_${String(batchIdx).padStart(5, '0')}.sql`);
        fs.writeFileSync(batchFile, sql);
        batchIdx++;
        batchValues = [];
      }
    }

    manifest.phases.push({
      name: phase.name,
      count: rows.length,
      batches: batchIdx
    });
    manifest.totalBatches += batchIdx;
    console.log(`  ${phase.name}: ${batchIdx} 批`);
  }

  // 保存 manifest
  fs.writeFileSync(path.join(OUTPUT_DIR, 'manifest.json'), JSON.stringify(manifest, null, 2));
  console.log(`\n完成！共 ${manifest.totalBatches} 批`);
  console.log(`输出目录: ${OUTPUT_DIR}`);

  db.close();
}

main();
