import { cp, readFile, writeFile, rename } from 'node:fs/promises';
import { dirname } from 'node:path';
import { spawn } from 'node:child_process';
const [fixture, path, phase] = process.argv.slice(2);
if (phase === 'slow_setup') await new Promise(r => setTimeout(r, 20000));
await cp(`/opt/fixtures/${fixture}`, '/work/repo', { recursive: true });
let source = `/work/repo/${path}`;
if (phase === 'patched') await writeFile(source, (await readFile(source, 'utf8')).replace('< maximum', '<= maximum'));
if (source.endsWith('.tsx')) { await rename(source, source.replace(/tsx$/, 'ts')); source = source.replace(/tsx$/, 'ts'); }
if (phase === 'slow_test') await new Promise(r => setTimeout(r, 20000));
const check = spawn('node', ['/opt/toolchain/node_modules/typescript/bin/tsc', '--noEmit', '--strict', '--target', 'es2022', '--module', 'nodenext', '--moduleResolution', 'nodenext', source], { stdio: 'inherit', env: { PATH: process.env.PATH } });
const typeExit = await new Promise(resolve => check.on('exit', resolve));
if (typeExit !== 0) process.exit(typeExit ?? 1);
console.log('Trusted TypeScript strict check passed');
const child = spawn('node', ['--experimental-strip-types', '/opt/harness/node_check.mjs', dirname(source)], { stdio: 'inherit', env: { PATH: process.env.PATH } });
child.on('exit', code => process.exit(code ?? 1));
