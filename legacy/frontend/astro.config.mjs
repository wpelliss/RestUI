import { defineConfig } from 'astro/config';
import node from '@astrojs/node';
import svelte from '@astrojs/svelte';
import tailwind from '@astrojs/tailwind';

export default defineConfig({
  // SSR obligatoire : toutes les pages ont prerender: false (données live depuis le backend).
  // Un build statique est incompatible avec ce design — les données changent à chaque requête.
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  integrations: [
    svelte(),
    tailwind(),
  ],
  vite: {
    server: {
      proxy: {
        // En dev : les fetches client vers /api/* sont proxifiés vers le backend FastAPI.
        // En prod : Caddy route /api/* → backend, le frontend n'est pas impliqué.
        '/api': {
          target: process.env.BACKEND_URL ?? 'http://localhost:8000',
          changeOrigin: true,
          // Les routes backend sont montées sous /api/* — pas de réécriture de path.
        },
      },
    },
  },
});
