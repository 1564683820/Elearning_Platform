const sdk = require('@cloudbase/node-sdk');
const app = sdk.init({env:'test'});
const db = app.rdb();
const table = db.from('test');

console.log('table own props:', Object.getOwnPropertyNames(table));
console.log('table fetch:', typeof table.fetch);
console.log('table url:', table.url);
console.log('table url props:', Object.getOwnPropertyNames(table.url));

// Check the fetch function
if (typeof table.fetch === 'function') {
  console.log('fetch source:', table.fetch.toString().substring(0, 500));
}

// Check all properties recursively
for (const key of Object.getOwnPropertyNames(table)) {
  const val = table[key];
  if (typeof val === 'object' && val !== null) {
    console.log(`${key} keys:`, Object.getOwnPropertyNames(val));
  } else {
    console.log(`${key}:`, typeof val);
  }
}
