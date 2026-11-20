import json, re, subprocess, sys
S = sys.argv[1]
starts = {"s1":0.4,"s2":5.0,"s2b":12.1,"s3":16.2,"s4a":25.6,"s4b":35.4,"s5a":47.4,"s5b":58.8}
END = 66.5
def dur(f):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f]))
def ts(x):
    h,m,s = x.split(":"); s,ms = s.split(",")
    return int(h)*3600+int(m)*60+int(s)+int(ms)/1000
def disp(w):
    w = re.sub(r"([oOgG])'", lambda m: m.group(1)+"‘", w)
    return w.replace("'", "’")
merges = [(["Ay-Si-Pi","Ay-Ti"], "ICP IT"), (["yigirma","to'rt","soat,","yetti","kun"], "24/7")]
segs = []
for k, st in starts.items():
    f = f"{S}/vo/{k}.mp3"
    txt = open(f+".srt").read().strip().split("\n\n")
    words = []
    for b in txt:
        ln = b.split("\n"); a, e = ln[1].split(" --> ")
        words.append({"w": ln[2], "a": st+ts(a), "e": st+ts(e)})
    # attach punctuation from the source sentence: srt drops it, so recover from original text
    segs.append({"id":k, "start":st, "end":st+dur(f), "words":words})
# original texts with punctuation for display
orig = {}
for line in open(f"{S}/tools/lines.txt"):
    k, t = line.rstrip("\n").split("|",1); orig[k] = t.replace(" —", "\u00a0—").split(" ")
for sg in segs:
    toks = orig[sg["id"]]
    assert len(toks) == len(sg["words"]), (sg["id"], toks, [w["w"] for w in sg["words"]])
    for w, t in zip(sg["words"], toks): w["w"] = t
    # merges
    ws = sg["words"]; out = []; i = 0
    while i < len(ws):
        done = False
        for seq, rep in merges:
            n = len(seq)
            if [x["w"].rstrip(",") for x in ws[i:i+n]] == [s.rstrip(",") for s in seq]:
                tail = ws[i+n-1]["w"][-1] if ws[i+n-1]["w"][-1] in ",.!?" else ""
                out.append({"w":rep+tail, "a":ws[i]["a"], "e":ws[i+n-1]["e"]}); i += n; done = True; break
        if not done: out.append(ws[i]); i += 1
    for w in out: w["w"] = disp(w["w"])
    sg["words"] = out
    # chunk into subtitle lines
    chunks = []; cur = []
    for w in out:
        if cur and len(" ".join(x["w"] for x in cur+[w])) > 22:
            chunks.append(cur); cur = []
        cur.append(w)
        if w["w"][-1] in ",.!?—":
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    sg["chunks"] = [{"a":c[0]["a"], "e":c[-1]["e"], "words":c} for c in chunks]
json.dump({"end":END, "segs":segs}, open(f"{S}/timeline.json","w"), ensure_ascii=False, indent=1)
for sg in segs:
    print(sg["id"], round(sg["start"],2), round(sg["end"],2), " | ".join(" ".join(w["w"] for w in c["words"]) for c in sg["chunks"]))
