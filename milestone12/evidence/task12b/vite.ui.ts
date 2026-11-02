import { defineConfig, mergeConfig } from 'vite';
import config from '../../vite.config.ts';
export default mergeConfig(config, defineConfig({ base: '/ui/', build: {
  outDir: '.runtime/task12b/ui-dist', rollupOptions: { input: '.runtime/task12b/ui.html' },
} }));
