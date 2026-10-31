# -*- coding: utf-8 -*-
"""校订上下文提取器：为全部 medium/low 叙事层事件生成 ±170 字宽上下文。

用法：python scripts/extract_curation_contexts.py [书名]   （默认 白发魔女传）

输出（kb/<书>/校订/）：
  核心-◉▲○◇.txt   — 核心动词类，主对话内由 LLM 逐条分析
  ◈-1.txt .. ◈-N.txt — 交战类按 curation_batch_size（默认 200）均分为 N 批，子代理逐条分析
每块格式：
  ### E{id} | {loc} | {码}{动词} | 启发 主=X 宾=Y | {conf}
  {上下文}
id 为 medium/low 叙事层事件在稳定顺序下的序号，apply_curation.py 按同一顺序回填。
"""
import io, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_event_table as bet  # noqa: E402  （其模块级已配置 UTF-8 stdout）

if len(sys.argv) > 1:
    bet.BOOK = sys.argv[1]
OUT_DIR = os.path.join(bet.ROOT, "kb", bet.BOOK, "校订")
CTX = 170

CFG = {}
_cfg = os.path.join(bet.ROOT, "kb", bet.BOOK, "pipeline配置.json")
if os.path.exists(_cfg):
    import json
    CFG = json.load(open(_cfg, encoding='utf-8'))
BATCH_SIZE = CFG.get("curation_batch_size", 200)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    reg, events, stats = bet.extract()
    ml = [e for e in events if not e["in_quote"]
          and e["confidence"] in ("medium", "low")]
    print(f"medium/low narrative events: {len(ml)}")

    core = [e for e in ml if e["verb_code"] != "◈"]
    wu = [e for e in ml if e["verb_code"] == "◈"]

    def dump(path, subset):
        with open(path, 'w', encoding='utf-8') as f:
            for e in subset:
                s = max(0, e["_vs"] - CTX)
                t = min(len(e["_line"]), e["_ve"] + CTX)
                ctx = bet.clean_excerpt(e["_line"][s:t])
                f.write(f"### E{e['_eid']} | {e['loc']} | {e['verb_code']}{e['verb']} "
                        f"| 启发 主={e['subject'] or '—'} 宾={e['object'] or '—'} "
                        f"| {e['confidence']}\n{ctx}\n\n")

    for i, e in enumerate(ml):
        e["_eid"] = i
    core = [e for e in ml if e["verb_code"] != "◈"]
    wu = [e for e in ml if e["verb_code"] == "◈"]
    dump(os.path.join(OUT_DIR, "核心-◉▲○◇.txt"), core)
    n = max(1, (len(wu) + BATCH_SIZE - 1) // BATCH_SIZE)
    per = (len(wu) + n - 1) // n
    for k in range(n):
        chunk = wu[k * per:(k + 1) * per]
        if chunk:
            dump(os.path.join(OUT_DIR, f"◈-{k+1}.txt"), chunk)
            print(f"◈-{k+1}.txt: {len(chunk)} events")
    print(f"core file: {len(core)} events -> 核心-◉▲○◇.txt")


if __name__ == '__main__':
    main()
