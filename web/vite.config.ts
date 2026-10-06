/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { chunkSizeWarningLimit: 700 }, // single-page app; most of the size is the chart library
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], globals: true },
})
