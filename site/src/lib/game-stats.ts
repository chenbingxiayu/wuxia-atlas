/**
 * game-stats —— 游戏战绩中心数据层（游戏页设计 §一决策 7 / §六 F3，任务 E1）。
 * 契约（localStorage 键 jianghu-stats-v1，纯前端，不上传）：
 *   {
 *     daily:  { plays, wins, curStreak, bestStreak, days: [YYYYMMDD...] },  // 每日一谜
 *     twenty: { plays, wins, curStreak, bestStreak, days: [YYYYMMDD...] },  // 二十问答
 *     cal?:   { [YYYYMMDD]: { d?: 'w'|'l', t?: 'w'|'l' } }                  // 附加：日历逐日结果（每日/二十最后结算），仅 hover 展示用
 *   }
 * 写入时机：仅在各游戏「结算」时（每日一谜 win/lose 落定；二十问答 猜对=胜 / 系统认输=负）各记一局。
 * 兼容：旧 wuxia-daily 每日存档不迁移——战绩自战绩中心上线起算（UI 注记）。
 * days 去重升序、上限 730 条；cal 只留近 90 日（防 localStorage 无界增长）。
 */

export const STATS_KEY = 'jianghu-stats-v1';

export type GameKey = 'daily' | 'twenty';

export type GameStats = {
  plays: number;
  wins: number;
  curStreak: number;
  bestStreak: number;
  days: string[]; // YYYYMMDD 去重升序
};

export type JianghuStats = {
  daily: GameStats;
  twenty: GameStats;
  cal?: Record<string, { d?: 'w' | 'l'; t?: 'w' | 'l' }>;
};

const MAX_DAYS = 730;
const MAX_CAL = 90;

export function emptyStats(): JianghuStats {
  const g = (): GameStats => ({ plays: 0, wins: 0, curStreak: 0, bestStreak: 0, days: [] });
  return { daily: g(), twenty: g(), cal: {} };
}

export function todayKey(d = new Date()): string {
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
}

/** 近 n 天（含今日）的 YYYYMMDD 升序数组——日历格用 */
export function lastNDays(n: number, end = new Date()): string[] {
  const out: string[] = [];
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(end.getFullYear(), end.getMonth(), end.getDate() - i);
    out.push(todayKey(d));
  }
  return out;
}

function fillGame(x: unknown): GameStats {
  const g = emptyStats().daily;
  const o = (x && typeof x === 'object') ? x as Record<string, unknown> : {};
  const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : 0);
  g.plays = num(o.plays);
  g.wins = Math.min(num(o.wins), g.plays); // 不变式：wins ≤ plays
  g.curStreak = num(o.curStreak);
  g.bestStreak = num(o.bestStreak);
  g.days = Array.isArray(o.days)
    ? [...new Set(o.days.filter((d): d is string => typeof d === 'string' && /^\d{8}$/.test(d)))].sort().slice(-MAX_DAYS)
    : [];
  return g;
}

/** 安全读取：损坏/缺字段/隐私模式一律回退空档，不抛错 */
export function readStats(): JianghuStats {
  const base = emptyStats();
  try {
    const raw = localStorage.getItem(STATS_KEY);
    if (!raw) return base;
    const o = JSON.parse(raw);
    if (!o || typeof o !== 'object') return base;
    const root = o as Record<string, unknown>;
    const out: JianghuStats = {
      daily: fillGame(root.daily),
      twenty: fillGame(root.twenty),
    };
    if (root.cal && typeof root.cal === 'object') {
      const cal: JianghuStats['cal'] = {};
      const keys = Object.keys(root.cal as object)
        .filter((k) => /^\d{8}$/.test(k))
        .sort()
        .slice(-MAX_CAL);
      for (const k of keys) {
        const v = (root.cal as Record<string, Record<string, unknown>>)[k] || {};
        const e: { d?: 'w' | 'l'; t?: 'w' | 'l' } = {};
        if (v.d === 'w' || v.d === 'l') e.d = v.d;
        if (v.t === 'w' || v.t === 'l') e.t = v.t;
        if (e.d || e.t) cal[k] = e;
      }
      out.cal = cal;
    }
    return out;
  } catch {
    return base;
  }
}

function writeStats(s: JianghuStats) {
  try {
    localStorage.setItem(STATS_KEY, JSON.stringify(s));
  } catch { /* 隐私模式等：静默放弃，游戏本体不受影响 */ }
}

/**
 * 记一局结算：plays+1；win→wins+1/连胜+1（刷新最佳）否则连胜清零；当日入 days（去重）。
 * 同时更新 cal 当日该游戏最后结算结果（w/l，日历 hover 用）。
 * 读-改-写整体 try 包裹：任何一步失败都不影响调用方（游戏结算流程零依赖本函数结果）。
 */
export function recordResult(game: GameKey, win: boolean, day = todayKey()): JianghuStats {
  const s = readStats();
  const g = s[game];
  g.plays += 1;
  if (win) {
    g.wins += 1;
    g.curStreak += 1;
    if (g.curStreak > g.bestStreak) g.bestStreak = g.curStreak;
  } else {
    g.curStreak = 0;
  }
  if (!g.days.includes(day)) {
    g.days.push(day);
    g.days.sort();
    if (g.days.length > MAX_DAYS) g.days = g.days.slice(-MAX_DAYS);
  }
  const cal = s.cal || (s.cal = {});
  const e = (cal[day] ||= {});
  if (game === 'daily') e.d = win ? 'w' : 'l';
  else e.t = win ? 'w' : 'l';
  const calKeys = Object.keys(cal).sort();
  if (calKeys.length > MAX_CAL) for (const k of calKeys.slice(0, calKeys.length - MAX_CAL)) delete cal[k];
  writeStats(s);
  return s;
}
