# -*- coding: utf-8 -*-
"""用 qwen3.8-27B 外部 API 重新标注《白发魔女传》第一回（实验，不写入 kb/tagged）。

流程：原文按段落切块 → 逐块调 LLM 插标 → difflib 对齐把标记机械回锚到原文
（保证剥标后与原文逐字一致）→ 拼装 YAML+围栏 → 自检。
"""
import difflib
import json
import os
import re
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "_qwen_标注对比")
RAW_DIR = os.path.join(OUT_DIR, "raw")
ORIG_PATH = os.path.join(ROOT, "章回版", "白发魔女传",
                         "001　第一回　铁矢神弓　少年扶巨宦　金鞍宝马　大盗震虚声.txt")
DST_PATH = os.path.join(OUT_DIR, "001_第一回.tagged.md")

API_URL = "https://tbqqujafrvwvmxmc.polylink.org/v1/chat/completions"
HEADERS = {
    "Content-Type": "application/json",
    "CF-Access-Client-Id": "8fb9e43ab389ffad0cf5a0d83ec98a11.access",
    "CF-Access-Client-Secret": "cfast_Wg36l0A3lpvELtx3ouhLd8O3pdretH8y6lpdGnOl6736bdcd",
    "Authorization": "Bearer 8bFbhnBPK0vcnGxvZD1SaR66otAZb7R7yZ60CkE9Woh+3C0YewDqHghXpi0rCpYd",
}
MODEL = "qwen3.8-27B"
CHUNK_BUDGET = 2800
MAX_RETRIES = 3

TAG_RE = re.compile(r"(〖[^〖〗]*〗|⟦[^⟦⟧]*⟧)")


def tag_surface(tok):
    inner = tok[1:-1]
    surf = inner[1:]
    if "|" in surf:
        surf = surf.split("|")[0]
    return surf


SYSTEM_PROMPT = """你是武侠小说知识库的专业标注员。任务：把用户给出的小说正文逐字誊写一遍，只在其中插入标注标记。

## 输出硬规则（违反即废稿）
1. 除插入的标记外，一字不增、一字不减、一字不改：标点、弯引号“”、全角符号必须原样保留。
2. 实体标记用全角方头括号：〖类型码 文本〗；动词标记：⟦动词码 词⟧。标记第一个字符是类型码，标记内的文本必须与原文字符完全一致。
3. 标记必须成对闭合、不得嵌套；实体与动词互不重叠。
4. 只输出标注后的正文；不要任何解释、不要 markdown 代码围栏、不要标题。

## 实体类型码（白名单，不得用其他字符）
@ 人物：真名、法号、绰号（指向单人）；史实人物同样标
= 地点：山川、关驿、城镇、府衙、区域名（中原/塞外/回疆/陕北/川陕…）；方位词（东北/西北/陕南/川东）也标；X家/X府用作处所（到/在/追到铁家）时标
◆ 组织：门派、帮会、镖局、官署、军队、政权、朝代、固定首领集体（武当派、龙门帮、锦衣卫、明朝、满洲、武当五老）
; 职衔称谓：官职、江湖职衔、门中辈分；亲属名词仅限归因结构（"儿子名唤卓继贤"中的儿子、"孙儿名卓一航"中的孙儿）；对话称呼不标
% 时间：纪年年号、时令、锚定时间线的时长（明万历四十三年、黄昏、五更、深秋、两年）
☆ 武功：有专名的功法/招式/身法/掌法，及武林通名技艺（铁沙掌、分筋错骨、轻功）
• 兵器宝物：专名兵器、暗器、宝物（蛇焰箭、猫儿绿宝珠）；淬毒暗器、药材原料也归此
§ 丹药：制炼成品药物（丹/丸/散/膏/药酒/药末/迷香/解药）
+ 坐骑灵兽专名（照夜狮子）
[ 秘籍文书：武学秘笈、剑谱、兵书、书信、遗书

## 动词类型码
◉ 杀伐：施行了的杀死/处决/残害（杀、斩、结果）
◈ 交战：施行了的打斗/比武核心动词（打、刺、进攻、杀败、击倒、打伤、抓、扑、劈）
○ 拜认结盟：拜师、收徒、结义、结盟
▲ 擒控：擒、捉、点（穴）、点倒、震住
◇ 传艺：传授、教、指点、相传

## 管道规则（重要）
一切非规范形的人物名都挂规范名管道：〖@别名|规范名〗。适用：绰号（玉罗刹|练霓裳、火灵猿|朱宝椿、翻山虎|周同、鹰爪王|归有章）、庙号尊称（神宗|朱翊钧）、短名代称（黄叶|黄叶道人）。surface 本身已是实名/规范名时不加管道。

## 不标清单（宁缺勿滥）
- 泛称与描写性代称：白马少年、虬髯汉子、矮胖老头、老镖头、女魔头、群盗、众人、红面老人
- 对话称呼语：耿兄、贤弟、老大人、练女侠、老人家、归老大
- 通名与泛量词：剑、刀、弹弓、银两、手下、弟子们、快马
- 未施行的动词（假设/命令/意图）："把他打死了""快点杀了我吧""斗她一斗"不标；已施行的追述照标
- 防御与移动微动作：挡、避、闪、退、接、冲、跃、跳、退
- 比喻/惯用法：打量、打个照面
- 书信内容文字不标

## 动词操作规则
每个冲突单元只标 1–2 个核心动词；击杀委婉语照标（结果、送你见阎王——仅叙述者使用时）。

## 标注密度参考
主干叙述每段 3–10 处；人物 @ 占大头。类型拿不准就不标（漏标可回填，错标污染下游）。

## 示例（摘自本书第二回，仅示范格式）
原文：但宫中卫士众多，那少年虽然厉害，被十余人围攻，也惭惭支持不住。王照希正看得出神，忽听得有人叫道：“喂，你为什么不上去呀！”这人乃是锦衣卫的一个指挥，王照希躲闪不及，和他打了个照面。
标注后：但宫中卫士众多，那少年虽然厉害，被十余人围攻，也惭惭支持不住。〖@王照希〗正看得出神，忽听得有人叫道：“喂，你为什么不上去呀！”这人乃是〖◆锦衣卫〗的一个〖;指挥〗，〖@王照希〗躲闪不及，和他⟦◈打⟧了个照面。

原文：过了几天，风波渐息。柳西铭交游颇广，听在宫中当差的人传来的消息，神宗皇帝又把宫中的执事太监庞保、刘成杀了。
标注后：过了〖%几天〗，风波渐息。〖@柳西铭〗交游颇广，听在宫中当差的人传来的消息，〖@神宗|朱翊钧〗皇帝又把宫中的执事太监〖@庞保〗、〖@刘成〗⟦◉杀⟧了。"""

