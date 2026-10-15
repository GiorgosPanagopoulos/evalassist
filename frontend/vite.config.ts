/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Το backend τρέχει χωριστά στο dev. Ο proxy κρατά frontend και API
// same-origin, όπως και πίσω από το portal, ώστε το session cookie να
// στέλνεται χωρίς CORS.
const apiProxy = { '/api': 'http://127.0.0.1:8000' }

export default defineConfig({
  // Σχετικά paths στα assets: το build δουλεύει κάτω από οποιοδήποτε
  // subpath (π.χ. /evalassist/) χωρίς να ξέρει το prefix.
  base: './',
  plugins: [react(), tailwindcss()],
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
})
