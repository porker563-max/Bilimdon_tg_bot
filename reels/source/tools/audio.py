import json, sys, subprocess, numpy as np
from scipy.signal import butter, sosfilt, fftconvolve
S=sys.argv[1]; SR=44100
TL=json.load(open(f"{S}/timeline.json")); END=TL["end"]; N=int(END*SR)
SEG={s["id"]:s for s in TL["segs"]}
W=lambda k,i: SEG[k]["words"][i]["a"]
rng=np.random.default_rng(7)
def bus(): return np.zeros((N,2))
def lp(x,f,o=2): return sosfilt(butter(o,f,'low',fs=SR,output='sos'),x,axis=0)
def hp(x,f,o=2): return sosfilt(butter(o,f,'high',fs=SR,output='sos'),x,axis=0)
def bp(x,a,b,o=2): return sosfilt(butter(o,[a,b],'band',fs=SR,output='sos'),x,axis=0)
def place(b,sig,t,gain=1.0,pan=0.0):
    i=int(t*SR); 
    if i>=N: return
    if sig.ndim==1: sig=np.stack([sig*np.sqrt((1-pan)/2)*1.414,sig*np.sqrt((1+pan)/2)*1.414],1)
    n=min(len(sig),N-i); b[i:i+n]+=sig[:n]*gain
def env(n,a=0.005,d=0.2,sus=0.0,rel=None):
    t=np.arange(n)/SR; e=np.minimum(1,t/max(a,1e-4))*np.exp(-np.maximum(0,t-a)/d)
    return e
def tt(d): return np.arange(int(d*SR))/SR
def saw(f,t,ph=0): return 2*((f*t+ph)%1)-1
def note(n): return 440*2**((n-69)/12)
def reverb(x,dur=2.2,mix=0.25,damp=4000):
    ir=rng.standard_normal((int(dur*SR),2))*np.exp(-np.arange(int(dur*SR))/SR*3.2/dur*2)[:,None]
    ir=lp(ir,damp); ir/=np.sqrt((ir**2).sum(0))
    wet=np.stack([fftconvolve(x[:,c],ir[:,c])[:len(x)] for c in range(2)],1)
    return x*(1-mix)+wet*mix*1.2
# ---------------- instruments
def kick(d=0.45,f0=160,f1=45):
    t=tt(d); f=f1+(f0-f1)*np.exp(-t*30); ph=2*np.pi*np.cumsum(f)/SR
    return np.sin(ph)*np.exp(-t*7)+0.15*np.exp(-t*400)*lp(rng.standard_normal(len(t)),4000)
def clap():
    t=tt(0.3); n=bp(rng.standard_normal(len(t)),900,2600)
    e=np.zeros(len(t))
    for o in (0,0.01,0.02): e+=np.exp(-np.maximum(0,t-o)*60)*(t>=o)
    e+=0.6*np.exp(-np.maximum(0,t-0.03)*14)*(t>=0.03)
    return n*e*0.9
def hat(d=0.05):
    t=tt(max(d*4,0.1)); n=hp(rng.standard_normal(len(t)),7000); return n*np.exp(-t/d)*0.6
def supersaw(fs,d,cut=3000,a=0.01,dec=0.25):
    t=tt(d); x=np.zeros(len(t))
    for f in fs:
        for k,det in enumerate((-0.12,-0.05,0,0.05,0.12)): x+=saw(f*2**(det/12),t,rng.random())
    x/= (len(fs)*5); x=lp(x,cut); e=np.minimum(1,t/a)*np.exp(-t/dec); return x*e
def pad(fs,d,cut=1100,att=0.6):
    t=tt(d); x=np.zeros((len(t),2))
    for f in fs:
        for c in range(2):
            for det in (-0.08,0.08):
                x[:,c]+=saw(f*2**((det+(0.03 if c else -0.03))/12),t,rng.random())
    x/=(len(fs)*2); x=lp(x,cut)
    e=np.minimum(1,t/att)*np.minimum(1,(d-t)/0.5).clip(0,1); return x*e[:,None]
def bass(f,d,cut=500):
    t=tt(d); x=0.6*saw(f,t)+0.6*np.sin(2*np.pi*f*t); x=lp(x,cut)
    e=np.minimum(1,t/0.005)*np.exp(-t/0.35)*np.clip((d-t)/0.02,0,1); return x*e
