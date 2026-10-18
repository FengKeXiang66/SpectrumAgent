import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  optimizeDeps: { entries: ['index.html'] },
  server: {
    host: '127.0.0.1', port: 1420, strictPort: true,
    watch: { ignored: [/[\\/](?:\.venv|\.cargo-home|\.npm-cache|\.toolchains|artifacts|src-tauri|build)[\\/]/] },
  },
  clearScreen: false,
});
