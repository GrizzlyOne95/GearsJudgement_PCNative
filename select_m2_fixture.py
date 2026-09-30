"""Automatically rank candidate M2 sublevels for world-serialization proof.

Hard requirements:
  World >=1, WorldInfo >=1, Level >=1, Model >=1, Polys >=1
  REJECT SkeletalMesh>0, failed decompression, failed parse

Strong preferences:
  StaticMesh small, StaticMeshComponent small, Texture2D few, SoundNodeWave 0,
  ShaderCache <=1, CoverLink preferably 0 initially, sequence ok,
  gameplay actors >=1, collision BSP >=1

Score (lower is better):
  file_size_mb*10 + export_count*0.1 + static_mesh_count*4 + texture_count*3 + coverlink_count*5 + sequence_complexity*1
Disqualify SkeletalMesh.

Optimizes for serialization surface area, not raw bytes.
Saves chosen manifest as M2_FIXTURE_SELECTION.json with rationale.

Usage:
  python select_m2_fixture.py [--work-dir e2-surface] [--top 10] [--out M2_FIXTURE_SELECTION.json]
  If no explicit package list, scans CookedXbox360 SP_*.xxx (437 packages)
"""
import collections, json, os, subprocess, sys, math, pathlib

PROBE = r"C:\Games\NostalgiaBundle\projects\judgment-native\package-probe\build\Release\judgment-package-probe.exe"
COOK = r"C:\Games\GearsJudgement\UnrealEngine3-Jack\GearGame\CookedXbox360"
CENSUS = r"C:\Games\_judgment-scratch\census-judgment-v2.csv"

def manifest_for(work_dir, name):
    src = os.path.join(COOK, name)
    unc = os.path.join(work_dir, name + ".unc")
    man = os.path.join(work_dir, name + ".json")
    if not os.path.exists(unc):
        subprocess.run([PROBE, "--decompress-package", src, unc], capture_output=True, text=True)
    if not os.path.exists(unc):
        return None, "decompress_failed"
    if not os.path.exists(man):
        subprocess.run([PROBE, "--manifest", unc, man], capture_output=True, text=True)
    if not os.path.exists(man):
        return None, "manifest_failed"
    try:
        with open(man) as h:
            return json.load(h), None
    except:
        return None, "json_failed"

