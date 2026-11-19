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
    // .temp / .runtime hold agent scratch trees (multi-GB pytest temp dirs). Watching them
    // costs thousands of chokidar handles and has hung the dev server's optimizer outright.
    watch: { ignored: [/[\\/](?:\.venv|\.cargo-home|\.npm-cache|\.toolchains|\.temp|\.runtime|artifacts|src-tauri|build)[\\/]/] },
  },
  clearScreen: false,
});
