# Expressive VO: each segment = list of phrases, each with its own rate/pitch/volume and a gap after.
import sys, json, asyncio, subprocess, certifi, os
certifi.where = lambda: "/root/.ccr/ca-bundle.crt"
import edge_tts
S=sys.argv[1]; SPEC=json.load(open(sys.argv[2])); ONLY=sys.argv[3:] 
SR=48000
def ts(x):
    h,m,s=x.split(":"); s,ms=s.split(","); return int(h)*3600+int(m)*60+int(s)+int(ms)/1000
def fmt(t):
    ms=int(round(t*1000)); return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"
async def one(voice,text,rate,pitch,vol,out):
    c=edge_tts.Communicate(text,voice,rate=rate,pitch=pitch,volume=vol,boundary="WordBoundary")
    words=[]
    with open(out,"wb") as f:
        async for ch in c.stream():
            if ch["type"]=="audio": f.write(ch["data"])
            elif ch["type"]=="WordBoundary":
                a=ch["offset"]/1e7; words.append([ch["text"],a,a+ch["duration"]/1e7])
    return words
async def seg(k,sp):
    os.makedirs(f"{S}/vo2/tmp",exist_ok=True)
    parts=[]; allw=[]; t=0.0
    for i,ph in enumerate(sp["phrases"]):
        mp=f"{S}/vo2/tmp/{k}_{i}.mp3"
        for attempt in range(4):
            try: w=await one(sp["voice"],ph["t"],ph.get("rate","+0%"),ph.get("pitch","+0Hz"),ph.get("vol","+0%"),mp); break
            except Exception as e: print("retry",k,i,e); await asyncio.sleep(2)
        a=max(0,w[0][1]-0.04); e=w[-1][2]+ph.get("tail",0.10)
        wav=f"{S}/vo2/tmp/{k}_{i}.wav"
        subprocess.run(["ffmpeg","-y","-v","error","-i",mp,"-ss",f"{a:.3f}","-to",f"{e:.3f}","-ar",str(SR),"-ac","1",
          "-af","afade=t=in:d=0.01,areverse,afade=t=in:d=0.03,areverse",wav],check=True)
        for x in w: allw.append([x[0],t+x[1]-a,t+x[2]-a])
        d=float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",wav]))
        parts.append(wav); t+=d
        gap=ph.get("gap",0.12)
        if i<len(sp["phrases"])-1:
            g=f"{S}/vo2/tmp/{k}_{i}_gap.wav"
            subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i",f"anullsrc=r={SR}:cl=mono","-t",f"{gap:.3f}",g],check=True)
            parts.append(g); t+=gap
    lst=f"{S}/vo2/tmp/{k}.txt"; open(lst,"w").write("".join(f"file '{p}'\n" for p in parts))
    raw=f"{S}/vo2/tmp/{k}_raw.wav"
    subprocess.run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i",lst,"-c","copy",raw],check=True)
    # "ad read" processing: clean lows, presence lift, compression, a touch of air
    subprocess.run(["ffmpeg","-y","-v","error","-i",raw,"-af",
      "highpass=f=85,equalizer=f=250:t=q:w=1.2:g=-2,equalizer=f=3200:t=q:w=1.0:g=3.5,equalizer=f=9000:t=h:w=2000:g=2,"
      "acompressor=threshold=-20dB:ratio=3.5:attack=4:release=90:makeup=4,alimiter=limit=0.95",
      f"{S}/vo/{k}.wav"],check=True)
    open(f"{S}/vo/{k}.wav.srt","w").write("\n".join(f"{i+1}\n{fmt(a)} --> {fmt(e)}\n{w}\n" for i,(w,a,e) in enumerate(allw)))
    print(k, round(t,2), "s")
async def main():
    await asyncio.gather(*[seg(k,sp) for k,sp in SPEC.items() if not ONLY or k in ONLY])
asyncio.run(main())
