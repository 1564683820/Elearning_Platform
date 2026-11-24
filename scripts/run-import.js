#!/usr/bin/env node
'use strict';

/**
 * 自动导入脚本：读取 JSON 批次文件，通过云函数导入到 MySQL
 * 
 * 用法: node run-import.js [--phase phase1] [--start 0] [--end 5]
 * 
 * 注意：此脚本需要 CloudBase 访问令牌才能调用云函数
 * 可通过 CloudBase CLI 或 HTTP API 调用
 */

const fs = require('fs');
const path = require('path');
const https = require('https');

const ENV_ID = process.env.TCB_ENV_ID || 'cloud1-d0g0f3q7g8d2bb58f';
const FUNC_NAME = 'import-dict';

// 解析参数
const args = process.argv.slice(2);
let phase = 'phase1';
let startBatch = 0;
let endBatch = Infinity;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--phase' && args[i + 1]) { phase = args[i + 1]; i++; }
  else if (args[i] === '--start' && args[i + 1]) { startBatch = parseInt(args[i + 1], 10); i++; }
  else if (args[i] === '--end' && args[i + 1]) { endBatch = parseInt(args[i + 1], 10); i++; }
}

const batchDir = path.join(__dirname, 'json-batches', phase);
if (!fs.existsSync(batchDir)) {
  console.error(`Batch directory not found: ${batchDir}`);
  console.error('Run gen-json-batches.js first to generate batch files.');
  process.exit(1);
}

const files = fs.readdirSync(batchDir)
  .filter(f => f.endsWith('.json'))
  .sort()
  .filter((_, idx) => idx >= startBatch && idx < endBatch);

console.log(`Found ${files.length} batch files in ${batchDir}`);
console.log(`Processing batches ${startBatch} to ${Math.min(endBatch, files.length + startBatch) - 1}`);

// 输出每个批次的 JSON 数据，供手动通过 MCP 工具导入
for (const file of files) {
  const filePath = path.join(batchDir, file);
  const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  const batchIdx = parseInt(file.replace('batch_', '').replace('.json', ''), 10);
  
  // 输出批次摘要
  console.log(`\nBatch ${batchIdx}: ${data.length} records`);
  console.log(`  First word: ${data[0]?.word}`);
  console.log(`  Last word: ${data[data.length - 1]?.word}`);
  console.log(`  File: ${filePath}`);
}
