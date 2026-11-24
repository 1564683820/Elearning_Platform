const sdk = require('@cloudbase/node-sdk');

async function main() {
  const app = sdk.init({env:'test'});

  // Check models API
  console.log('=== models ===');
  console.log('models type:', typeof app.models);
  const modelKeys = Object.getOwnPropertyNames(app.models);
  console.log('models own props:', modelKeys);

  const proto = Object.getPrototypeOf(app.models);
  const protoKeys = Object.getOwnPropertyNames(proto).filter(k => typeof proto[k] === 'function');
  console.log('models proto methods:', protoKeys);

  // Check rdb
  const db = app.rdb();
  const table = db.from('dict_word');
  console.log('\n=== rdb table ===');
  console.log('table url:', table.url.toString());

  // Check what HTTP methods are available via fetch
  console.log('\n=== fetch source ===');
  const fetchSrc = table.fetch.toString().substring(0, 1000);
  console.log(fetchSrc);
}

main().catch(console.error);
