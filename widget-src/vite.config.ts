import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

// 和队友 vite.widget.config.ts 一样，只是输出到本项目的 web/widget/
export default defineConfig({
  plugins: [react()],
  publicDir: false,
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: fileURLToPath(new URL('../web/widget', import.meta.url)),
    emptyOutDir: true,
    minify: true,
    lib: {
      entry: fileURLToPath(new URL('./src/entry.tsx', import.meta.url)),
      formats: ['es'],
      fileName: () => 'hafiller-widget.js',
      cssFileName: 'hafiller-widget',
    },
  },
});
