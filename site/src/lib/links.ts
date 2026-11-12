/**
 * 链接目标解析（构建期）：所有站内 href 必须先经本模块解析为 **canonical / 已存在页面**，
 * 展示文案再经 `@lib/display` 的 `dsp()` 处理——避免三类 404：
 *   1) display 当 URL（如 康熙/飞红巾/顺治）；
 *   2) 别名/变体当 URL（如 允祯→胤禛、晦明禅师→岳鸣珂、董鄂妃→董小宛）；
 *   3) 引用对象本身没有页面（群称/地名/组织，如 清兵/罗军/罗布族）→ 返回 null，页面改纯文本。
 *
 * 数据来源（构建期只读）：site/data 的 dossiers/arts/sects/weapons/books/chapters。
 * 纪律：本模块只决定“链到哪/是否可链”，不改数据、不改展示层。
 */
import dossiersJson from '@data/dossiers.json';
import artsJson from '@data/arts.json';
import sectsJson from '@data/sects.json';
import weaponsJson from '@data/weapons.json';
import booksJson from '@data/books.json';
import chaptersJson from '@data/chapters.json';
import { isMainDossier } from '@lib/scope';

const D = (dossiersJson as any).dossiers as any[];
const ARTS = (artsJson as any).arts as any[];
const SECTS = (sectsJson as any).sects as any[];
const WEAPONS = (weaponsJson as any).weapons as any[];
const BOOKS = (booksJson as any).books as any[];
const CHAPTERS = chaptersJson as any;

function buildPersonMap(): Map<string, string> {
  const m = new Map<string, string>();
  // 第一遍：canonical 优先占位（任何同名别名不得覆盖真正的人名）
  for (const d of D) if (d?.canonical && !m.has(d.canonical)) m.set(d.canonical, d.canonical);
  // 第二遍：display / 别名（仅在未被 canonical 占用时登记）
  for (const d of D) {
    const names = [d.display, d.display_name, ...((d.aliases || []).map((a: any) => a.alias))];
    for (const n of names) {
      if (typeof n === 'string' && n && !m.has(n)) m.set(n, d.canonical);
    }
  }
  return m;
}

const PERSON = buildPersonMap();

/** 人物名（canonical/display/别名/变体）→ 有档案页的 canonical；无页返回 null。
 *  W0-T5 存目守卫（方案 §2.3）：dossiers 现为主档口径，且 canonical 须经
 *  @lib/scope isMainDossier 复核（entity-index page=false → null，页面渲染纯文本+定位符）。 */
export function personTarget(name: unknown): string | null {
  if (typeof name !== 'string') return null;
  const n = name.trim();
  if (!n) return null;
  const canon = PERSON.get(n) || null;
  return canon && isMainDossier(canon) ? canon : null;
}

/** 是否是有档案页的人物（供“存在才链接”判断）。 */
export function hasPerson(name: unknown): boolean {
  return personTarget(name) !== null;
}

function buildNameMap(items: any[], aliasesOf: (x: any) => unknown[] = () => []): Map<string, string> {
  const m = new Map<string, string>();
  for (const x of items) if (x?.canonical && !m.has(x.canonical)) m.set(x.canonical, x.canonical);
  for (const x of items) {
    for (const a of aliasesOf(x)) {
      if (typeof a === 'string' && a && !m.has(a)) m.set(a, x.canonical);
    }
  }
  return m;
}

const ART = buildNameMap(ARTS, (a) => a.aliases || []);
const WEAPON = buildNameMap(WEAPONS, (w) => w.aliases || []);
const SECT = new Map<string, string>();
for (const s of SECTS) if (s?.canonical) SECT.set(s.canonical, s.canonical);

/** 武功名（含别名/变体）→ 有武功页的 canonical；无页返回 null。 */
export function artTarget(name: unknown): string | null {
  if (typeof name !== 'string' || !name.trim()) return null;
  return ART.get(name.trim()) || null;
}

/** 神兵名（含别名）→ 有名物页的 canonical；无页返回 null。 */
export function weaponTarget(name: unknown): string | null {
  if (typeof name !== 'string' || !name.trim()) return null;
  return WEAPON.get(name.trim()) || null;
}

/** 门派名 → 有门派页的 canonical；无页（如“少林寺” vs 数据“少林”）返回 null。 */
export function sectTarget(name: unknown): string | null {
  if (typeof name !== 'string' || !name.trim()) return null;
  return SECT.get(name.trim()) || null;
}

const LIT_BOOKS = new Map<string, any>();
for (const b of BOOKS) if (b?.book) LIT_BOOKS.set(b.book, b);

/** 已点亮作品名 → 自身；未点亮/缺佚（如《挑灯看剑录》）返回 null。 */
export function bookTarget(name: unknown): string | null {
  if (typeof name !== 'string' || !name.trim()) return null;
  return LIT_BOOKS.has(name.trim()) ? name.trim() : null;
}

function chapterNoOf(loc: unknown): number | null {
  if (typeof loc === 'number' && Number.isFinite(loc)) return Math.trunc(loc);
  if (typeof loc !== 'string') return null;
  const m = loc.trim().match(/\d+/);
  if (!m) return null;
  const n = parseInt(m[0], 10);
  return Number.isFinite(n) ? n : null;
}

const CHAP_SET = new Map<string, Set<number>>();
for (const [book, v] of Object.entries(CHAPTERS)) {
  if (book === 'meta') continue;
  const list = (v as any)?.chapters;
  if (Array.isArray(list)) CHAP_SET.set(book, new Set(list.map((c: any) => c.no)));
}

/** (书, 定位符/章号) → 存在章页的 3 位章号（"003"/"000"）；不存在返回 null。 */
export function chapterNo(book: unknown, loc: unknown): string | null {
  const b = bookTarget(book);
  if (!b) return null;
  const n = chapterNoOf(loc);
  if (n === null || n < 0) return null;
  const set = CHAP_SET.get(b);
  if (!set || !set.has(n)) return null;
  return String(n).padStart(3, '0');
}

import { B } from '@lib/base';

/**
 * (书, 定位符) → 回目页 URL（含 base 与尾斜杠）；章页不存在返回 null。
 * 全站唯一回目链接实现（spec 001 R1）——islands 内不得手拼 parseInt 版本，
 * 无法 import 本模块时（如按需 fetch 场景）以内联同式 helper 并注释互指。
 */
export function chapterHref(book: unknown, loc: unknown): string | null {
  const ch = chapterNo(book, loc);
  const b = bookTarget(book);
  return ch && b ? `${B}books/${encodeURIComponent(b)}/${ch}/` : null;
}
