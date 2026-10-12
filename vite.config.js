import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({
  root: 'web',
  base: '/assets/',
  plugins: [react(), tailwindcss()],
  build: {outDir: '../popcorn_sr/static', emptyOutDir: true, assetsDir: 'bundles'},
});
