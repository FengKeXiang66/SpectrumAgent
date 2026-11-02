import { defineConfig, mergeConfig } from 'vite';
import config from '../../vite.config.ts';
export default mergeConfig(config, defineConfig({ base: '/ui/', build: {
  outDir: '.runtime/task12/browser-dist', rollupOptions: { input: '.runtime/task12/browser.html' }
} }));