# 示例中的半角引号仅为提示词排版，正文硬规则仍以原文弯引号为准（示例已按原文改写）


def call_llm(chunk_text, idx, total):
    user = (f"以下是《白发魔女传》第一回的第 {idx}/{total} 块正文。请按系统规则输出标注后的正文，"
            f"只输出正文本身：\n\n{chunk_text}")
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "top_p": 0.8,
        "max_tokens": 8000,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.time()
        try:
            # 流式：读超时只约束相邻字节间隔，长生成不会被总时长砍断
            r = requests.post(API_URL, headers=HEADERS, json=payload,
                              timeout=(60, 120), stream=True)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            parts = []
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                delta = json.loads(data)["choices"][0].get("delta", {})
                c = delta.get("content")
                if c:
                    parts.append(c)
            if not parts:
                raise RuntimeError("空响应")
            print(f"  [chunk {idx}] ok {time.time()-t0:.0f}s {sum(map(len,parts))} 字",
                  flush=True)
            return "".join(parts)
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  [chunk {idx}] attempt {attempt} failed: {e}", flush=True)
            time.sleep(5 * attempt)
    raise RuntimeError(f"chunk {idx} 全部重试失败: {last_err}")


def clean_output(text):
    """去掉代码围栏与 <think> 残留。"""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    m = re.search(r"```(?:markdown|md|text)?\n(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    return text.strip("\n")


def parse_tags(text):
    """返回 (plain, [(token, start_in_plain)])，plain 中标记已替换为其 surface。"""
    parts, tags, i = [], [], 0
    for m in TAG_RE.finditer(text):
        parts.append(text[i:m.start()])
        tags.append((m.group(0), sum(len(p) for p in parts)))
        parts.append(tag_surface(m.group(0)))
        i = m.end()
    parts.append(text[i:])
    return "".join(parts), tags


def reanchor(orig, model_text):
    """把模型输出里的标记回锚到 orig 上，返回 (tagged_orig, n_tags, n_dropped, plain_diff_ratio)。"""
    plain, tags = parse_tags(model_text)
    sm = difflib.SequenceMatcher(a=plain, b=orig, autojunk=False)
    fwd = {}
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal":
            for d in range(a2 - a1):
                fwd[a1 + d] = b1 + d
    insertions, dropped = [], []
    cursor = 0
    for tok, s in tags:
        surf = tag_surface(tok)
        L = len(surf)
        ostart = None
        if (s + L - 1) in fwd and s in fwd:
            if fwd[s + L - 1] - fwd[s] == L - 1 and orig[fwd[s]:fwd[s] + L] == surf:
                ostart = fwd[s]
        if ostart is None:
            j = orig.find(surf, cursor)
            if j >= 0:
                ostart = j
        if ostart is None:
            dropped.append(tok)
            continue
        insertions.append((ostart, ostart + L, tok))
        cursor = ostart + L
    insertions.sort()
    out, pos, n = [], 0, 0
    for a, b, tok in insertions:
        if a < pos:
            dropped.append(tok)
            continue
        out.append(orig[pos:a]); out.append(tok); pos = b; n += 1
    out.append(orig[pos:])
    ratio = difflib.SequenceMatcher(None, plain, orig).ratio()
    return "".join(out), n, len(dropped), ratio


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(ORIG_PATH, encoding="utf-8") as f:
        lines = f.read().split("\n")

    # 结构定位
    idx_title = 0
    idx_tiao = next(i for i, l in enumerate(lines) if l.startswith("——调寄"))
    idx_zheng = next(i for i, l in enumerate(lines) if l.startswith("正是："))
    narr = list(range(idx_title + 2, idx_zheng - 1))  # 叙事正文段（跳过标题/词/空行）
    narr = [i for i in narr if lines[i].strip()]

    # 切块：段落为最小单元，按字数预算合并
    chunks, cur, cur_len = [], [], 0
    for i in narr:
        L = len(lines[i])
        if cur and cur_len + L > CHUNK_BUDGET:
            chunks.append(cur); cur, cur_len = [], 0
        cur.append(i); cur_len += L
    if cur:
        chunks.append(cur)
    print(f"叙事段 {len(narr)} 个，切分为 {len(chunks)} 块 "
          f"(每块≈{sum(len(lines[i]) for i in narr)//len(chunks)} 字)", flush=True)

    tagged_by_idx, stats, failed = {}, [], []
    for ci, idxs in enumerate(chunks, 1):
        raw_path = os.path.join(RAW_DIR, f"chunk_{ci:02d}.txt")
        if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
            with open(raw_path, encoding="utf-8") as f:
                raw = f.read()
            print(f"  [chunk {ci}] 复用已有 raw（断点续跑）")
        else:
            chunk_text = "\n\n".join(lines[i] for i in idxs)
            try:
                raw = call_llm(chunk_text, ci, len(chunks))
            except RuntimeError as e:
                print(f"  [chunk {ci}] 跳过：{e}", flush=True)
                failed.append(ci)
                continue
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(raw)
        cleaned = clean_output(raw)
        # 块内逐段回锚（空行分隔）
        model_paras = cleaned.split("\n\n")
        if len(model_paras) != len(idxs):
            print(f"  [chunk {ci}] 段落数不匹配 model={len(model_paras)} orig={len(idxs)}，整块对齐")
            model_paras = [cleaned]
            orig_paras = [chunk_text]
        else:
            orig_paras = [lines[i] for i in idxs]
        for pi, (mp, op) in enumerate(zip(model_paras, orig_paras)):
            tagged, n, nd, ratio = reanchor(op, mp)
            stats.append((ci, pi, n, nd, ratio))
            if len(model_paras) == len(idxs):
                tagged_by_idx[idxs[pi]] = tagged
            else:
                # 整块对齐：按顺序映射回原段
                parts = tagged.split("\n\n")
                for k, ii in enumerate(idxs):
                    if k < len(parts):
                        tagged_by_idx[ii] = parts[k]
        n_t = sum(s[2] for s in stats if s[0] == ci)
        n_d = sum(s[3] for s in stats if s[0] == ci)
        print(f"  [chunk {ci}] 回锚标记 {n_t}，丢弃 {n_d}", flush=True)

    # 拼装
    out = ["---", "book: 白发魔女传", "chapter: 1",
           f"title: {lines[idx_title]}", 
           f"source: 章回版/白发魔女传/{os.path.basename(ORIG_PATH)}",
           "schema: wuxia-tagged-v0.2", "annotator: qwen3.8-27B-api", "---"]
    for i, ln in enumerate(lines):
        if ln.startswith("正是："):
            out.append("::: 回末")
        out.append(tagged_by_idx.get(i, ln))
        if i == idx_tiao:
            out.append(":::")
    while out and not out[-1].strip():
        out.pop()
    out.append(":::")
    text = "\n".join(out) + "\n"
    with open(DST_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    total = sum(s[2] for s in stats); drop = sum(s[3] for s in stats)
    print(f"\n写入 {DST_PATH}", flush=True)
    print(f"标记总数 {total}，丢弃 {drop}，平均相似度 "
          f"{sum(s[4] for s in stats)/len(stats):.4f}", flush=True)
    if failed:
        print(f"失败未标注块：{failed}（可重跑本脚本续补）", flush=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
