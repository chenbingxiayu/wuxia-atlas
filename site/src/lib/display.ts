/**
 * 展示层（display）映射：canonical → display（display-canonical-v1，B-1/B-2 最后一步）。
 *
 * 数据来源：`site/data/entity-index.json` 的 `display` 字段（导出器已按
 * `registry/display_canonical.json` 落层：玄烨→康熙、朱由检→崇祯、福临→顺治、
 * 胤禛→雍正、哈玛雅→飞红巾；未登记条目 display==canonical 回落，不重复恒等映射）。
 *
 * 使用纪律：**只用于展示文案**；URL slug / 内部 key / 链接参数一律 canonical
 * （见 `@lib/display-shared` 的客户端版本 dsp/dspText/toCanonical）。
 */
import entityIndex from '@data/entity-index.json';
import type { DisplayMap } from './display-shared';
import { dspText as dspTextShared } from './display-shared';

export type { DisplayMap };

/** 构建期 canonical → display 映射（仅非恒等项；当前 5 条）。 */
function buildDisplayMap(): DisplayMap {
  const map: DisplayMap = {};
  const entities = (entityIndex as { entities?: Array<Record<string, unknown>> }).entities || [];
  for (const e of entities) {
    const canonical = e.c as string;
    const display = e.display as string;
    if (canonical && display && display !== canonical) map[canonical] = display;
  }
  return map;
}

/** 全站展示映射（构建期常量；仅含非恒等覆盖，当前 5 条）。 */
export const DISPLAY: DisplayMap = buildDisplayMap();

/** canonical → display；未登记则回落原名。展示处专用，禁止用于 URL/内部 key。 */
export function dsp(name: string | null | undefined): string {
  if (!name) return '';
  return DISPLAY[name] || name;
}

/** 文本批量替换展示名（长名优先）；用于数据内嵌文案（note/摘要/题库题干等）。 */
export function dspText(text: string | null | undefined): string {
  return dspTextShared(DISPLAY, text);
}
