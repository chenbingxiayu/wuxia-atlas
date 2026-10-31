# -*- coding: utf-8 -*-
import re

tagged = open(r"kb/tagged/江湖三女侠/044_第四十四回.tagged.md", encoding="utf-8").read()
orig = open(r"章回版/江湖三女侠/044　第四十四回　魂断洪波　生难偿宿愿　心伤大变　死却惹思量.txt",
            encoding="utf-8").read()

def strip_marks(text):
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "〖":
            j = text.index("〗", i)
            inner = text[i + 1:j]
            surface = inner.split("|")[0][1:]
            out.append(surface)
            i = j + 1
        elif ch == "⟦":
            j = text.index("⟧", i)
            out.append(text[i + 1:j][1:])
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)

tl = tagged.split("\n")
ti = tl.index("---", 1)
tb = [l for l in tl[ti + 1:] if not re.match(r"^:::(\s+\S+)?\s*$", l)]
ol = orig.split("\n")
print("line counts:", len(tb), len(ol))
bad = 0
for i, (t, o) in enumerate(zip(tb, ol), 1):
    s = strip_marks(t)
    if s != o:
        bad += 1
        if bad > 5:
            break
        print("=== tagged body line", i)
        for k, (a, b) in enumerate(zip(s, o)):
            if a != b:
                print("diff at char", k)
                print("orig :", repr(o[max(0, k - 15):k + 15]))
                print("strip:", repr(s[max(0, k - 15):k + 15]))
                break
        else:
            print("length diff:", len(o), len(s))
            print("orig tail :", repr(o[-25:]))
            print("strip tail:", repr(s[-25:]))
print("bad lines:", bad)
