#!/usr/bin/env node
'use strict';

const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');

const DB_PATH = path.join(__dirname, 'ecdict-data', 'stardict.db');
const OUTPUT_DIR = path.join(__dirname, 'json-batches', 'phase1');
const BATCH_SIZE = 30;

function generateSW(word) {
  return (word || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
}

const db = new Database(DB_PATH, { readonly: true });

const sql = `SELECT word, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange 
FROM stardict 
WHERE bnc != '' AND CAST(bnc AS INTEGER) > 0 AND CAST(bnc AS INTEGER) <= 2000 
ORDER BY CAST(bnc AS INTEGER) ASC`;

const rows = db.prepare(sql).all();
console.log(`Found ${rows.length} records`);

const importRows = rows.map(r => ({
  word: (r.word || '').substring(0, 128),
  sw: generateSW(r.word),
  phonetic: (r.phonetic || '').substring(0, 128),
  definition: r.definition || '',
  translation: r.translation || '',
  pos: (r.pos || '').substring(0, 64),
  collins: parseInt(r.collins) || 0,
  oxford: parseInt(r.oxford) || 0,
  tag: (r.tag || '').substring(0, 128),
  bnc: parseFloat(r.bnc) || 0,
  frq: parseFloat(r.frq) || 0,
  exchange: r.exchange || '',
}));

fs.mkdirSync(OUTPUT_DIR, { recursive: true });

let batchCount = 0;
for (let i = 0; i < importRows.length; i += BATCH_SIZE) {
  const batch = importRows.slice(i, i + BATCH_SIZE);
  const fileName = `batch_${String(batchCount).padStart(4, '0')}.json`;
  fs.writeFileSync(path.join(OUTPUT_DIR, fileName), JSON.stringify(batch));
  batchCount++;
}

console.log(`Generated ${batchCount} batches in ${OUTPUT_DIR}`);
db.close();
