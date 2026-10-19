import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';

const product = JSON.parse(readFileSync(new URL('./src-tauri/tauri.conf.json', import.meta.url), 'utf8')) as { version: string };

export default defineConfig({
  plugins: [react()],
  define: { __SPECTRUM_PRODUCT_VERSION__: JSON.stringify(product.version) },
  optimizeDeps: { entries: ['index.html'] },
  server: {
    host: '127.0.0.1', port: 1420, strictPort: true,
    watch: { ignored: [/[\\/](?:\.venv|\.cargo-home|\.npm-cache|\.toolchains|artifacts|src-tauri|build)[\\/]/] },
  },
  clearScreen: false,
});
