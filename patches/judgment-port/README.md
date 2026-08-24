# judgment-port patches

Deltas authored by this port against the unmodified build tree, kept here so
the work survives off-machine without ever committing Epic-licensed source.

## Base revision

- Tree: gears_of_war_3_2011-09-14 alpha drop (v828-native UE3 era), exactly as
  extracted locally before port edits began.
- No pristine copy of Development/Src is redistributed anywhere in this
  repository; patches apply onto a fresh extraction of that drop.

## Coverage

| Patch | Target | Contents |
| --- | --- | --- |
| 0001-gearai-v845-member-order.patch | GearGame/Inc/GearGameAIClasses.h | AGearAI props reordered to v845 relinked layout (227 members, simulation-verified) |
| 0002-gameplayercontroller-drop-currentsoundmode.patch | GameFramework/Inc/GameFrameworkClasses.h | removed FName CurrentSoundMode + VERIFY line (dropped in v845; -8B parent drift fix) |
| 0003-gearengine-gri-reorder.patch | GearGame/Inc/GearGameClasses.h | UGearEngine + GearGRI to v845 order |
| 0003-gearspawner-reorder.patch | GearGame/Inc/GearGameSpawnerClasses.h | GearSpawner to v845 order |
| 0003-locustcorpserlarva-underground-reorder.patch | GearGame/Inc/GearGamePawnClasses.h | GearPawn_LocustCorpserLarvaUndergroundBase to v845 |
| 0003-seqact-dummyweaponfire-reorder.patch | GearGame/Inc/GearGameSequenceClasses.h | SeqAct_DummyWeaponFire to v845 |
| 0004-engine-header-deltas-since-0816.patch | Engine/Inc/EngineClasses.h | accumulated deltas vs 2026-08-16 in-tree backup (incl. FileWriter v845 order) |

Every patch is verified by applying it onto its recorded pre-edit state and
byte-comparing against the live tree (7/7 PASS, 2026-08-24).

## Known gap

Edits made before the oldest surviving per-file backups have no diff coverage.
CHANGES-MANIFEST.md lists every known-modified file so nothing is forgotten.
A frozen baseline snapshot of Development/Src is kept out-of-repo at
_Backups/src-port-snapshot-20260824/; from that point forward every future edit
can be emitted as a real unified diff into this directory with the same
verify-before-publish treatment.

## Applying

From the build-tree root (fresh extraction of the same drop):

    git apply patches/judgment-port/0001-gearai-v845-member-order.patch
    git apply patches/judgment-port/0002-gameplayercontroller-drop-currentsoundmode.patch
    ... etc.

Plain unified diffs; patch -p1 also works. Order not significant today
(disjoint files), keep numeric order anyway.
