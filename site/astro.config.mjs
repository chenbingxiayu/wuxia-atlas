// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import { cpSync } from 'node:fs';

// 梁羽生武侠宇宙 · 江湖图志
// 架构决议见《网站完整设计方案》：SSG + 交互岛；版权闸门见 scripts/copyright_gate.py

// site/data 是构建管线（Python）的唯一输出目录；交互岛在运行时 fetch 它，
// 而 Astro 只原样发布 public/ —— 构建与开发启动时把 data/ 镜像进 public/data/
// （public/data 为生成物，见 .gitignore；单一事实源仍是 site/data）。
function copySiteData() {
  try {
    cpSync(new URL('./data', import.meta.url), new URL('./public/data', import.meta.url), {
      recursive: true,
    });
  } catch (e) {
    console.warn('[copy-site-data] site/data 尚不存在，跳过镜像：', e.message);
  }
  return { name: 'copy-site-data' };
}

const mirrorData = {
  name: 'copy-site-data',
  hooks: {
    'astro:build:start': copySiteData,
    'astro:dev:start': copySiteData,
  },
};

export default defineConfig({
  // GitHub Pages 项目站点（自定义域名/Cloudflare 时改为根路径并更新 site）
  site: 'https://chenbingxiayu.github.io',
  base: '/wuxia-atlas',
  trailingSlash: 'ignore',
  build: {
    inlineStylesheets: 'auto',
  },
  integrations: [react(), mirrorData],
});
