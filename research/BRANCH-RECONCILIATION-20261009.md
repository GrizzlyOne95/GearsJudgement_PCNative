# Judgment PC-native branch reconciliation — 2026-10-09

This audit covers **GrizzlyOne95/GearsJudgement_PCNative**, not the separate
[ReXGlue fork](https://github.com/GrizzlyOne95/gears-judgement-recomp).
The ReXGlue fork was created with only `main`; its source baseline has no
outstanding inherited Git branches to merge. The older conversion repository
had seven other branches alongside `main`.

Issue tracking remaining decisions: [#8](https://github.com/GrizzlyOne95/GearsJudgement_PCNative/issues/8).

## Git topology and disposition

| Branch | Tip at audit | Relationship to `main` | Action |
|---|---|---|---|
| `chore/repository-content-policy` | `e9a0afe81dab` | fully behind / merged | safe to delete after verifying remote |
| `fix/gears3-steam-coop` | `0c8ceb630160` | fully behind / merged (PR #7) | safe to delete after verifying remote |
| `jules-campaign-conversion-plan-13287290722673609885` | `b03cba7e4178` | fully behind / merged (PR #5) | safe to delete after verifying remote |
| `feat-synthetic-v845-converter-harness-17854212739089917223` | `b9aae30e3a0b` | divergent, one unique commit (PR #4 closed unmerged) | review useful pieces; do not auto-merge |
| `jules-16527718599525064984-ac0584da` | `43834e3db863` | divergent, one unique commit (PR #3 closed unmerged) | review useful pieces; do not auto-merge |
| `judgment/port-workspace` | `4ad68fbc2b6b` | **no common ancestor** with main | preserve as independent history until curated |
| `judgment/skeletalmesh-20260930` | `b9835cf8e2c4` | **no common ancestor** with main | preserve as independent history until curated |

## Why not merge everything indiscriminately?

- PRs #3 and #4 add alternative v845 conversion/relocation implementations
  (`v845_rewrite.py`, `v845_converter.py`, associated tests). `main` already
  contains `v845_package_rewrite.py` and `tests/test_v845_rewrite.py`;
  blindly merging creates competing implementations and could overwrite tests.
  Compare specific invariants, fail-closed behavior, export-offset relocation,
  populated FVert widening and ShaderCache tests before selectively adopting code.
- `judgment/port-workspace` is a **separate Git root** holding
  `JUDGMENT-PORT-STATUS.md` and build-response manifests. It is primarily
  research/status evidence, not a normal merge-ready feature branch.
- `judgment/skeletalmesh-20260930` is another **separate Git root** and contains
  substantially more than skeletal-mesh tweaks: v845 endian/package conversion,
  animation/geometry/nav/AI helpers, regression tests, campaign loading and
  play-through tooling. Many filenames overlap the present `main` tools.
  Replacing `main` with that tree or allowing an automatic two-root merge would
  risk losing the current layout, test harness and fork integration.

## Safe reconciliation plan

1. **Retain both unrelated-history branches.** Review their scripts/tests and
   research against `main`; decide whether a curated `native-ue3-lab/` subtree,
   a separate repository, or selective transfers would best preserve the working
   code. Do not use `git merge --allow-unrelated-histories` as a shortcut.
2. Compare PR #3 and #4 against `main` and cherry-pick **behavior with tests**
   rather than importing duplicate converter modules just to mark branches merged.
   Closed PRs are not evidence that their content was already merged.
3. After verifying each branch's unique work is preserved or consciously
   superseded, delete the three already-merged branches and any reviewed
   duplicates. Do **not** remove either independent workspace until the
   preservation decision is resolved.
4. Keep ReXGlue development in its own fork, tracked by the pinned submodule.
   Advance the parent gitlink only after the fork commit has been pushed.
5. Never commit retail XEX/packages/assets, generated recompilation output, or
   private game build trees into this public repository.

## Status of this audit

Completed: classified all eight heads, checked the old PR merge states, verified
that the fork has only `main`, preserved both unrelated histories, and recorded
the remaining decisions in issue #8.

**Not completed:** transferring converter/standalone-workspace implementations,
running their local regressions against a proprietary game build, or deleting
old remote branches. Those require code/content validation and a deliberate
preservation decision. The GitHub connector available for this work does not
expose branch deletion, so stale refs were left untouched rather than
force-updated or hidden.