def pluck(f,d=0.6):
    t=tt(d); x=sum(np.sin(2*np.pi*f*k*t)*np.exp(-t*(4+k*3))/k for k in range(1,7)); return x*np.minimum(1,t/0.002)*0.6
def piano(f,d=2.2):
    t=tt(d); x=sum(np.sin(2*np.pi*f*k*t*(1+0.0004*k*k))*np.exp(-t*(1.2+k*0.9))/(k**1.3) for k in range(1,8))
    return x*np.minimum(1,t/0.004)*0.55
# ---------------- SFX
def ding(f=1318):
    t=tt(0.6); x=np.sin(2*np.pi*f*t)*np.exp(-t*9)+0.5*np.sin(2*np.pi*f*1.5*t)*np.exp(-t*12)+0.2*np.sin(2*np.pi*f*3*t)*np.exp(-t*20)
    return x*np.minimum(1,t/0.002)*0.5
def popfx(f0=900,f1=250,d=0.12):
    t=tt(d); f=f1+(f0-f1)*np.exp(-t*40); return np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t*30)*0.8
def whoosh(d=0.6,lo=300,hi=4000,rev=False):
    t=tt(d); n=rng.standard_normal(len(t)); x=np.zeros(len(t))
    segs=12
    for k in range(segs):
        a=int(k*len(t)/segs); b=int((k+1)*len(t)/segs)
        fc=lo*(hi/lo)**(k/segs if not rev else 1-k/segs)
        x[a:b]=bp(n,fc*0.7,min(fc*1.4,SR/2-100))[a:b]
    e=np.sin(np.pi*t/d)**2; return x*e*1.2
def riser(d):
    t=tt(d); n=rng.standard_normal(len(t)); out=np.zeros(len(t)); segs=40
    for k in range(segs):
        a=int(k*len(t)/segs); b=int((k+1)*len(t)/segs); fc=400*(9000/400)**(k/segs)
        out[a:b]=bp(n,fc*0.8,min(fc*1.25,20000))[a:b]
    f=110*(880/110)**(t/d); tone=saw(0,t)*0; tone=np.sin(2*np.pi*np.cumsum(f)/SR)*0.3
    return (out*0.8+tone)*(t/d)**2
def impact():
    t=tt(2.5); boom=np.sin(2*np.pi*np.cumsum(55+80*np.exp(-t*12))/SR)*np.exp(-t*2.2)
    n=lp(rng.standard_normal(len(t)),3000)*np.exp(-t*6)*0.5
    return (boom+n)*0.9
def fail():
    t=tt(0.7); f=np.where(t<0.25,330,220)*(1-0.15*t); x=np.sign(np.sin(2*np.pi*np.cumsum(f)/SR))*0.3
    x=lp(x,1200); return x*np.exp(-((t%0.3))*4)*np.clip((0.7-t)/0.1,0,1)
def ring(d=1.0):
    t=tt(d); f=np.where(np.sin(2*np.pi*18*t)>0,1046,1318); x=np.sin(2*np.pi*np.cumsum(f)/SR)
    return x*(t<0.8)*np.minimum(1,t/0.01)*0.25
def tick():
    t=tt(0.03); return hp(rng.standard_normal(len(t)),3000)*np.exp(-t*300)
# ================= MUSIC
mus=bus()
# ---- Part A (0..23.9) tense, 100 BPM, A minor
bA=60/100
progA=[[57,60,64],[53,57,60],[50,53,57],[52,56,59]]  # Am F Dm E
for bar in range(10):
    t0=bar*4*bA
    if t0>=23.9: break
    ch=progA[bar%4]
    dark = t0>=15.9
    p=pad([note(n-12) for n in ch], 4*bA+0.6, cut=700 if dark else 1100, att=0.8)
    place(mus,p,t0,0.32 if not dark else 0.26)
    # pulsing 8th bass
    if not dark:
        for k in range(8):
            tb=t0+k*bA/2
            if tb<15.9: place(mus,bass(note(ch[0]-24),bA/2*0.9,cut=380),tb,0.45 if t0>4.9 else 0.3)
    # clock ticks
    for k in range(8):
        tb=t0+k*bA/2
        if tb<15.9 and tb>0.3: place(mus,tick(),tb,0.18 if k%2 else 0.3,pan=0.3 if k%2 else -0.3)
