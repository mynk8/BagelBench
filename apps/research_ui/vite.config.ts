import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'
export default defineConfig({
 plugins:[react(),tailwindcss()], resolve:{alias:{'@':fileURLToPath(new URL('./src',import.meta.url))}},
 server:{port:5173,proxy:Object.fromEntries(['/api','/images','/videos'].map(path=>[path,{target:'http://127.0.0.1:8000',changeOrigin:false}]))},
 test:{environment:'jsdom',globals:true,restoreMocks:true},
})
