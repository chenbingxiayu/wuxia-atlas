// @ts-check
import { defineConfig } from 'astro/config';

// 梁羽生武侠宇宙 · 江湖图志
// 架构决议见《网站完整设计方案》：SSG + 交互岛；版权闸门见 scripts（M1 接入 CI）
export default defineConfig({
  // GitHub Pages 项目站点（自定义域名/Cloudflare 时改为根路径并更新 site）
  site: 'https://chenbingxiayu.github.io',
  base: '/wuxia-atlas',
  trailingSlash: 'ignore',
  build: {
    inlineStylesheets: 'auto',
  },
});
