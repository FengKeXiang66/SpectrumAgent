import { defineConfig, mergeConfig } from 'vite';
import config from '../../vite.config.ts';
export default mergeConfig(config, defineConfig({ base: '/ui/', build: {
  outDir: '.runtime/task13/ui-dist', rollupOptions: { input: '.runtime/task13/ui.html' }
} }));
