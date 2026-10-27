import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Forward chatbot requests to the Python backend (backend/server.py)
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
