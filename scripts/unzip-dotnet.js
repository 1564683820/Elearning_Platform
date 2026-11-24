#!/usr/bin/env node
/**
 * 使用 Node.js 内置 zlib 解压 ZIP 文件
 * 不依赖 adm-zip，使用 child_process 调用 PowerShell .NET API
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const SCRIPT_DIR = __dirname;
const DB_FILE = path.join(SCRIPT_DIR, 'stardict.db');

function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

function main() {
  if (fs.existsSync(DB_FILE)) {
    const stat = fs.statSync(DB_FILE);
    log(`stardict.db 已存在，大小: ${(stat.size / 1024 / 1024).toFixed(1)}MB`);
    return;
  }

  // 列出目录中的 ZIP 文件
  const zipFiles = fs.readdirSync(SCRIPT_DIR).filter(f => f.endsWith('.zip'));
  log(`可用的 ZIP 文件: ${zipFiles.join(', ')}`);

  if (zipFiles.length === 0) {
    log('错误：没有 ZIP 文件');
    process.exit(1);
  }

  // 找到 ecdict zip 文件
  const zipName = zipFiles.find(f => f.includes('ecdict')) || zipFiles[0];
  const zipPath = path.join(SCRIPT_DIR, zipName);
  const stat = fs.statSync(zipPath);
  log(`使用 ZIP 文件: ${zipName} (${(stat.size / 1024 / 1024).toFixed(1)}MB)`);

  // 使用 PowerShell .NET API 解压
  log('使用 .NET API 解压...');
  const psScript = `
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead('${zipPath.replace(/\\/g, '\\\\')}')
foreach ($entry in $zip.Entries) {
    Write-Host "Found: $($entry.Name) ($($entry.Length) bytes)"
    if ($entry.Name -like '*.db') {
        $destPath = Join-Path '${SCRIPT_DIR.replace(/\\/g, '\\\\')}' $entry.Name
        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destPath, $true)
        Write-Host "Extracted: $($entry.Name)"
    }
}
$zip.Dispose()
`;

  const tmpPs = path.join(SCRIPT_DIR, '_extract.ps1');
  fs.writeFileSync(tmpPs, psScript);
  
  try {
    execSync(`powershell -ExecutionPolicy Bypass -File "${tmpPs}"`, { stdio: 'inherit', timeout: 120000 });
  } catch (e) {
    log(`PowerShell 解压失败: ${e.message}`);
  }
  
  // 清理临时脚本
  try { fs.unlinkSync(tmpPs); } catch(e) {}

  // 验证
  if (fs.existsSync(DB_FILE)) {
    const dbStat = fs.statSync(DB_FILE);
    log(`解压成功！stardict.db 大小: ${(dbStat.size / 1024 / 1024).toFixed(1)}MB`);
  } else {
    const dbFiles = fs.readdirSync(SCRIPT_DIR).filter(f => f.endsWith('.db'));
    log(`目录中的 .db 文件: ${dbFiles.join(', ')}`);
  }
}

main();
