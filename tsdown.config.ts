import { defineConfig } from 'tsdown'

export default defineConfig({
  entry: ['src/index.ts'],
  format: 'esm',
  outDir: 'dist',
  clean: true,
  platform: 'node',
  target: 'node24',
  // GitHub Actions expects dist/index.js, not .mjs
  outExtensions: ({ format, pkgType }) => ({ js: '.js' }),
})
