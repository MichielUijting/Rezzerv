import { build } from 'esbuild';
import { mkdir, copyFile } from 'node:fs/promises';
await mkdir('dist', { recursive: true });
await Promise.all(['index.html', 'style.css'].map(name => copyFile(name, 'dist/' + name)));
await build({ entryPoints: ['app.mjs'], bundle: true, format: 'esm', platform: 'browser', outfile: 'dist/app.js' });
