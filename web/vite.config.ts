// Vite build configuration for the ParallaX web app (fully static, relative base).
// SI disclosure: written with the help of an SI coding assistant (Claude), checked by the team.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: './',
  plugins: [react()],
  build: { target: 'es2022', sourcemap: false },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
