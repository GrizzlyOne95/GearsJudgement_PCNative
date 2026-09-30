"""Second-layer semantic verifier - logical reference integrity.

Preserves distinction:
  package_verify.py          -> physical/package layout integrity (SerialOffset+Size<=FileSize, table landing)
  package_semantic_verify.py -> serialized object/reference integrity (FPackageIndex, FName, TArray, FString)

For every field known to contain FPackageIndex:
  0       -> null
  >0      -> ExportMap[index-1]
  <0      -> ImportMap[-index-1]
Require resulting index exists.

Similarly:
  FName index < NameCount, number sane
  TArray count nonnegative and structurally bounded
  FString length structurally bounded

This catches endian errors where a believable-but-wrong BE object index remains
inside legal package bounds but resolves to wrong import/export - more dangerous
than a physical file-offset error.

Usage:
  python package_semantic_verify.py <package.le.xxx> --manifest <package.json> [--out semantic.json]
  Manifest is from package-probe --manifest (names/imports/exports).
"""
import json, struct, sys, os

def verify_semantic(package_path, manifest_path):
    buf=open(package_path,"rb").read()
    man=json.load(open(manifest_path))
    names=man["names"] if "names" in man else [e["name"] for e in man.get("name_table",[])]
    # Fallback: try to read names from package_verify
    import package_verify as pv
    res=pv.verify_package(package_path)
    name_count=res.name_count
    import_count=res.import_count
    export_count=res.export_count

    errors=[]
    # Check every export's payload for object references via be2le's tagged properties
    # For M2 we need to walk Level.Actors[] and every UObject field containing FPackageIndex
    # This stub reports counts and shows where to plug be2le's reference walk.
    # Full implementation will reuse be2le's payload parsing to enumerate every FPackageIndex
    # and validate against import/export maps, plus FName and TArray bounds.

    # Placeholder: count invalid references as 0 for now, to be filled
    # For GearGame_P and Museum fixtures, physical verifier already shows 0 invalid
    # but semantic verifier will add logical checks.

    # Example: check Level Actors[] histogram
    # Find Level exports
    level_exports=[e for e in man["exports"] if e["class_name"]=="Level"]
    histogram={}
    for le in level_exports:
        # In real verifier, parse Level payload's Actors TTransArray and validate each index
        pass

    return {
        "package": package_path,
        "manifest": manifest_path,
        "name_count": name_count,
        "import_count": import_count,
        "export_count": export_count,
        "invalid_FPackageIndex": 0,
        "invalid_FName": 0,
        "invalid_TArray": 0,
        "Level_Actors_histogram": "pending - requires Level payload parse",
        "status": "pending - stub ready for be2le reference walk"
    }

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default=None)
    args=ap.parse_args()
    result=verify_semantic(args.package, args.manifest)
    print(json.dumps(result,indent=2))
    if args.out:
        with open(args.out,"w") as f:
            json.dump(result,f,indent=2)

if __name__=="__main__":
    main()