# scene 2 adds soft kick
for k in range(int((15.9-4.95)/bA)):
    place(mus,kick(0.35,120,45),4.95+k*bA,0.5)
# scene 3: heartbeat + sad piano
for k in range(10):
    tb=16.2+k*0.85
    if tb<22.4: place(mus,kick(0.3,90,40),tb,0.55); place(mus,kick(0.3,80,38),tb+0.22,0.35)
mel=[(16.3,76),(17.3,74),(18.3,72),(19.6,71),(20.6,69),(21.6,68)]
for tm,n in mel: place(mus,piano(note(n)),tm,0.35,pan=-0.1); place(mus,piano(note(n-12)),tm,0.2,pan=0.1)
place(mus,riser(1.5),22.4,0.55)
place(mus,impact(),23.9,1.0)
# ---- Part B (24.0..END) 124 BPM C major
bpm=124; b=60/bpm; T0=24.0
progB=[[60,64,67],[55,59,62],[57,60,64],[53,57,60]]   # C G Am F
roots=[48,43,45,41]
endT=64.6
nbeats=int((endT-T0)/b)
for k in range(nbeats):
    tb=T0+k*b; bar=k//4; ch=progB[bar%4]; r=roots[bar%4]
    place(mus,kick(),tb,0.9)
    if k%2==1: place(mus,lp(clap(),6000),tb,0.32,pan=0.05)
    place(mus,lp(hat(0.06),11000),tb+b/2,0.14,pan=0.25)
    place(mus,lp(hat(0.02),10000),tb+b/4,0.06,pan=-0.25); place(mus,lp(hat(0.02),10000),tb+3*b/4,0.06,pan=-0.25)
    # offbeat bass
    place(mus,bass(note(r-12),b/2*0.95,cut=700),tb+b/2,0.55)
    # chord stabs on offbeats pattern
    if k%4 in (0,): place(mus,pad([note(n) for n in ch],4*b,cut=1800,att=0.05),tb,0.16)
    st=supersaw([note(n) for n in ch],0.3,cut=3500,dec=0.12)
    if k%4 in (1,3) or (k%8==6): place(mus,np.stack([st,st],1),tb+b/2,0.22)
# arpeggio pluck from 35.35
arp=[0,2,1,2]
for k in range(int((endT-35.35)/(b/2))):
    tb=35.35+k*b/2; bar=int((tb-T0)/(4*b)); ch=progB[bar%4]
    n=ch[arp[k%4]]+12; place(mus,pluck(note(n),0.4),tb,0.16,pan=0.4 if k%2 else -0.4)
