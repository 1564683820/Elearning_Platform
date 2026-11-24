#!/usr/bin/env node
/**
 * ECDICT 下载脚本
 * 单独运行此脚本下载 ECDICT SQLite 数据库并解压
 * 
 * 用法：node download-ecdict.js
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');
const { pipeline } = require('stream/promises');

const ECDICT_URL = 'https://github.com/skywind3000/ECDICT/releases/download/1.0.28/ecdict-sqlite-28.zip';
const SCRIPT_DIR = __dirname;
const ZIP_FILE = path.join(SCRIPT_DIR, 'ecdict-sqlite-28.zip');
const DB_FILE = path.join(SCRIPT_DIR, 'stardict.db');

function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

async function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    let redirectCount = 0;
    
    function doRequest(requestUrl) {
      if (redirectCount++ > 10) {
        reject(new Error('Too many redirects'));
        return;
      }
      
      const mod = requestUrl.startsWith('https') ? https : http;
      const request = mod.get(requestUrl, { timeout: 600000 }, (response) => {
        if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
          log(`重定向到: ${response.headers.location}`);
          doRequest(response.headers.location);
          return;
        }
        if (response.statusCode !== 200) {
          reject(new Error(`HTTP ${response.statusCode}`));
          return;
        }
        const totalSize = parseInt(response.headers['content-length'], 10);
        let downloaded = 0;
        let lastPct = -1;
        response.on('data', (chunk) => {
          downloaded += chunk.length;
          if (totalSize) {
            const pct = Math.floor((downloaded / totalSize) * 100);
            if (pct !== lastPct && pct % 5 === 0) {
              lastPct = pct;
              log(`下载进度: ${pct}% (${(downloaded / 1024 / 1024).toFixed(1)}MB / ${(totalSize / 1024 / 1024).toFixed(1)}MB)`);
            }
          }
        });
        response.pipe(file);
        file.on('finish', () => {
          file.close();
          log(`下载完成: ${dest} (${(downloaded / 1024 / 1024).toFixed(1)}MB)`);
          resolve();
        });
      });
      
      request.on('error', (err) => {
        fs.unlink(dest, () => {});
        reject(err);
      });
      
      request.on('timeout', () => {
        request.destroy();
        reject(new Error('Request timeout'));
      });
    }
    
    doRequest(url);
  });
}

async function main() {
  if (fs.existsSync(DB_FILE)) {
    log(`SQLite 文件已存在: ${DB_FILE}`);
    const stat = fs.statSync(DB_FILE);
    log(`文件大小: ${(stat.size / 1024 / 1024).toFixed(1)}MB`);
    return;
  }
  
  // 下载
  if (!fs.existsSync(ZIP_FILE)) {
    log(`下载 ECDICT SQLite 数据库...`);
    log(`URL: ${ECDICT_URL}`);
    await downloadFile(ECDICT_URL, ZIP_FILE);
  } else {
    log(`ZIP 文件已存在: ${ZIP_FILE}`);
  }
  
  // 解压
  log('解压中...');
  try {
    execSync(`powershell -Command "Expand-Archive -Path '${ZIP_FILE}' -DestinationPath '${SCRIPT_DIR}' -Force"`, { stdio: 'inherit' });
    log('解压完成');
  } catch (e) {
    log('PowerShell 解压失败，尝试 tar...');
    try {
      execSync(`tar -xf "${ZIP_FILE}" -C "${SCRIPT_DIR}"`, { stdio: 'inherit' });
      log('解压完成');
    } catch (e2) {
      log('自动解压失败，请手动解压 ecdict-sqlite-28.zip 到 scripts/ 目录');
      log(`解压后应该得到 stardict.db 文件`);
      process.exit(1);
    }
  }
  
  // 验证
  if (fs.existsSync(DB_FILE)) {
    const stat = fs.statSync(DB_FILE);
    log(`解压成功！stardict.db 大小: ${(stat.size / 1024 / 1024).toFixed(1)}MB`);
  } else {
    log('错误：解压后未找到 stardict.db');
    const files = fs.readdirSync(SCRIPT_DIR).filter(f => f.endsWith('.db'));
    if (files.length > 0) {
      log(`找到的 .db 文件: ${files.join(', ')}`);
      log('请将正确的文件重命名为 stardict.db');
    }
    process.exit(1);
  }
}

main().catch(e => {
  log(`错误: ${e.message}`);
  console.error(e);
  process.exit(1);
});
