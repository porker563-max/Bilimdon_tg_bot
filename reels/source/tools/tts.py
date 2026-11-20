import sys, asyncio, certifi
certifi.where = lambda: "/root/.ccr/ca-bundle.crt"
import edge_tts
async def main(voice, text, out, rate="+0%"):
    c = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    sub = edge_tts.SubMaker()
    with open(out, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio": f.write(ch["data"])
            elif ch["type"] in ("WordBoundary","SentenceBoundary"):
                sub.feed(ch)
    open(out + ".srt","w").write(sub.get_srt())
asyncio.run(main(*sys.argv[1:]))
