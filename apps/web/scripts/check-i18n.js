const fs = require('fs');
const path = require('path');

const locales = ['en', 'ta', 'hi'];
const messagesDir = path.join(__dirname, '..', 'messages');

function getKeys(obj, prefix = '') {
  let keys = [];
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      keys = keys.concat(getKeys(value, fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  return keys;
}

const loaded = {};
for (const locale of locales) {
  const filePath = path.join(messagesDir, `${locale}.json`);
  if (!fs.existsSync(filePath)) {
    console.error(`Missing locale file: ${filePath}`);
    process.exit(1);
  }
  loaded[locale] = JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

const enKeys = new Set(getKeys(loaded.en));
let hasError = false;

for (const locale of ['ta', 'hi']) {
  const locKeys = new Set(getKeys(loaded[locale]));
  for (const key of enKeys) {
    if (!locKeys.has(key)) {
      console.error(`[${locale}] Missing translation key: ${key}`);
      hasError = true;
    }
  }
}

if (hasError) {
  console.error('i18n key validation failed.');
  process.exit(1);
} else {
  console.log(`All ${enKeys.size} i18n keys present across all locales.`);
}
