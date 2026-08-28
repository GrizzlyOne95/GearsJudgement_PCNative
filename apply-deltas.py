import os,re,shutil
from collections import Counter
STAGE=r"C:\Users\iestu\AppData\Local\Temp\opencode\delta-staging"
SRC=r"C:\Games\Gears 3 Files\gears_of_war_3_2011-09-14\Development\Src"
BAK=r"C:\Users\iestu\AppData\Local\Temp\opencode\hdr-backup\delta-v52"
os.makedirs(BAK,exist_ok=True)
NAME_RE=re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?::\d+)?\s*(?:\[[^\]]*\])?\s*;",re.A)
def sig(lines):
    out=[]
    for r2 in lines:
        s2=re.sub(r"\s+"," ",r2.strip())
        if not s2 or s2.startswith("//"): continue
        nm=NAME_RE.search(s2)
        if not nm: continue
        ln=nm.group(1).lower()
        if ln=="script_align" or ln.endswith("_deprecated"): continue
        out.append(s2.lower())
    return Counter(out)
files=[]
for root,_,fs in os.walk(SRC):
    if root.endswith("Inc"):
        files += [os.path.join(root,f) for f in fs if f.endswith(".h")]
applied=[];failed=[];fbacked={}
for f in sorted(os.listdir(STAGE)):
    if not f.endswith(".block.txt"): continue
    owner=f[:-10]
    stg=[l.rstrip("\n") for l in open(os.path.join(STAGE,f),encoding="latin1") if l.strip()]
    B=re.escape(f"//## BEGIN PROPS {owner}"); E=f"//## END PROPS {owner}"
    pat=re.compile(B+r"(?![A-Za-z0-9_])")
    hit=None
    for p in files:
        txt=open(p,"rb").read().decode("latin1")
        m=pat.search(txt)
        if not m: continue
        e=txt.find(E,m.end())
        while e>0 and len(txt)>e+len(E) and re.match(r"[A-Za-z0-9_]",txt[e+len(E)]):
            e=txt.find(E,e+1)
        if e<0: continue
        hit=(p,m.end(),e); break
    if not hit:
        failed.append((owner,"block not found")); continue
    p,i,j=hit
    txt=open(p,"rb").read().decode("latin1")
    a,b=sig(txt[i:j].splitlines()),sig(stg)
    lost=list((a-b).elements())
    extras=list((b-a).elements())
    if lost:
        # a kept member would vanish -> refuse
        failed.append((owner,"LOST kept members: %s"%lost[:4])); continue
    if not extras:
        failed.append((owner,"no-op")); continue
    if p not in fbacked:
        shutil.copyfile(p,os.path.join(BAK,os.path.basename(p))); fbacked[p]=1
    nl="\r\n" if "\r\n" in txt else "\n"
    indented=["    "+l.strip() for l in stg]
    open(p,"wb").write((txt[:i]+nl+nl.join(indented)+nl+txt[j:]).encode("latin1"))
    applied.append(owner)
print("applied:",len(applied))
print("failed:",len(failed),"files:",len(fbacked))
for x in failed[:20]: print("  FAIL:",x)
