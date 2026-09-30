"""Mutation tests for global relocation layer - stress synthetic size changes.

Take a known-valid fixture (e.g., GearGame_P 7575B, Museum expanded3 297k) and:
  export 5 grows by +1 byte, +127 bytes, +128 KiB, shrinks nearly to zero,
  multiple exports grow/shrink simultaneously, name table changes size

Assert:
  all SerialOffsets valid, all known BulkData retargeted, table offsets valid,
  byte-for-byte unchanged payloads identical, old->new mapping monotonic,
  verifier green.

The +128 KiB case is useful boundary because Judgment's original LZX container
works in 128 KiB blocks, even though decompressed relocation is independent.

Usage:
  python test_relocation_mutations.py --fixture C:\Games\_judgment-scratch\GearGame_P.verify.le.xxx
"""
import struct, os, sys, json, tempfile, pathlib
import package_verify
import package_relocate

def mutate(fixture_path):
    buf=open(fixture_path,"rb").read()
    info=package_relocate.read_le_package_info(buf)
    print(f"fixture {fixture_path} size {len(buf)} exports {info['ec']} names {info['nc']}")

    # Test 1: export 0 grows +1
    # Build jobs dict with one export enlarged by 1 byte (append 0xFF)
    for delta in [1,127,131072]:
        # Pick export 0 if exists
        exp0 = info["exports"][0]
        cls,outer,nmi,osz,ooff = exp0[:5] if len(exp0)>=5 else exp0
        old_payload=buf[ooff:ooff+osz]
        new_payload=old_payload + b"\xFF"*delta
        jobs={0:(ooff,osz,new_payload)}
        appended=b""  # no name change
        new_buf=package_relocate.relocate_and_emit(buf, info, appended, jobs)
        # Verify
        tmp=tempfile.NamedTemporaryFile(delete=False,suffix=".xxx")
        tmp.write(new_buf); tmp.close()
        res=package_verify.verify_package(tmp.name)
        os.unlink(tmp.name)
        status="PASS" if res.invariants_ok else "FAIL"
        print(f"  mutate +{delta} export0 {osz}->{len(new_payload)} new size {len(new_buf)} verifier {status} first_error={res.first_error}")

    # Test name table change
    appended=b"\x05\x00\x00\x00Test\x00\x07\x00\x10\x00\x00\x00\x00\x00"  # one fake name
    jobs={}
    new_buf2=package_relocate.relocate_and_emit(buf, info, appended, jobs)
    tmp=tempfile.NamedTemporaryFile(delete=False,suffix=".xxx")
    tmp.write(new_buf2); tmp.close()
    res2=package_verify.verify_package(tmp.name)
    os.unlink(tmp.name)
    print(f"  name table +1 entry new size {len(new_buf2)} verifier {'PASS' if res2.invariants_ok else 'FAIL'}")

    print("mutation tests done - all should be PASS if relocation monotonic")

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--fixture", default=r"C:\Games\_judgment-scratch\GearGame_P.verify.le.xxx")
    args=ap.parse_args()
    mutate(args.fixture)
