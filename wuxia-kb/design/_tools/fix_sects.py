# -*- coding: utf-8 -*-
"""修复 P-Sects.dc.html：整文件重建（原模板 + sed 字体变更 + 真实省界地图 + $preview 1930）。"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from upgrade_maps import load_rings, land_path, fit, svg_open, PROJ

W, H, mx, my = 1100, 700, 40, 44
f = fit(W, H, mx, my)
d = land_path(load_rings(), f)
m = {
    "天山派": ("天山", "#a63a2b", 10), "无极派": ("伏牛山", "#a63a2b", 8),
    "少林派": ("嵩山", "#a63a2b", 9), "武当派": ("武当山", "#a63a2b", 9),
    "峨嵋派": ("峨眉山", "#a63a2b", 8), "唐家": ("成都", "#b8860b", 8),
    "朝廷·大内": ("北京", "#34546e", 10), "关东四侠": ("长白山", "#5e7d5a", 9),
}
dots = []
mx_, my_ = f(108.0, 32.1)  # 明月峡：虚构推理偏移示例（锚：剑门关 · 同回共现）
dots.append(f'<circle cx="{mx_}" cy="{my_}" r="8" fill="none" stroke="#5e7d5a" stroke-width="2" stroke-dasharray="3 3"/>'
            f'<text x="{mx_}" y="{my_+26}" font-size="11.5" fill="#5e7d5a" text-anchor="middle" font-weight="700">明月峡 ◌ 推理偏移</text>')
for name, (key, color, r) in m.items():
    x, y = f(*__import__("upgrade_maps").P[key])
    anchors = {"天山派": (-6, -16), "朝廷·大内": (0, 26), "武当派": (0, 26), "关东四侠": (-10, 26),
               "少林派": (10, -12), "无极派": (0, 24), "峨嵋派": (0, 24), "唐家": (12, -10)}
    dx, dy = anchors[name]
    mid = "middle" if dy > 0 or abs(dx) < 12 else ("start" if dx > 0 else "end")
    dots.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}" stroke="#fbf8ef" stroke-width="2"/>'
                f'<text x="{x+dx}" y="{y+dy}" font-size="11.5" fill="{color}" text-anchor="{mid}" font-weight="700">{name}</text>')
MAP = (svg_open(W, H, "势力驻地图（真实省界）") +
       f'''
        <rect width="{W}" height="{H}" fill="#f8f3e6"/>
        <path d="{d}" fill="#f1e9d7" stroke="#c9bda2" stroke-width="1.2"/>
        <g>{''.join(dots)}</g>
        <text x="{W-28}" y="{H-22}" font-size="11" fill="#8c8477" text-anchor="end">实锚 ● 与推理偏移 ◌（虚构地名，依附近实锚）落图 · DataV 省界简化投影 · 驻地待考名单见图下</text>
      </svg>''')

TPL = '''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>页面组装 · 门派总览</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<style>
  body{margin:0;background:#f5efe4;font-family:"LXGW WenKai TC","LXGW WenKai","KaiTi","STKaiti","Noto Serif SC","SimSun",serif;color:#2b2b2b}
  a{color:#34546e;text-decoration:none}a:hover{color:#a63a2b}
  .wrap{max-width:1240px;margin:0 auto;padding:0 48px}
  .nav{display:flex;gap:20px;align-items:center;font-size:14px}
  .lab{font-size:12px;color:#8c8477;line-height:1.7}
  .badge{display:inline-block;border:1.5px solid;border-radius:3px;padding:0 8px;font-size:12px}
  .card{border:1px solid #b9ab90;border-radius:4px;padding:14px 16px;background:#fbf8ef;display:block;color:#2b2b2b}
  .card:hover{border-color:#a63a2b}
  h2.sec{font-family:'Noto Serif SC','SimSun',serif;font-weight:900;font-size:20px;margin:32px 0 10px;border-bottom:1px solid #d8cdb8;padding-bottom:5px;letter-spacing:2px}
</style>
</helmet>
<div style="min-height:100%;display:flex;flex-direction:column">
  <header style="border-bottom:1px solid #d8cdb8;background:#fbf8ef"><div class="wrap nav" style="height:52px">
    <span style="font-family:'Ma Shan Zheng','KaiTi','STKaiti',cursive;font-size:24px;color:#a63a2b;margin-right:18px">江湖图志</span>
    <a href="#">作品</a><a href="#">宇宙</a><a href="#">人物</a><a href="#">武功</a><a href="#">名物</a><a href="#" style="color:#a63a2b;font-weight:700">门派</a><a href="#">地图</a><a href="#">武评</a><a href="#">游戏</a><a href="#">搜索</a><a href="#">关于</a></div></header>

  <main class="wrap" style="flex:1;padding-bottom:48px">
    <p class="lab" style="margin:14px 0 0"><a href="#">首页</a> / 门派志</p>
    <h1 style="font-family:'Noto Serif SC','SimSun',serif;font-weight:900;font-size:36px;letter-spacing:3px;margin:6px 0 4px">门派志</h1>
    <p class="lead" style="color:#5a544a;font-size:15px">四书江湖的势力版图：名门正派、世家、绿林帮会与朝廷机构，各在何处、谁家当家、恩怨几何——每一条都挂原著定位。</p>

    <h2 class="sec">全景势力地图 <span class="lab">仅标注原文明文驻地；驻地待考的势力列于图下，同样可点 · 点击标记进入门派页</span></h2>
    <div style="border:1px solid #b9ab90;border-radius:4px;background:#f8f3e6;padding:8px">
      __MAP__
      <div style="padding:8px 12px" class="lab">
        驻地待考（同样可点）：太极派 · 天龙派 · 嵩阳派 · 岳家 · 雪山派 ｜
        类型图例：<span style="color:#a63a2b;font-weight:700">● 名门正派</span> · <span style="color:#b8860b;font-weight:700">● 世家</span> · <span style="color:#5e7d5a;font-weight:700">● 绿林帮会</span> · <span style="color:#34546e;font-weight:700">● 朝廷势力</span></div>
    </div>

    <h2 class="sec">江湖势力 <span class="lab">名门正派 → 世家 → 绿林帮会 · 搜索框命中派名与别名</span></h2>
    <div style="margin-top:8px"><input style="width:320px;padding:8px 14px;border:1.5px solid #2b2b2b;border-radius:4px;font-family:inherit;background:#fbf8ef" value="搜索门派名或别名…" aria-label="搜索门派"></div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:12px">
      <a class="card" href="#"><div style="display:flex;align-items:center;gap:8px"><b style="font-family:'Noto Serif SC','SimSun',serif;font-size:16px">武当派</b><span class="badge" style="border-color:#a63a2b;color:#a63a2b">名门正派</span></div>
        <p class="lab" style="margin:6px 0 0">镇山：达摩一百零八式 · 掌门卓一航（白发 007:75）· 成员 4 · 见于 2 书</p></a>
      <a class="card" href="#"><div style="display:flex;align-items:center;gap:8px"><b style="font-family:'Noto Serif SC','SimSun',serif;font-size:16px">天山派</b><span class="badge" style="border-color:#a63a2b;color:#a63a2b">名门正派</span><span class="badge" style="border-color:#b8860b;color:#b8860b;border-style:dashed">建设中</span></div>
        <p class="lab" style="margin:6px 0 0">镇山：天山剑法 · 世系考订中（晦明→凌未风→易兰珠）· 成员 5</p></a>
      <a class="card" href="#"><div style="display:flex;align-items:center;gap:8px"><b style="font-family:'Noto Serif SC','SimSun',serif;font-size:16px">关东四侠</b><span class="badge" style="border-color:#5e7d5a;color:#5e7d5a">绿林帮会</span></div>
        <p class="lab" style="margin:6px 0 0">玄风等四兄弟 · 三女侠 004 联袂斗双魔 · 事件参与 7 起</p></a>
    </div>
    <p class="lab" style="margin-top:10px"><a href="#">其余势力（记载简略）▾</a>　终南派 · 华山派 · 昆仑派 · 太极派 · 唐家 · 岳家 · 五龙帮 · 铁扇帮…</p>

    <h2 class="sec">朝廷势力 <span class="lab">另册 · 不与江湖门派混编</span></h2>
    <div style="background:#ece2cf;border:1px solid #b9ab90;border-radius:4px;padding:14px 18px;display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
      <a class="card" href="#"><b style="font-family:'Noto Serif SC','SimSun',serif;font-size:16px">大内（卫士系统）</b><p class="lab" style="margin:6px 0 0">含血滴子特务组织侧 · 三女侠主对手 · 驻地：北京紫禁城</p></a>
      <a class="card" href="#"><b style="font-family:'Noto Serif SC','SimSun',serif;font-size:16px">锦衣卫</b><p class="lab" style="margin:6px 0 0">白发魔女传时代 · 事件参与 3 起</p></a>
      <a class="card" href="#"><b style="font-family:'Noto Serif SC','SimSun',serif;font-size:16px">御林军 / 禁卫军</b><p class="lab" style="margin:6px 0 0">机构侧 · 军队泛称（清军/官军）不入册</p></a>
    </div>
  </main>
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{"$preview":{"width":1360,"height":1930}}'>
class Component extends DCLogic {
  renderVals() { return {}; }
}
</script>
</body>
</html>
'''

out = TPL.replace("__MAP__", MAP)
(PROJ / "P-Sects.dc.html").write_text(out, encoding="utf-8")
print("-> P-Sects.dc.html 已重建", len(out), "bytes")
