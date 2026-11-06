#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qwen 外部复核器（通用文件评审，2026-11-04 新增）。

用途：把一组文件（代码/词表/文档）打包成评审请求，调用 AMD Radeon API 的
Qwen3.8-Flash-Next（OpenAI 兼容 chat/completions），逐组产出独立评审意见。
本脚本只读文件、只写评审产物；不修改被评审文件。

凭据（不入库）：环境变量
  QWEN_API_KEY   必填
  QWEN_BASE_URL  可选，默认 https://developer.amd.com.cn/radeon/api/v1
  QWEN_MODEL     可选，默认 Qwen3.8-Flash-Next

用法：
  python scripts/qwen_review_files.py --manifest logs/qa/qwen_max_review/manifest.json \
      --out-dir logs/qa/qwen_max_review --workers 2

manifest 格式（JSON 数组）：
  [{"id":"G1_tag_scripts","title":"C16/C17/C19 标签脚本",
    "kind":"code",                       # code|wordlist|doc
    "files":[{"path":"scripts/x.py"},     # 整文件
             {"path":"scripts/y.py","lines":[1,300]}],  # 可选行范围
    "extra":"本组补充关注点"}]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "https://developer.amd.com.cn/radeon/api/v1"
DEFAULT_MODEL = "Qwen3.8-Flash-Next"
MAX_FILE_CHARS = 60000          # 单组文件内容上限（超出则报错提示拆组）
MAX_TOKENS = 6000

KIND_GUIDE = {
    "code": (
        "这是一批 Python 脚本（武侠知识库标注管线）。请重点审查：\n"
        "1) 正确性 bug：正则/边界条件/编码/路径/CLI 参数/异常处理/静默失败；\n"
        "2) 项目契约一致性：应 import config/symbols/masker（路径与符号唯一来源）、"
        "默认不得修改 tagged 正文、写 tagged 必须备份+剥标断言、建议 TSV 需兼容 "
        "apply_annotation_patches 的 7 列契约；\n"
        "3) 误报/漏报风险（词表召回类脚本）与可维护性（重复代码/魔法数/可测试性）；\n"
        "4) 明显缺失的测试/自检。"
    ),
    "wordlist": (
        "这是一批词表人工源（Markdown 表格：surface/type/tier/status/conf/evidence/note）。"
        "请重点审查：\n"
        "1) 词条质量：同形歧义/误收（普通名词当专名）、重复 surface、类型码是否属于 15 类定版；\n"
        "2) 档位纪律：tier 只能是 auto/review/watch，status 只能 auto/待审/已核准，"
        "conf 只能 strong/ok/weak；本批应为全 review/watch、零 auto；\n"
        "3) 负规则一致性：D1（纯亲属/谦辞/自称不标）、通名不标、冻结名不拆；\n"
        "4) 覆盖缺口与建议增删（每表给 5-10 条具体建议）。"
    ),
    "doc": (
        "这是一批项目文档（实施记录/验收报告/审计报告）。请重点审查：\n"
        "1) 内部矛盾与数字不一致（同一事实多处数字/状态冲突）；\n"
        "2) 过度声称：把'建议/未执行/计划'写成'已完成'，或缺乏证据的结论；\n"
        "3) 与所描述实现的一致性（可从文中引用的脚本/命令推断其是否可实现）；\n"
        "4) 结构可读性与遗漏的关键信息（复现命令、局限、残余风险）。"
    ),
}

OUTPUT_SPEC = """\
输出格式（中文 Markdown，≤1200 字，避免复述文件内容）：
## 总评
（2-3 句：质量判断 + 最值得肯定/最需修的点）
## 问题清单
| 严重度 | 位置 | 问题 | 建议 |
|---|---|---|---|
| P0 | 文件:行/函数 | ... | ... |
（P0=会出错/数据损坏；P1=明显缺陷或契约违反；P2=改进建议。每文件至少 2 条，最多 8 条）
## 亮点
（2-4 条）
## 结论
（可接受 / 小修后可接受 / 需返工）
注意：无法验证的外部事实标注【需核验】；不要臆造文件中不存在的内容；不要给泛泛而谈的建议。"""


