# -*- coding: utf-8 -*-
"""LLM API 凭据加载器 —— 密钥不入代码库（P1 修复，2026-11-03）。

背景：annotate_llm.py 与 scripts/_oneshot/ 一次性脚本原把 polylink/NIM/AMD 的
密钥硬编码在源码里（承自 _qwen_标注对比 旧脚本家族）。本模块统一改为外部加载。

读取顺序（先到先得，逐字段独立）：
  1. 环境变量：
       WUXIA_API_POLYLINK_URL / WUXIA_API_POLYLINK_CF_ID / WUXIA_API_POLYLINK_CF_SECRET
       / WUXIA_API_POLYLINK_KEY / WUXIA_API_NIM_URL / WUXIA_API_NIM_KEY
       / WUXIA_API_AMD_URL / WUXIA_API_AMD_KEY
       / WUXIA_API_DEEPSEEK_URL / WUXIA_API_DEEPSEEK_KEY / WUXIA_API_DEEPSEEK_MODEL
  2. 配置文件 config.ROOT/.api_config.json（已被 wuxia-kb/.gitignore 排除，勿提交）：
       {"polylink": {url, cf_id, cf_secret, key}, "nim": {url, key}, "amd": {url, key},
        "deepseek": {url, key, model}}

用法（消费方需先把 wuxia-kb/scripts 加入 sys.path）：
    import api_config
    headers = {"Authorization": "Bearer " + api_config.get("polylink", "key")}
"""
import json
import os

import config

CONFIG_PATH = config.ROOT / ".api_config.json"

_ENV = {
    ("polylink", "url"): "WUXIA_API_POLYLINK_URL",
    ("polylink", "cf_id"): "WUXIA_API_POLYLINK_CF_ID",
    ("polylink", "cf_secret"): "WUXIA_API_POLYLINK_CF_SECRET",
    ("polylink", "key"): "WUXIA_API_POLYLINK_KEY",
    ("nim", "url"): "WUXIA_API_NIM_URL",
    ("nim", "key"): "WUXIA_API_NIM_KEY",
    ("amd", "url"): "WUXIA_API_AMD_URL",
    ("amd", "key"): "WUXIA_API_AMD_KEY",
    ("deepseek", "url"): "WUXIA_API_DEEPSEEK_URL",
    ("deepseek", "key"): "WUXIA_API_DEEPSEEK_KEY",
    ("deepseek", "model"): "WUXIA_API_DEEPSEEK_MODEL",
}


def load() -> dict:
    """返回 {服务: {字段: 值}}；env 覆盖配置文件。不缓存（env 可中途变更）。"""
    data = {}
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    out = {}
    for (svc, field), env in _ENV.items():
        val = os.environ.get(env) or data.get(svc, {}).get(field)
        if val:
            out.setdefault(svc, {})[field] = val
    return out


def get(service: str, field: str) -> str:
    """取单条凭据；缺失时抛错并给出配置方法。"""
    val = load().get(service, {}).get(field)
    if not val:
        raise RuntimeError(
            f"缺少 API 凭据 {service}.{field}：设置环境变量 {_ENV[(service, field)]}，"
            f"或写入 {CONFIG_PATH}（该文件已被 .gitignore 排除，勿提交）")
    return val
