# Known-modified source files (change manifest)

Files below were edited in place in the build tree. Those with a patch are
covered; the rest pre-date surviving per-file backups and exist only in the
live tree plus the _Backups/src-port-snapshot-20260824 frozen baseline.
Never commit these files themselves - regenerate diffs against baselines.

## Core engine (Development/Src/Core/Src)
- UnObj.cpp        - JUDGMENT* diagnostics: layout dump, ExitProperties owner
                     tracking, CDO watchdog, generic CLS chain dumper
- UnProp.cpp       - array-destroy validator, destroy trace
- UnLinker.cpp     - foreign-package ceiling, CEX limit, linker forensics,
                     rooted linkers
- UnClass.cpp      - script relink / replace-path instrumentation
- UnObjGC.cpp      - GC guard changes (flag-gated)

## GearGame (Development/Src/GearGame)
- Src/GearGame.cpp         - GJudgNat_* STRUCT_OFFSET anchor tables, loader glue
- Src/GearPawn.cpp         - Infantry MI-base removal follow-ups, layout fixes
- Inc/GearGameAIClasses.h          - see patch 0001
- Inc/GearGameClasses.h            - see patches 0003
- Inc/GearGamePawnClasses.h        - see patch 0003 (+ earlier edits: AGearPawn
                                     tail floats removed, Infantry MI bases removed)
- Inc/GearGameSpawnerClasses.h     - see patch 0003
- Inc/GearGameSequenceClasses.h    - see patch 0003
- Inc/GearGameJudgmentStructs.h    - NEW FILE, authored: Judgment-only structs
- Engine/Inc/EngineClasses.h       - see patch 0004
- Engine-side: ~45 class-layout deltas across Engine headers documented in
  ENGINE-CLASS-DELTA.md at repo root (pre-baseline; no per-file diffs)

## Also authored (not engine source)
- Binaries/Win32/GearGame-JudgmentLoader-*.exe builds are compiled derivatives -
  never redistribute.