def read_file(spec: dict) -> tuple[str, str]:
    path = ROOT / spec["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    lines = spec.get("lines")
    if lines:
        arr = text.splitlines()
        a = max(1, int(lines[0]))
        b = len(arr) if len(lines) < 2 or lines[1] is None else min(len(arr), int(lines[1]))
        text = "\n".join(arr[a - 1:b])
        label = f"{spec['path']}（第 {a}-{b} 行）"
    else:
        label = spec["path"]
    return label, text


def build_prompt(group: dict) -> tuple[str, str]:
    kind = group.get("kind", "code")
    parts, total = [], 0
    for spec in group["files"]:
        label, text = read_file(spec)
        total += len(text)
        parts.append(f"\n===== FILE: {label} =====\n{text}\n===== END FILE =====\n")
    if total > MAX_FILE_CHARS:
        raise ValueError(f"{group['id']}: 文件内容 {total} 字符 > {MAX_FILE_CHARS}，请拆组")
    system = (
        "你是资深的中文 NLP 知识库项目评审专家（Python + 标注规范 + 文档审计）。"
        "你的任务是对给定文件做独立、严格、可执行的评审。只依据文件内容判断，"
        "不要假设文件外的事实；不确定处标注【需核验】。"
    )
    user = (
        f"# 评审任务：{group['title']}\n\n"
        f"## 背景\n{group.get('background', '')}\n\n"
        f"## 审查重点\n{KIND_GUIDE.get(kind, KIND_GUIDE['code'])}\n"
        + (f"\n## 本组补充关注点\n{group['extra']}\n" if group.get("extra") else "")
        + "\n## 文件内容\n"
        + "".join(parts)
        + "\n"
        + OUTPUT_SPEC
    )
    return system, user


def call_qwen(base: str, key: str, model: str, system: str, user: str,
              retries: int = 3, verify: bool = True) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        # AMD/vLLM 端点：关闭 Qwen thinking 的生效写法是 chat_template_kwargs；
        # 顶层 enable_thinking 在该端点无效（实测仍产生 reasoning 并吃满 max_tokens）。
        "chat_template_kwargs": {"enable_thinking": False},
        "enable_thinking": False,
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    # 默认校验 TLS 证书（Bearer key 随请求发送，禁校验可被中间人窃取）；
    # 端点证书链异常时用 --insecure 显式退出。
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    last = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            base.rstrip("/") + "/chat/completions", data=data,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key})
        try:
            with urllib.request.urlopen(req, timeout=600, context=ctx) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {e.code}: {body_txt}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        if attempt < retries:
            time.sleep(5 * attempt)
    raise RuntimeError(f"调用失败（{retries} 次）：{last}")


def extract_content(resp: dict) -> str:
    try:
        msg = resp["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        if not content:
            content = (msg.get("reasoning") or "").strip()
        return content
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out-dir", default="logs/qa/qwen_max_review")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only", default="", help="只跑指定 id（逗号分隔）")
    ap.add_argument("--insecure", action="store_true",
                    help="关闭 TLS 证书校验（端点证书链异常时才用）")
    args = ap.parse_args()

    key = os.environ.get("QWEN_API_KEY", "")
    if not key:
        print("✗ 缺少环境变量 QWEN_API_KEY")
        return 2
    base = os.environ.get("QWEN_BASE_URL", DEFAULT_BASE)
    model = os.environ.get("QWEN_MODEL", DEFAULT_MODEL)

    groups = json.loads((ROOT / args.manifest).read_text(encoding="utf-8"))
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        groups = [g for g in groups if g["id"] in want]
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    def run_one(g: dict) -> dict:
        t0 = time.time()
        system, user = build_prompt(g)
        resp = call_qwen(base, key, model, system, user, verify=not args.insecure)
        content = extract_content(resp)
        usage = resp.get("usage", {})
        meta = {
            "id": g["id"], "title": g["title"], "kind": g.get("kind"),
            "files": [s["path"] for s in g["files"]],
            "model": model, "base_url": base,
            "prompt_chars": len(user), "elapsed_s": round(time.time() - t0, 1),
            "usage": usage, "cost_usd": usage.get("cost"),
            "generated": datetime.now().isoformat(timespec="seconds"),
            "finish_reason": (resp.get("choices") or [{}])[0].get("finish_reason"),
        }
        (out_dir / f"{g['id']}.md").write_text(
            f"# 评审：{g['title']}\n\n> 模型 {model} · {meta['generated']} · "
            f"prompt {len(user)} 字符 · {meta['elapsed_s']}s\n\n{content}\n",
            encoding="utf-8")
        (out_dir / f"{g['id']}.json").write_text(
            json.dumps({"meta": meta, "content": content}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        return meta

    results, errors = [], []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(run_one, g): g for g in groups}
        for fut in as_completed(futs):
            g = futs[fut]
            try:
                m = fut.result()
                results.append(m)
                print(f"✓ {g['id']}: {m['elapsed_s']}s · "
                      f"in={m['usage'].get('prompt_tokens')} out={m['usage'].get('completion_tokens')} "
                      f"· cost={m['cost_usd']} · finish={m['finish_reason']}")
            except Exception as e:  # noqa: BLE001
                errors.append({"id": g["id"], "error": str(e)})
                print(f"✗ {g['id']}: {e}")

    total_cost = sum((r.get("cost_usd") or 0) for r in results)
    summary = {"generated": datetime.now().isoformat(timespec="seconds"),
               "model": model, "base_url": base,
               "groups_ok": len(results), "groups_failed": len(errors),
               "total_cost_usd": round(total_cost, 6), "errors": errors,
               "results": results}
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n完成 {len(results)}/{len(groups)} 组；失败 {len(errors)}；"
          f"合计 ${total_cost:.6f}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
