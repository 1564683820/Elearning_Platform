const fs = require('fs');
const path = require('path');

const SCRIPT_DIR = __dirname;
const ZIP_FILE = path.join(SCRIPT_DIR, 'ecdict-sqlite-28.zip');
const DB_FILE = path.join(SCRIPT_DIR, 'stardict.db');

async function main() {
  if (fs.existsSync(DB_FILE)) {
    const stat = fs.statSync(DB_FILE);
    console.log(`stardict.db 已存在，大小: ${(stat.size / 1024 / 1024).toFixed(1)}MB`);
    return;
  }

  if (!fs.existsSync(ZIP_FILE)) {
    console.log('错误: ecdict-sqlite-28.zip 不存在');
    process.exit(1);
  }

  const stat = fs.statSync(ZIP_FILE);
  console.log(`ZIP 文件大小: ${(stat.size / 1024 / 1024).toFixed(1)}MB`);

  console.log('正在解压...');
  
  try {
    const AdmZip = require('adm-zip');
    const zip = new AdmZip(ZIP_FILE);
    const entries = zip.getEntries();
    console.log(`ZIP 内文件: ${entries.map(e => e.entryName).join(', ')}`);
    zip.extractAllTo(SCRIPT_DIR, true);
    console.log('解压完成!');
  } catch (e) {
    console.log(`adm-zip 解压失败: ${e.message}`);
    process.exit(1);
  }

  // 验证
  if (fs.existsSync(DB_FILE)) {
    const dbStat = fs.statSync(DB_FILE);
    console.log(`解压成功！stardict.db 大小: ${(dbStat.size / 1024 / 1024).toFixed(1)}MB`);
  } else {
    const dbFiles = fs.readdirSync(SCRIPT_DIR).filter(f => f.endsWith('.db'));
    console.log(`未找到 stardict.db，目录中的 .db 文件: ${dbFiles.join(', ')}`);
    // 如果有其他 db 文件，尝试重命名
    if (dbFiles.length === 1) {
      const src = path.join(SCRIPT_DIR, dbFiles[0]);
      fs.renameSync(src, DB_FILE);
      console.log(`已重命名 ${dbFiles[0]} -> stardict.db`);
    }
  }
}

main().catch(e => {
  console.error('错误:', e.message);
  process.exit(1);
});
