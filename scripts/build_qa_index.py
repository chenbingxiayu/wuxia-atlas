# -*- coding: utf-8 -*-
"""spec 001 T5：QA 预索引（build_qa_index.py）。

从 atlas 切片（persons/bychap/events）构建 person → {chaps, events, places} 索引，
供问答 killer/versus/行踪模板查表求解（替代运行时全量扫书）。

输出：site/data/qa-index.json（L0：定位符+结构化事实）。
W0-T3b（天山演示版总体方案 §1.2，2026-11-08）新增 --scope：
  - --scope <profile>：书目 = state.json 书目 ∩ scope，persons/chaps/places/events 按书过滤，
    qa-events/<书>.json 只产 scope 书（qa-index 书目上限仍随 atlas/state.json——其陈旧性见任务报告）；
  - 不带 --scope：全量口径，行为与现状一致（meta 无 scope 键，方案 R6）。
W2-B10（天山演示版总体方案 §4.2，2026-11-11）：qa-events/<书>.json 书目全覆盖——
  无事件层书（散花女侠/联剑风云录/冰魄寒光剑：D03/EX-5 未上线，atlas 切片 events={}）
  写空文件 {"book", "events": [], "gap": true}（不伪造事件），meta.field_gaps 声明缺口
  （EX-7「冰魄 events={} + field_gaps」同款纪律）；QaExplorer 按 events_files 逐书 fetch，
  空数组天然兼容。
W2-D12（qa-events 3 书真事件接入，2026-11-12）：缺旧事件表的书（atlas 切片无事件行）
  改读 wuxia-kb/registry/events/<书>.json（D03 新事件层 event-v1）适配成旧行 schema
  {l,v,a,b,code,book}——旧表存在的书保持旧路径（两源并存不迁移，白发魔女传等虽在
  registry 也有事件文件但不覆盖）；过滤纪律对齐旧产物（gate=excluded 丢弃 ≈ 旧 dropped、
  review 保留 ≈ 旧 in_quote/单侧行；非互动族 T05/07/08/09/12/13 不入——行语义=人物间
  作用行，行踪职能在 qa-index persons），映射细节见 registry_event_rows 与
  tests/test_qa_events_registry.py。接入后 3 书不再 gap，meta.field_gaps 随之收窄/清空。
用法：python scripts/build_qa_index.py [--scope tianshan-demo] [--apply]
  --apply：显式确认真跑（本脚本恒直写 site/data、无 dry-run——同 run_pipeline 切片脚本语义，
  传与不传行为一致）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import SITE_DATA, today  # noqa: E402

# W0-T3b：scope 基础设施复用（export_site_common 在 wuxia-kb/scripts，import 胜过复制）
_WXKB_SCRIPTS = Path(__file__).resolve().parents[1] / 'wuxia-kb' / 'scripts'
if str(_WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WXKB_SCRIPTS))
import export_site_common as esc  # noqa: E402

ATLAS = SITE_DATA / "atlas"
# W2-D12：D03 新事件层（event-v1）——缺旧事件表的书从这接（旧表书保持旧路径，两源并存不迁移）
REG_EVENTS = Path(__file__).resolve().parents[1] / "wuxia-kb" / "registry" / "events"


def select_titles(state, scope=None):
    """state.json books → 待索引书名列表（保持顺序；scope 口径取 book ∈ scope 子集）。"""
    titles = []
    for entry in state.get("books", []):
        title = entry.get("title")
        if title and esc.in_scope(title, scope):
            titles.append(title)
    return titles


def index_slices(pairs):
    """[(书名, atlas 切片)] → (persons 索引, 已索引书数)。

    persons[name] = {"chaps": {书: [回]}, "events": [行], "places": {地名: {书: 首回}}}；
    纯函数（不含文件 IO），书目集合由调用方 select_titles 保证。
    """
    persons: dict[str, dict] = {}
    book_count = 0
    for title, sl in pairs:
        book_count += 1
        for name, p in (sl.get("persons") or {}).items():
            rec = persons.setdefault(name, {"chaps": {}, "events": [], "places": {}})
            chaps = sorted({int(c) for c in (p.get("chaps") or [])})
            rec["chaps"][title] = chaps
        for chap, bc in (sl.get("bychap") or {}).items():
            chap_i = int(chap)
            for pname in bc.get("p") or []:
                rec = persons.setdefault(pname, {"chaps": {}, "events": [], "places": {}})
                chaps = rec["chaps"].setdefault(title, [])
                if chap_i not in chaps:
                    chaps.append(chap_i)
                    chaps.sort()
            for pl in bc.get("l") or []:
                rec = persons.setdefault(pname, {"chaps": {}, "events": [], "places": {}})
                slots = rec["places"].setdefault(pl, {})
                slots[title] = min(slots.get(title, 999), chap_i)
        for chap, evs in (sl.get("events") or {}).items():
            for e in evs or []:
                row = {"l": e.get("l"), "v": e.get("v"), "a": e.get("a"), "b": e.get("b"),
                       "code": e.get("code"), "book": title}
                for who in (e.get("a"), e.get("b")):
                    if who:
                        persons.setdefault(who, {"chaps": {}, "events": [], "places": {}})["events"].append(row)
    return persons, book_count


def slim_index(persons, real_of, gaz_names):
    """persons → 轻索引 {name: {chaps, places}}（spec 011 T26 行踪去噪：places 仅 gazetteer 收录）。"""
    out_persons = {}
    for name, rec in persons.items():
        places = sorted(
            ({"name": n, "first": f"{b}·{c:03d}", "real": real_of.get(n)}
             for n, slots in rec["places"].items()
             if n in gaz_names  # spec 011 T26：非地名噪声过滤（保留 gazetteer 全部收录，含虚构 4 处）
             for b, c in sorted(slots.items(), key=lambda kv: kv[1])[:1]),
            key=lambda x: (x["first"],),
        )
        out_persons[name] = {
            "chaps": {b: sorted(c) for b, c in sorted(rec["chaps"].items())},
            "places": places,
        }
    return out_persons


def split_events(persons):
    """persons 事件按书拆分 + 完全重复行去重 → ({书: rows}, 去重删除数)。

    去重：同一事件行经「参与者×」聚合（a、b 各 append 一次）会成倍复制；atlas 切片自身
    偶有重复行。按整行（l/v/a/b/code/book）精确去重——镜像行（a/b 互换）是独立记录，
    保留，交由 versus 模板双向匹配语义处理。
    """
    by_book: dict[str, list] = {}
    dedup_dropped = 0
    for book in {r["book"] for rec in persons.values() for r in rec["events"]}:
        rows = [r for rec in persons.values() for r in rec["events"] if r["book"] == book]
        seen: set[str] = set()
        uniq: list[dict] = []
        for r in rows:
            k = json.dumps(r, ensure_ascii=False, sort_keys=True)
            if k in seen:
                continue
            seen.add(k)
            uniq.append(r)
        dedup_dropped += len(rows) - len(uniq)
        by_book[book] = uniq
    return by_book, dedup_dropped


def dedup_rows(rows):
    """行列表整行精确去重（同 split_events 口径：完全重复去 1，镜像行保留）。"""
    seen: set[str] = set()
    uniq: list[dict] = []
    for r in rows:
        k = json.dumps(r, ensure_ascii=False, sort_keys=True)
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


# W2-D12：registry event-v1 → 旧 qa-events 行 schema 适配（映射与过滤纪律固化于
# tests/test_qa_events_registry.py）。
# code 降级映射：旧 5 类 verb_code 家族中 4 类在新 T13 分类下有明确延续
# （◈交战↔T01 比武较技 / ◉杀伐↔T02 生死杀伐 / ◇传艺↔T04 拜师传艺 / ○拜认结盟↔T06 结盟背盟）；
# 旧 ▲擒控 无对应新类型（擒拿动词已归 T01）——延续不到的互动族回落新源 verb_domain 符号。
REG_TYPE_CODE = {"T01": "◈", "T02": "◉", "T04": "◇", "T06": "○"}
# qa-events 行语义 = 人物间作用事件族（旧事件表同构，killer/versus 可消费）；
# 非互动族不入：T05 练功（独修）/T07 门派/T08 朝廷/T09 战争（组织级）/T12 行踪（职能在
# qa-index persons）/T13 大会（容器聚合，本就无锚动词）。
REG_INTERACTION_TYPES = {"T01", "T02", "T03", "T04", "T06", "T10", "T11"}


def registry_norm_loc(loc):
    """registry loc "001:002"（段号 3 位补零）→ 旧产物 loc 格式 "001:2"（段号不补零）。

    旧产物（kb 事件表→atlas 切片）loc 段号从不补零；前端 QaExplorer parseInt(e.l,10)
    取回号、答案卡显示 书·l——格式不一致会让回链/展示漂移。
    """
    chap, _, para = loc.partition(":")
    return f"{int(chap):03d}:{int(para)}"


def registry_event_rows(title, payload):
    """registry/events event-v1 payload → 旧 qa-events 行列表（{l,v,a,b,code,book}）。

    过滤纪律对齐旧产物（build_atlas_slices 消费 kb 事件表的口径）：
      - gate=excluded（R1 无参与方 / R3 非事实叙述）→ 丢弃 ≈ 旧 dropped/verdict=drop 不入切片
        （旧产物 0 双空行）；
      - gate=review（R2 单方降级 / R4 对白内）→ 保留 ≈ 旧产物保留单侧空行与 in_quote 行
        （白发 247 条非 drop in_quote 中 216 条在旧 qa-events 在案）；
      - anchor_verbs 空（T13 容器聚合行）→ 丢弃（无动词锚 → 无 v）；
      - 双侧参与者皆空 → 丢弃（旧产物无双空行）。
    字段映射：l=loc（段号去补零）；v=anchor_verbs[].verb（逐动词成行，实测 1 事件 1 锚动词）；
      a=subject（空则 施者 参与者）；b=object（空则 受者 参与者；单侧参与→另一侧 null）；
      code=REG_TYPE_CODE[type]（旧家族延续），延续不到的互动族回落锚动词 verb_domain 符号
      （降级映射）；book=书名（scope 书名，行落 qa-events/<书>.json）。
    """
    rows: list[dict] = []
    if payload.get("schema") != "event-v1":
        return rows
    for e in payload.get("events", []):
        if e.get("gate") == "excluded":
            continue
        anchors = e.get("anchor_verbs") or []
        if not anchors or e.get("type") not in REG_INTERACTION_TYPES:
            continue
        parts = e.get("participants") or []
        a = e.get("subject") or next((p.get("name") for p in parts if p.get("role") == "施者"), None) or None
        b = e.get("object") or next((p.get("name") for p in parts if p.get("role") == "受者"), None) or None
        if not a and not b:
            continue
        for av in anchors:
            code = REG_TYPE_CODE.get(e.get("type")) or av.get("domain") or e.get("verb_domain")
            rows.append({"l": registry_norm_loc(e["loc"]), "v": av.get("verb"),
                         "a": a, "b": b, "code": code, "book": title})
    return dedup_rows(rows)


def merge_registry_gaps(by_book, titles, reg_dir=REG_EVENTS):
    """W2-D12：atlas 切片无事件的书（旧事件表缺）→ registry/events/<书>.json 新源适配补入。

    两源并存不迁移：atlas 有事件行的书（旧 4 书）保持旧路径不动——白发魔女传等虽在
    registry 也有事件文件，本函数一律不覆盖（仅补 by_book 缺失的书）。
    返回 [(书名, 补入行数)]（按 titles 序；registry 文件缺失/schema 不符的书静默跳过，
    交由 plan_event_files 维持 gap 占位纪律）。
    """
    filled = []
    for title in titles:
        if title in by_book:
            continue
        fp = reg_dir / f"{title}.json"
        if not fp.exists():
            continue
        payload = json.loads(fp.read_text(encoding="utf-8"))
        rows = registry_event_rows(title, payload)
        if rows:
            by_book[title] = rows
            filled.append((title, len(rows)))
    return filled


def plan_event_files(by_book, titles):
    """qa-events/<书>.json 书目全覆盖（W2-B10）→ (events_files 条目列表, 无事件层书列表)。

    有事件书：{"book", "file", "events": 行数}；无事件层书（atlas 切片 events={}——
    D03/EX-5 未上线）：{"book", "file", "events": 0, "gap": True}，调用方写空文件占位
    （不伪造事件），meta.field_gaps 声明缺口。titles 顺序即输出顺序（scope 口径=配置序）。
    """
    entries, gaps = [], []
    for title in titles:
        rows = by_book.get(title)
        if rows is None:
            gaps.append(title)
            entries.append({"book": title, "file": f"qa-events/{title}.json", "events": 0, "gap": True})
        else:
            entries.append({"book": title, "file": f"qa-events/{title}.json", "events": len(rows)})
    return entries, gaps


def build_meta(book_count, slim, events_files, scope=None, gaps=None):
    """qa-index meta（scope 口径 meta 加 scope/books；有缺口时加 field_gaps）。

    注意：qa-index 旧契约 meta.books = 已索引书数（int）；scope 口径按方案 §1.2 统一契约
    books = scope 书目列表（前端无 meta.books 消费方；书数可由 len(books) 推出）。
    field_gaps = 无事件层书（W2-B10：events 占位空文件，不伪造；EX-7 同款纪律）。
    """
    meta = {"schema": "qa-index-v2", "generated": today(), "books": book_count,
            "persons": len(slim), "events_files": events_files,
            "note": "事件按书拆分 qa-events/<书>.json（按需 fetch）；本文件仅 chaps/places 轻索引"}
    if gaps:
        meta["field_gaps"] = list(gaps)
    smeta = esc.scope_meta(scope)
    if smeta:
        meta.update(smeta)
        meta["books"] = list(smeta["books"])  # 统一契约：scope 口径 books=书目列表（覆盖计数）
    return meta


def main() -> int:
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    state = json.loads((ATLAS / "state.json").read_text(encoding="utf-8"))
    gaz = json.loads((SITE_DATA / "gazetteer.json").read_text(encoding="utf-8"))
    real_of = {p["name"]: p.get("real") for p in gaz.get("places", [])}
    gaz_names = {p["name"] for p in gaz.get("places", [])}

    titles = select_titles(state, scope)
    pairs = []
    for title in titles:
        fp = ATLAS / f"{title}.json"
        if fp.exists():
            pairs.append((title, json.loads(fp.read_text(encoding="utf-8"))))
    persons, book_count = index_slices(pairs)

    # spec 002 T3：事件按书拆分（qa-events/<书>.json），qa-index.json 只留 chaps/places 轻索引
    # W2-B10：书目全覆盖——无事件层书写 gap 空文件占位（不伪造事件，meta.field_gaps 声明）
    # W2-D12：缺旧事件表的书改读 registry/events 新源适配补入（旧表书保持旧路径；接入后无 gap）
    by_book, dedup_dropped = split_events(persons)
    reg_filled = merge_registry_gaps(by_book, titles)
    ev_dir = SITE_DATA / "qa-events"
    ev_dir.mkdir(parents=True, exist_ok=True)
    events_files, gaps = plan_event_files(by_book, titles)
    for e in events_files:
        payload = {"book": e["book"]}
        if e.get("gap"):
            payload["gap"] = True
            payload["events"] = []
            payload["note"] = "事件层未上线（D03/EX-5 未接管本书）：空占位不伪造事件；上线后由管线重建"
        else:
            payload["events"] = by_book[e["book"]]
        (ev_dir / f"{e['book']}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    slim = slim_index(persons, real_of, gaz_names)
    out = {"meta": build_meta(book_count, slim, events_files, scope, gaps=gaps), "persons": slim}
    fp_out = SITE_DATA / "qa-index.json"
    fp_out.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    size_kb = fp_out.stat().st_size / 1024
    ev_total = sum(f["events"] for f in events_files)
    scope_note = f"（scope={scope['profile']}）" if scope is not None else ""
    gap_note = f"；无事件层 gap 占位 {'、'.join(gaps)}（meta.field_gaps）" if gaps else ""
    reg_note = (f"；registry 新源接入 {len(reg_filled)} 书"
                + (f"（{'、'.join(f'{b} {n} 条' for b, n in reg_filled)}）" if reg_filled else ""))
    print(f"-> {fp_out} ({size_kb:.0f} KB) · books={book_count} · persons={len(slim)} · "
          f"事件 {ev_total} 条拆 {len(events_files)} 文件（去重删除 {dedup_dropped} 条完全重复行）"
          f"{reg_note}{gap_note}{scope_note}")
    if size_kb > 2048:
        print("⚠ 仍超 2MB——需再拆")
    return 0


if __name__ == "__main__":
    sys.exit(main())
