/// <reference types="vitest/config" />
import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  server: {
    port: 5173,
    // Behind Caddy the browser's host name reaches Vite; besides localhost, allow the Mac's
    // network name set by `make lan` (Vite blocks unknown hosts against DNS rebinding).
    allowedHosts: (process.env.VITE_ALLOWED_HOSTS ?? '')
      .split(',')
      .map((h) => h.trim())
      .filter(Boolean),
    // Behind Caddy in Docker the API is same-origin; for `npm run dev` on the host, proxy it.
    proxy: { '/api': process.env.VITE_API_PROXY ?? 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
    // JUNIT_DIR=../reports also writes a JUnit report for the feature catalog check.
    reporters: process.env.JUNIT_DIR
      ? ['default', ['junit', { suiteName: 'frontend-unit' }]]
      : ['default'],
    outputFile: process.env.JUNIT_DIR
      ? { junit: path.join(process.env.JUNIT_DIR, 'frontend-unit.xml') }
      : undefined,
  },
});
