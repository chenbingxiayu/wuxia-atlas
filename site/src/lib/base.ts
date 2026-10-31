// 统一内部链接前缀：GitHub Pages 项目站点部署在 /wuxia-atlas/ 子路径下，
// 所有内部链接必须经 B 前缀（Astro base 不会自动改写 href——见《网站完整设计方案》风险表）。
const RAW = import.meta.env.BASE_URL || '/';
export const B = RAW.endsWith('/') ? RAW : RAW + '/';
