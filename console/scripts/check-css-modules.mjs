// CSS Module 类名自检：确保每个 styles.xxx / styles['xxx'] 引用的类在对应 .module.css 中真实存在。
// 这类错误 tsc 不报，只在运行时得到 undefined（表现为「样式丢失」），因此需要独立校验。
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const files = [];
(function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (/\.(tsx|ts)$/.test(entry.name)) files.push(full);
  }
})(join(root, 'src'));

let problems = 0;
for (const file of files) {
  const src = readFileSync(file, 'utf8');
  const importRe = /import\s+(\w+)\s+from\s+'([^']+\.module\.css)'/g;
  let m;
  while ((m = importRe.exec(src))) {
    const varName = m[1];
    const cssPath = resolve(dirname(file), m[2]);
    if (!existsSync(cssPath)) {
      console.log(`MISSING CSS FILE  ${relative(root, file)} -> ${m[2]}`);
      problems += 1;
      continue;
    }
    const css = readFileSync(cssPath, 'utf8');
    const defined = new Set([...css.matchAll(/\.([A-Za-z_][\w-]*)/g)].map((x) => x[1]));

    const used = new Set();
    const useRe = new RegExp(`${varName}\\.([A-Za-z_][\\w]*)`, 'g');
    let u;
    while ((u = useRe.exec(src))) used.add(u[1]);
    const bracketRe = new RegExp(`${varName}\\['([^']+)'\\]`, 'g');
    while ((u = bracketRe.exec(src))) used.add(u[1]);

    for (const cls of used) {
      if (!defined.has(cls)) {
        console.log(`UNDEFINED CLASS   ${relative(root, file)}  ${varName}.${cls}`);
        problems += 1;
      }
    }

    // 动态拼接引用：styles[`sevbar_${item.severity}`] / styles[MODE_CLASS[x]]
    const dynRe = new RegExp(`${varName}\\[` + '`([A-Za-z_]+)\\$\\{', 'g');
    while ((u = dynRe.exec(src))) {
      const prefix = u[1];
      if (![...defined].some((x) => x.startsWith(prefix))) {
        console.log(`UNDEFINED PREFIX  ${relative(root, file)}  ${varName}[\`${prefix}...\`]`);
        problems += 1;
      }
    }
  }
}

console.log(
  problems === 0
    ? 'CSS Module 类名引用全部有定义 ✅'
    : `CSS Module 检查发现 ${problems} 个问题 ❌`,
);
process.exit(problems === 0 ? 0 : 1);
