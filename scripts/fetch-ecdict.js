#!/usr/bin/env node
/**
 * 使用 Node.js fetch API 下载 ECDICT 并解压
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const SCRIPT_DIR = __dirname;
const DB_FILE = path.join(SCRIPT_DIR, 'stardict.db');
const ZIP_FILE = path.join(SCRIPT_DIR, 'ecdict-new.zip');
const ECDICT_URL = 'https://github.com/skywind3000/ECDICT/releases/download/1.0.28/ecdict-sqlite-28.zip';

function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

async function main() {
  // 检查是否已有 db
  if (fs.existsSync(DB_FILE)) {
    const stat = fs.statSync(DB_FILE);
    log(`stardict.db 已存在，大小: ${(stat.size / 1024 / 1024).toFixed(1)}MB`);
    return;
  }

  // 下载
  if (!fs.existsSync(ZIP_FILE)) {
    log('下载 ECDICT SQLite 数据库...');
    const resp = await fetch(ECDICT_URL, { redirect: 'follow' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const totalSize = parseInt(resp.headers.get('content-length') || '0', 10);
    log(`文件大小: ${(totalSize / 1024 / 1024).toFixed(1)}MB`);
    
    const buffer = Buffer.from(await resp.arrayBuffer());
    fs.writeFileSync(ZIP_FILE, buffer);
    log(`下载完成: ${ZIP_FILE} (${(buffer.length / 1024 / 1024).toFixed(1)}MB)`);
  }

  // 解压
  log('解压中...');
  const AdmZip = require('adm-zip');
  const zip = new AdmZip(ZIP_FILE);
  const entries = zip.getEntries();
  log(`ZIP 内文件: ${entries.map(e => e.entryName).join(', ')}`);
  zip.extractAllTo(SCRIPT_DIR, true);
  log('解压完成!');

  // 验证
  if (fs.existsSync(DB_FILE)) {
    const stat = fs.statSync(DB_FILE);
    log(`成功！stardict.db 大小: ${(stat.size / 1024 / 1024).toFixed(1)}MB`);
  } else {
    const dbFiles = fs.readdirSync(SCRIPT_DIR).filter(f => f.endsWith('.db'));
    log(`未找到 stardict.db，目录中的 .db 文件: ${dbFiles.join(', ')}`);
    if (dbFiles.length === 1) {
      fs.renameSync(path.join(SCRIPT_DIR, dbFiles[0]), DB_FILE);
      log(`已重命名 ${dbFiles[0]} -> stardict.db`);
    }
  }
}

main().catch(e => {
  log(`错误: ${e.message}`);
  process.exit(1);
});
