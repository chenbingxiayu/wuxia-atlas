/**
 * 群目/组合实体黑名单（spec 001 T1）——战绩卡、谜题、穿帮雷达 R1 三处共用同一口径。
 * 群目 = 以集体名义出现在事件层的非个人实体：军队/机构/弟子群/侠团/帮会。
 * 纪律：群目不参与个人战绩展示、不进谜题死者、不进 R1 核验清单（朝廷机构侧走门派志另册）。
 */
const GROUP_LABELS: ReadonlySet<string> = new Set([
  // 兵员泛称
  '清兵', '清军', '清军水师', '明军', '官兵', '官军', '满洲军队', '满洲军', '神策营',
  // 机构/宫廷
  '锦衣卫', '御林军', '禁卫军', '大内', '大内卫士', '清宫', '血滴子',
  // 弟子/随从群
  '武当弟子', '少林弟子', '峨嵋弟子', '众人', '侍卫', '卫士',
  // 侠团/帮会（组合实体，非个人）
  '关东四侠', '江南七侠', '桑家三妖', '五龙帮', '铁扇帮',
]);

/** 是否群目/组合实体（不可作为个人战绩、谜题死者、R1 核验对象）。 */
export function isGroupLabel(name: unknown): boolean {
  return typeof name === 'string' && GROUP_LABELS.has(name.trim());
}

/** 通用过滤：按给定键剔除群目行（服务端 Astro / 客户端均可）。 */
export function filterOutGroups<T>(rows: T[], keyOf: (row: T) => unknown): T[] {
  return rows.filter((r) => !isGroupLabel(keyOf(r)));
}