def score_package(doc, name, size_mb):
    cnt = collections.Counter(e["class_name"] for e in doc["exports"])
    # Hard requirements
    required = {"World","WorldInfo","Level","Model","Polys"}
    missing = [c for c in required if cnt.get(c,0) <1]
    if missing:
        return None, f"missing {missing}"
    if cnt.get("SkeletalMesh",0) >0:
        return None, "SkeletalMesh>0 rejected"
    export_count = len(doc["exports"])
    # M2 needs a real world proof, not an FX stub: require meaningful export count and gameplay
    if export_count < 20:
        return None, f"too_small_for_world_proof exp{export_count}<20"
    gameplay = sum(cnt.get(k,0) for k in ("PlayerStart","Trigger","NavigationPoint","InterpActor","BlockingVolume","StaticMeshActor","Brush","ModelComponent"))
    if gameplay < 1:
        return None, "no gameplay/collision actor"
    # Unknown structure already handled by manifest_for failure
    # Strong preferences - not hard reject but score penalty
    static_mesh = cnt.get("StaticMesh",0)
    static_comp = cnt.get("StaticMeshComponent",0)
    texture = cnt.get("Texture2D",0) + cnt.get("LightMapTexture2D",0) + cnt.get("ShadowMapTexture2D",0)
    sound = cnt.get("SoundNodeWave",0)
    shader = cnt.get("ShaderCache",0)
    cover = cnt.get("CoverLink",0)
    seq = sum(cnt.get(k,0) for k in cnt if k.startswith("Seq"))
    # Compute score - optimize for serialization surface, not raw bytes
    score = (size_mb*10 + export_count*0.1 + static_mesh*4 + texture*3 + cover*5 + seq*0.1 + static_comp*0.05)
    # Bonus for BSP-heavy small: if Model/Polys present and StaticMesh low, reduce score slightly
    if static_mesh==0 and texture<=2:
        score *= 0.9
    # Penalize SoundNodeWave and large texture counts for M2 (want no audio, few textures)
    if sound>0:
        score += sound*5
    if texture>50:
        score += (texture-50)*2
    details={
        "World":cnt.get("World",0),"WorldInfo":cnt.get("WorldInfo",0),"Level":cnt.get("Level",0),
        "Model":cnt.get("Model",0),"Polys":cnt.get("Polys",0),
        "StaticMesh":static_mesh,"StaticMeshComponent":static_comp,
        "Texture2D":texture,"SoundNodeWave":sound,"ShaderCache":shader,"CoverLink":cover,
        "Sequence":seq, "export_count":export_count, "size_mb":round(size_mb,2),
        "distinct_classes":len(cnt)
    }
    return score, details

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--work-dir", default=r"C:\Games\_judgment-scratch\e2-surface")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--out", default=r"C:\Games\_judgment-scratch\M2_FIXTURE_SELECTION.json")
    ap.add_argument("packages", nargs="*")
    args=ap.parse_args()

    os.makedirs(args.work_dir, exist_ok=True)

    # Get candidate list
    if args.packages:
        names=args.packages
    else:
        # Scan census for SP_* and not _P (persistent) maybe? But we want sublevels, so include all SP
        # Use census file to get names
        names=[]
        try:
            with open(CENSUS) as f:
                for line in f:
                    if "SP_" in line:
                        # parse path
                        # format: path,size,endian,ver,...
                        path=line.split(",")[0].strip().strip('"')
                        base=os.path.basename(path)
                        if base.startswith("SP_"):
                            names.append(base)
        except:
            # fallback list Cook dir
            names=[f for f in os.listdir(COOK) if f.startswith("SP_") and f.endswith(".xxx")]
        # Deduplicate and sort
        names=sorted(set(names))
        print(f"scanning {len(names)} SP packages from census")

    results=[]
    failed=[]
    for name in names:
        src=os.path.join(COOK, name)
        if not os.path.exists(src):
            continue
        size_mb=os.path.getsize(src)/1048576
        # Quick filter: very large files >50MB decompressed likely have many textures; still score but deprioritize
        doc, err = manifest_for(args.work_dir, name)
        if doc is None:
            failed.append((name, err))
            print(f"  {name}: FAILED {err}")
            continue
        sc, details = score_package(doc, name, size_mb)
        if sc is None:
            print(f"  {name}: REJECT {details}")
            failed.append((name, details))
            continue
        # Also compute decompressed size
        unc=os.path.join(args.work_dir, name+".unc")
        dec_mb=os.path.getsize(unc)/1048576 if os.path.exists(unc) else size_mb*3
        results.append((sc, name, details, doc, dec_mb))
        print(f"  {name}: score {sc:.1f} exp{details['export_count']} sm{details['StaticMesh']} tex{details['Texture2D']} cover{details['CoverLink']} size {size_mb:.1f}MB dec {dec_mb:.1f}MB")

    results.sort(key=lambda x: x[0])
    top=results[:args.top]
    print(f"\n=== TOP {len(top)} M2 CANDIDATES (lower score better) ===")
    for sc, name, d, doc, dec in top:
        print(f"{sc:7.1f} {name:35s} exp{d['export_count']:4d} sm{d['StaticMesh']:2d} tex{d['Texture2D']:2d} cover{d['CoverLink']:2d} seq{d['Sequence']:3d} {d['size_mb']:5.1f}MB dec{dec:5.1f}MB classes{d['distinct_classes']}")

    # Save selection
    if top:
        best_sc, best_name, best_details, best_doc, best_dec = top[0]
        # Build conversion-surface manifest for best
        surface={
            "Package": {"name":best_name, "compressed_mb":best_details["size_mb"], "decompressed_mb":round(best_dec,2), "name_count":best_doc.get("name_count", len(best_doc.get("names",[]))), "import_count":len(best_doc["imports"]), "export_count":len(best_doc["exports"])},
            "Required_world_classes": {k:best_details[k] for k in ["World","WorldInfo","Level","Model","Polys"]},
            "Geometry": {k:best_details.get(k,0) for k in ["StaticMesh","StaticMeshComponent"]},
            "Gameplay": {i:best_doc["exports"][i]["class_name"] for i in range(min(5,len(best_doc["exports"])))},
            "Platform_sensitive": {k:best_details.get(k,0) for k in ["Texture2D","ShaderCache","SoundNodeWave","SkeletalMesh"]},
            "Conversion_state": "to be determined by world_package_proof.py (KNOWN/OPAQUE_PRESERVE_UNVERIFIED/TRANSIENT/UNSUPPORTED)",
            "Score_details": best_details,
            "Ranking": [{"rank":i+1,"name":n,"score":round(sc,1),"details":d} for i,(sc,n,d,_,_) in enumerate(top)],
            "Failed_or_rejected": len(failed),
            "Selection_rationale": "BSP-heavy, no SkeletalMesh, minimal StaticMesh/texture, low sequence complexity, optimizes serialization surface not raw bytes. Saved as documented answer to 'Why was this map selected?'"
        }
        # Build full class histogram for best
        hist=collections.Counter(e["class_name"] for e in best_doc["exports"])
        surface["Class_histogram"]=dict(hist.most_common(30))
        # Required world classes presence
        surface["Geometry_detail"]= {"StaticMesh":hist.get("StaticMesh",0), "StaticMeshComponent":hist.get("StaticMeshComponent",0), "Brush":hist.get("Brush",0), "BrushComponent":hist.get("BrushComponent",0), "ModelComponent":hist.get("ModelComponent",0)}
        # Gameplay detail
        gameplay_keys=[k for k in hist if k in ("PlayerStart","NavigationPoint","Trigger","Sequence","InterpActor","CoverLink","BlockingVolume","StaticMeshActor")]
        surface["Gameplay_detail"]={k:hist.get(k,0) for k in gameplay_keys}
        surface["Platform_detail"]={k:hist.get(k,0) for k in ["Texture2D","LightMapTexture2D","ShaderCache","SoundNodeWave","SkeletalMesh","ParticleSystem"]}

        with open(args.out,"w") as f:
            json.dump(surface,f,indent=2)
        print(f"\nwrote {args.out}")

if __name__=="__main__":
    main()
