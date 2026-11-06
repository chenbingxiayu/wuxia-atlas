# -*- coding: utf-8 -*-
"""设计板地图升级：DataV 省界 GeoJSON → 简化静态 SVG 路径 + 真实经纬度标记重投影。
用法: python upgrade_maps.py   （在 _tools/ 下运行；产物写回 ../project/*.dc.html）
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJ = ROOT / "project"
GEO = Path(r"C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\site\public\geo\china-provinces.json")

L0, L1, T, B, KX = 73.0, 135.5, 54.3, 17.8, 0.799  # 经度界/纬度界/等距投影 cos37° 修正

def load_rings():
    data = json.loads(GEO.read_text(encoding="utf-8"))
    rings = []
    for f in data["features"]:
        g = f.get("geometry") or {}
        polys = []
        if g.get("type") == "MultiPolygon":
            polys = [p[0] for p in g["coordinates"]]
        elif g.get("type") == "Polygon":
            polys = [g["coordinates"][0]]
        for ring in polys:
            lons = [p[0] for p in ring]; lats = [p[1] for p in ring]
            if min(lats) < 18.0:            # 南海诸岛：设计稿不落
                continue
            if (max(lons)-min(lons)) * (max(lats)-min(lats)) < 0.35:  # 微小岛屿
                continue
            rings.append(ring)
    return rings

def dp(points, tol):
    """Douglas-Peucker 简化。"""
    if len(points) < 3:
        return points
    keep = [False]*len(points); keep[0] = keep[-1] = True
    stack = [(0, len(points)-1)]
    while stack:
        a, b = stack.pop()
        if b <= a+1: continue
        ax, ay = points[a]; bx, by = points[b]
        dx, dy = bx-ax, by-ay
        norm = (dx*dx+dy*dy) ** .5 or 1e-9
        dmax, imax = -1.0, -1
        for i in range(a+1, b):
            px, py = points[i]
            d = abs(dx*(ay-py) - dy*(ax-px)) / norm
            if d > dmax: dmax, imax = d, i
        if dmax > tol:
            keep[imax] = True; stack.append((a, imax)); stack.append((imax, b))
    return [p for p, k in zip(points, keep) if k]

def thin(points, min_step=0.12):
    out = [points[0]]
    for p in points[1:]:
        if abs(p[0]-out[-1][0]) + abs(p[1]-out[-1][1]) >= min_step:
            out.append(p)
    return out

def fit(W, H, mx, my):
    s = min((W-2*mx)/((L1-L0)*KX), (H-2*my)/(T-B))
    mw, mh = (L1-L0)*KX*s, (T-B)*s
    ox, oy = (W-mw)/2, (H-mh)/2
    def f(lng, lat):
        return (round(ox+(lng-L0)*KX*s, 1), round(oy+(T-lat)*s, 1))
    return f

def land_path(rings, f):
    parts = []
    for r in rings:
        pts = [(p[0], p[1]) for p in r]
        # 闭合环去尾——GeoJSON 有"环内部再现起点坐标"的瑕疵（如北京环），
        # 必须循环剥掉所有与首点相同的尾部重复，否则 DP 零弦退化、整环丢失
        while len(pts) > 2 and pts[-1] == pts[0]:
            pts = pts[:-1]
        pts = thin(dp(pts, 0.2))
        if len(pts) < 4: continue
        d = "M" + "L".join(f"{f(x,y)[0]},{f(x,y)[1]}" for x, y in pts) + "Z"
        parts.append(d)
    return "".join(parts)

P = {  # 真实经纬度标记表（GCJ-02 近似）
    "天山": (85.5, 43.0), "拉萨": (91.1, 29.7), "嘉峪关": (98.3, 39.8),
    "成都": (104.0, 30.6), "峨眉山": (103.3, 29.5), "武当山": (111.0, 32.4),
    "伏牛山": (111.9, 33.7), "汝州": (112.8, 34.2), "嵩山": (113.0, 34.5),
    "五台山": (113.1, 39.0), "北京": (116.4, 39.9), "杭州": (120.2, 30.3),
    "长白山": (128.0, 42.0),
}

def replace_svg(html, aria, new_svg):
    i = html.find(aria)
    assert i > 0, f"aria 未找到: {aria}"
    a = html.rfind("<svg", 0, i)
    b = html.find("</svg>", i) + len("</svg>")
    return html[:a] + new_svg + html[b:]

def svg_open(W, H, label):
    return f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;display:block" role="img" aria-label="{label}">'

# ---------- 各板 ----------
def mod_map():
    W, H, mx, my = 940, 640, 40, 42
    f = fit(W, H, mx, my)
    rings = load_rings()
    d = land_path(rings, f)
    t = lambda n, dx=0, dy=0: f(*P[n]) if dx == dy == 0 else (f(*P[n])[0]+dx, f(*P[n])[1]+dy)
    tx, ty = f(*P["天山"]); bjx, bjy = f(*P["北京"]); wd = f(*P["武当山"]); cb = f(*P["长白山"])
    cj = f(*P["成都"]); wt = f(*P["五台山"]); ls = f(*P["拉萨"]); jy = f(*P["嘉峪关"]); hz = f(*P["杭州"])
    inner = f'''
        <rect width="{W}" height="{H}" fill="#f8f3e6"/>
        <path d="{d}" fill="#f1e9d7" stroke="#c9bda2" stroke-width="1.2"/>
        <g font-size="11" fill="#8c8477">
          <text x="{tx+14}" y="{ty+4}">天山</text>
          <text x="{bjx-10}" y="{bjy-12}">北京</text>
          <text x="{wd[0]-16}" y="{wd[1]+18}">武当山</text>
          <text x="{wt[0]-8}" y="{wt[1]-14}">五台山</text>
          <text x="{hz[0]+8}" y="{hz[1]+14}">杭州</text>
        </g>
        <path d="M{tx},{ty}L{f(*P['嘉峪关'])[0]},{f(*P['嘉峪关'])[1]}L{wt[0]},{wt[1]}L{bjx},{bjy}L{hz[0]},{hz[1]}"
          fill="none" stroke="#a63a2b" stroke-width="1.6" stroke-dasharray="4 4" opacity=".55"/>
        <g fill="#a63a2b" opacity=".7">
          <circle cx="{wt[0]}" cy="{wt[1]}" r="3.5"/><circle cx="{bjx}" cy="{bjy}" r="3.5"/>
        </g>
        <g>
          <circle cx="{tx}" cy="{ty}" r="9" fill="#a63a2b" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{tx}" y="{ty-16}" font-size="11.5" fill="#a63a2b" text-anchor="middle" font-weight="700">天山派</text>
          <circle cx="{bjx}" cy="{bjy}" r="9" fill="#34546e" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{bjx}" y="{bjy+24}" font-size="11.5" fill="#34546e" text-anchor="middle" font-weight="700">朝廷 · 大内</text>
          <circle cx="{wd[0]}" cy="{wd[1]}" r="9" fill="#a63a2b" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{wd[0]}" y="{wd[1]+26}" font-size="11.5" fill="#a63a2b" text-anchor="middle" font-weight="700">武当派</text>
          <circle cx="{cb[0]}" cy="{cb[1]}" r="9" fill="#5e7d5a" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{cb[0]-8}" y="{cb[1]+26}" font-size="11.5" fill="#5e7d5a" text-anchor="middle" font-weight="700">关东四侠（绿林）</text>
          <circle cx="{cj[0]}" cy="{cj[1]}" r="8" fill="#b8860b" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{cj[0]}" y="{cj[1]+24}" font-size="11.5" fill="#b8860b" text-anchor="middle" font-weight="700">唐家（世家）</text>
        </g>
        <g>
          <circle cx="{ls[0]}" cy="{ls[1]}" r="7" fill="#34546e" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{ls[0]}" y="{ls[1]+22}" font-size="11" fill="#34546e" text-anchor="middle" font-weight="700">① 布达拉宫 · 被囚十年</text>
          <path d="M{ls[0]+6},{ls[1]-6}L{tx+4},{ty+6}" fill="none" stroke="#34546e" stroke-width="1.3" stroke-dasharray="5 4"/>
          <text x="{(ls[0]+tx)/2}" y="{(ls[1]+ty)/2-8}" font-size="10.5" fill="#34546e">② 脱困东归</text>
          <circle cx="{tx-2}" cy="{ty+2}" r="5" fill="none" stroke="#34546e" stroke-width="1.5"/>
        </g>
        <g>
          <circle cx="{f(108.0,32.1)[0]}" cy="{f(108.0,32.1)[1]}" r="8" fill="none" stroke="#5e7d5a" stroke-width="2" stroke-dasharray="3 3"/>
          <text x="{f(108.0,32.1)[0]}" y="{f(108.0,32.1)[1]+24}" font-size="11" fill="#5e7d5a" text-anchor="middle" font-weight="700">明月峡 ◌ 推理偏移</text>
          <text x="{f(108.0,32.1)[0]}" y="{f(108.0,32.1)[1]+38}" font-size="9.5" fill="#8c8477" text-anchor="middle">锚：剑门关 · 同回共现 3 次</text>
        </g>
        <text x="{W-24}" y="{H-20}" font-size="11" fill="#8c8477" text-anchor="end">底图：DataV 省界（简化静态投影）· ● 实锚 · ◌ 虚构推理偏移（如明月峡）</text>
      '''
    return svg_open(W, H, "地图底座与三图层标记示意"), inner

def map_page():
    W, H, mx, my = 1100, 640, 40, 42
    f = fit(W, H, mx, my)
    d = land_path(load_rings(), f)
    tx, ty = f(*P["天山"]); bj = f(*P["北京"]); wt = f(*P["五台山"]); ls = f(*P["拉萨"]); hz = f(*P["杭州"]); jy = f(*P["嘉峪关"])
    route = f"M{tx},{ty}L{jy[0]},{jy[1]}L{wt[0]},{wt[1]}L{bj[0]},{bj[1]}L{hz[0]},{hz[1]}"
    inner = f'''
        <rect width="{W}" height="{H}" fill="#f8f3e6"/>
        <path d="{d}" fill="#f1e9d7" stroke="#c9bda2" stroke-width="1.2"/>
        <path d="{route}" fill="none" stroke="#a63a2b" stroke-width="1.8" stroke-dasharray="4 4" opacity=".6"/>
        <g font-size="11" fill="#8c8477">
          <text x="{tx+14}" y="{ty+4}">天山</text><text x="{bj[0]-10}" y="{bj[1]-12}">北京</text>
          <text x="{wt[0]-8}" y="{wt[1]-14}">五台山</text><text x="{hz[0]+8}" y="{hz[1]+14}">杭州</text>
        </g>
        <path d="M{tx},{ty}L{ls[0]},{ls[1]}" fill="none" stroke="#34546e" stroke-width="1.4" stroke-dasharray="6 4" opacity=".7"/>
        <g>
          <circle cx="{tx}" cy="{ty}" r="8" fill="#a63a2b" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{tx}" y="{ty-16}" font-size="11.5" fill="#a63a2b" text-anchor="middle" font-weight="700">天山派</text>
          <circle cx="{bj[0]}" cy="{bj[1]}" r="8" fill="#34546e" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{bj[0]}" y="{bj[1]+24}" font-size="11.5" fill="#34546e" text-anchor="middle" font-weight="700">大内</text>
          <circle cx="{wt[0]}" cy="{wt[1]}" r="10" fill="#34546e" stroke="#fbf8ef" stroke-width="2.5"/>
          <circle cx="{wt[0]}" cy="{wt[1]}" r="16" fill="none" stroke="#34546e" opacity=".4"/>
          <text x="{wt[0]}" y="{wt[1]+34}" font-size="11.5" fill="#34546e" text-anchor="middle" font-weight="700">当前 · 凉爽寺</text>
          <circle cx="{ls[0]}" cy="{ls[1]}" r="6" fill="#b8860b" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{ls[0]}" y="{ls[1]+20}" font-size="10.5" fill="#8a6607" text-anchor="middle">① 被囚十年（剧情锚点）</text>
        </g>
        <text x="{(tx+ls[0])/2-60}" y="{(ty+ls[1])/2}" font-size="10.5" fill="#a63a2b" transform="rotate(-38 {(tx+ls[0])/2-60} {(ty+ls[1])/2})">断点：两书之间无共现记录，不推断途中路线</text>
        <g style="opacity:.95">
          <rect x="{W-346}" y="{H-236}" width="300" height="164" rx="4" fill="#fbf8ef" stroke="#2b2b2b" stroke-width="1.5" transform="translate(4,4)"/>
          <rect x="{W-350}" y="{H-240}" width="300" height="164" rx="4" fill="#fbf8ef" stroke="#2b2b2b" stroke-width="1.5"/>
          <text x="{W-330}" y="{H-212}" font-size="15" font-weight="700" font-family="'Noto Serif SC','SimSun',serif">凉爽寺</text>
          <text x="{W-66}" y="{H-212}" font-size="10" fill="#4f6e4a" text-anchor="end">● 精确</text>
          <text x="{W-330}" y="{H-190}" font-size="11.5" fill="#5a544a">五台山 · 凌未风被囚前挂单之地</text>
          <text x="{W-330}" y="{H-170}" font-size="11" fill="#8c8477">在场：凌未风 · 武琼瑶 · 见于 七剑 021</text>
          <text x="{W-330}" y="{H-148}" font-size="11" fill="#34546e">关联：天山派 · 回目页 021 →</text>
          <text x="{W-330}" y="{H-112}" font-size="10" fill="#8c8477">坐标置信：● 精确（明文地标）· ◐ 偏移 · ○ 近似</text>
        </g>
      '''
    return svg_open(W, H, "行踪地图示意"), inner

def sects():
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
    for name, (key, color, r) in m.items():
        x, y = f(*P[key])
        anchors = {"天山派": (-6, -16), "朝廷·大内": (0, 26), "武当派": (0, 26), "关东四侠": (-10, 26), "少林派": (10, -12), "无极派": (0, 24), "峨嵋派": (0, 24), "唐家": (12, -10)}
        dx, dy = anchors[name]
        anchors_mid = "middle" if dy > 0 or abs(dx) < 12 else ("start" if dx > 0 else "end")
        dots.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}" stroke="#fbf8ef" stroke-width="2"/>'
                    f'<text x="{x+dx}" y="{y+dy}" font-size="11.5" fill="{color}" text-anchor="{anchors_mid}" font-weight="700">{name}</text>')
    inner = f'''
        <rect width="{W}" height="{H}" fill="#f8f3e6"/>
        <path d="{d}" fill="#f1e9d7" stroke="#c9bda2" stroke-width="1.2"/>
        <g>{''.join(dots)}</g>
        <text x="{W-28}" y="{H-22}" font-size="11" fill="#8c8477" text-anchor="end">实锚 ● 与推理偏移 ◌（虚构地名，依附近实锚）落图 · DataV 省界简化投影 · 驻地待考名单见图下</text>
      '''
    return svg_open(W, H, "全景势力地图"), inner

def character():
    W, H, mx, my = 940, 600, 40, 42
    f = fit(W, H, mx, my)
    d = land_path(load_rings(), f)
    rz = f(*P["汝州"]); bj = f(*P["北京"]); tx = f(*P["天山"])
    inner = f'''
        <rect width="{W}" height="{H}" fill="#f8f3e6"/>
        <path d="{d}" fill="#f1e9d7" stroke="#c9bda2" stroke-width="1.2"/>
        <path d="M{rz[0]},{rz[1]}L{bj[0]},{bj[1]}L{tx[0]},{tx[1]}" fill="none" stroke="#8c8477" stroke-width="1.3" stroke-dasharray="4 4"/>
        <g>
          <circle cx="{rz[0]}" cy="{rz[1]}" r="8" fill="#a63a2b" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{rz[0]}" y="{rz[1]+24}" font-size="11" text-anchor="middle" font-weight="700">① 劫镖初会 · 汝州</text>
          <circle cx="{bj[0]}" cy="{bj[1]}" r="8" fill="#34546e" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{bj[0]+6}" y="{bj[1]-14}" font-size="11" text-anchor="middle" font-weight="700">② 一夜白头 · 西山秘魔崖</text>
          <circle cx="{tx[0]}" cy="{tx[1]}" r="8" fill="#5e7d5a" stroke="#fbf8ef" stroke-width="2"/>
          <text x="{tx[0]}" y="{tx[1]-16}" font-size="11" text-anchor="middle" font-weight="700">③ 塞外重逢 · 天山</text>
        </g>
        <text x="{W-24}" y="{H-18}" font-size="10.5" fill="#8c8477" text-anchor="end">点=锚点（颜色示类型 · 编号示先后）· 虚线=故事先后，不表示行进路线 · 底图 DataV 简化投影</text>
      '''
    return svg_open(W, H, "练霓裳剧情地图示意"), inner

JOBS = [
    ("Mod-Map.dc.html", "地图底座与三图层标记示意", mod_map, 1450),
    ("P-MapPage.dc.html", "行踪地图示意", map_page, 1380),
    ("P-Character.dc.html", "练霓裳剧情地图示意", character, 2560),
]

def main():
    for fname, aria, builder, new_h in JOBS:
        p = PROJ / fname
        html = p.read_text(encoding="utf-8")
        open_tag, inner = builder()
        new_svg = open_tag + inner + "\n      </svg>"
        html = replace_svg(html, aria, new_svg)
        p.write_text(html, encoding="utf-8")
        print(f"-> {fname} 地图已替换（板高 → {new_h}）")
    cj = PROJ / "canvas.json"
    meta = json.loads(cj.read_text(encoding="utf-8"))
    for fname, _, _, new_h in JOBS:
        meta["boards"][fname]["h"] = new_h
    cj.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("-> canvas.json 板高已更新")

if __name__ == "__main__":
    sys.exit(main())