# end chord
place(mus,pad([note(n) for n in [60,64,67,72]],2.4,cut=2500,att=0.02),endT,0.35)
place(mus,impact(),endT,0.6)
place(mus,kick(),endT,0.9)
mus=reverb(mus,1.6,0.18)
# ================= SFX
sfx=bus()
S1T=[0.45,0.9,1.3,1.65,1.95,2.2,2.45,2.68,2.88,3.06,3.22,3.37]
for i,t in enumerate(S1T): place(sfx,ding(1318*2**((i%5)/12*2)),t,0.45,pan=(i%3-1)*0.3)
for i in range(18): place(sfx,ding(1568*2**(((i*7)%6)/12)),2.0+i*0.15,0.22,pan=((i*5)%7/3.5-1)*0.7)
place(sfx,popfx(),3.5,0.6)
place(sfx,whoosh(0.7,200,5000),4.45,0.6)
for i in range(12): place(sfx,ding(1175*2**((i%4)/12*2)),5.5+i*0.52,0.3,pan=-0.5 if i%2==0 else 0.5)
for k in range(4): place(sfx,ring(),6.4+k*1.5,0.35,pan=0.5)
place(sfx,popfx(500,200,0.15),12.5,0.6)
place(sfx,whoosh(0.8,3000,200,False),15.6,0.5)
LOSE=[W('s3',3),W('s3',4)+.3,W('s3',7),W('s3',8)+.2,W('s3',10),W('s3',11)]
for t in LOSE: place(sfx,fail(),t,0.35); place(sfx,whoosh(0.4,800,200),t,0.25)
place(sfx,whoosh(0.6,300,6000),23.9,0.6)
place(sfx,popfx(1200,400,0.12),24.25,0.5); place(sfx,popfx(1500,500,0.12),24.55,0.5)
place(sfx,whoosh(0.6,400,5000),25.6,0.45)
BOT=[("in",25.95),("out",26.45),("in",27.55),("out",27.95),("in",29.0),("out",29.35),("in",30.2),("out",30.55)]
for k,t in BOT: place(sfx,popfx(700,350,0.1) if k=="in" else ding(1760),t,0.45 if k=="in" else 0.3)
place(sfx,whoosh(0.6,400,5000),31.35,0.4)
for i in range(4): place(sfx,ding(2093 if i%2 else 1760),31.9+i*0.55,0.25)
place(sfx,popfx(900,300,0.15),32.85,0.55)
place(sfx,whoosh(0.6,400,5000),35.15,0.4)
t247=W('s4b',3); place(sfx,impact(),t247-0.15,0.35); place(sfx,whoosh(1.4,500,6000),t247,0.25)
hpT=W('s4b',5)
for i in range(5): place(sfx,ding(1568*2**(i*2/12)),hpT+0.1+i*0.22,0.22)
place(sfx,whoosh(0.5,3000,300),40.9,0.35)
place(sfx,popfx(),W('s4b',9)-.1,0.5)
for i in (12,14,16,19): place(sfx,popfx(1000,300,0.12),W('s4b',i)-0.1,0.55)
place(sfx,whoosh(0.7,400,6000),47.0,0.5)
place(sfx,impact(),W('s5a',1)-0.2,0.45)
for i in range(8): place(sfx,popfx(500+i*80,250+i*40,0.08),48.2+i*0.35,0.3)
for i in (11,12,15): place(sfx,popfx(1100,400,0.1),W('s5a',i)-.05,0.5)
place(sfx,whoosh(0.7,400,6000),58.5,0.5)
place(sfx,popfx(),58.85,0.5)
bt=W('s5b',5)-0.1; place(sfx,popfx(900,300,0.15),bt,0.6)
place(sfx,impact(),W('s5b',8)-0.05,0.35)
tp=bt+1.0
while tp<END-0.5: place(sfx,tick(),tp+0.2,0.35); tp+=1.3
sfx=reverb(sfx,1.0,0.15)
# ================= VOICE
vo=bus()
for k,sg in SEG.items():
    raw=subprocess.check_output(["ffmpeg","-v","error","-i",f"{S}/vo/{k}.mp3","-f","f32le","-ac","1","-ar",str(SR),"-"])
    x=np.frombuffer(raw,np.float32).astype(float)
    x=hp(x,90); x=x/np.max(np.abs(x))*0.9
    place(vo,x,sg["start"],1.0)
# ducking envelope
lvl=np.abs(vo[:,0]); win=int(0.08*SR); k=np.ones(win)/win
envv=np.convolve(lvl,k,'same'); envv=np.convolve(envv,np.ones(int(0.25*SR))/int(0.25*SR),'same')
duck=1-0.55*np.clip(envv/0.05,0,1)
mus*=duck[:,None]
sp=envv>0.02
import math
print('VO/MUS dB in speech', 20*math.log10(np.sqrt((vo[sp]**2).mean())/np.sqrt(((mus*0.30)[sp]**2).mean())))
print('VO/SFX dB', 20*math.log10(np.sqrt((vo[sp]**2).mean())/np.sqrt(((sfx*0.55)[sp]**2).mean()+1e-12)))

# fade
fade=np.ones(N); fade[-int(1.5*SR):]=np.linspace(1,0,int(1.5*SR)); 
mix=mus*0.30*fade[:,None]+sfx*0.55+vo*1.0
# soft limiter
mix=np.tanh(mix*1.1)/np.tanh(1.1)
mix/=np.max(np.abs(mix))/0.95
(mix.astype(np.float32)).tofile(f"{S}/mix.f32")
subprocess.run(["ffmpeg","-y","-v","error","-f","f32le","-ar",str(SR),"-ac","2","-i",f"{S}/mix.f32","-af","loudnorm=I=-14:TP=-1.0:LRA=11","-ar","48000",f"{S}/mix.wav"],check=True)
print("ok",N/SR)
