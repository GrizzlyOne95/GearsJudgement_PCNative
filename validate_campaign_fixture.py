"""Compare original mission graphs and require observed startup/objective state.

This validates a startup milestone, not a playable encounter or checkpoint restore.
Native fallback calls remain visible in the report even when startup passes.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from campaign_graph import GraphError, compare


FIXTURES = Path(r"C:\Games\_judgment-scratch\e2-surface")
ARTIFACTS = {
    "SP_E2_P": "textures-v2-20260930",
    "SP_E2_01_S": "navigation-20260930",
    "SP_E2_02_S": "animation-v1-20260930",
}
BASE = "TheWorld.PersistentLevel.Main_Sequence."
STARTUP = BASE + "Level_Startup."
REQUIRED = [
    ("complete", STARTUP + "SeqEvent_LevelLoaded_1"),
    ("complete", STARTUP + "SeqAct_MultiLevelStreaming_0"),
    ("complete", STARTUP + "SeqAct_WaitForLevelsVisible_8"),
    ("complete", STARTUP + "SeqAct_Checkpoint_5"),
    ("complete", STARTUP + "SeqAct_ToggleCinematicMode_5"),
    ("complete", STARTUP + "SeqAct_CameraFade_5"),
    ("complete", STARTUP + "SeqAct_DisplayChapterTitle_0"),
    ("complete", BASE + "MISSION_OBJECTIVES.SeqAct_ManageObjectives_1"),
]


def audit_ai_accessor_layer(text):
    """Require real singleton evidence and disclose the unported native Init/Tick."""
    enabled = "-JUDGAIACCESSORS" in text
    if not enabled:
        if "[JUDGAI]" in text or "[JUDGAI][PARTIAL]" in text:
            raise GraphError("AI prototype ran without its explicit flag")
        return None
    partial = re.findall(r"\[JUDGAI\]\[PARTIAL\] singleton=(\S+) root=(\d+) cdo=(\d+) native-init-pending=(\S+) tick-pending=(\d+)", text)
    if len(partial) != 1 or partial[0][1:] != (
            "1", "0", "ETQSystem,AISpawnManager,AIDebugTool", "1"):
        raise GraphError("missing or inconsistent partial AI initialization disclosure")
    instance = partial[0][0]
    calls = re.findall(r"\[JUDGAI\] get-instance caller=(\S+) instance=(\S+) root=(\d+) cdo=(\d+) count=(\d+)", text)
    if len(calls) < 3 or any(row[1] != instance or row[2:4] != ("1", "0") for row in calls):
        raise GraphError("AI accessors did not return the same real rooted singleton")
    initial = [row for row in calls if int(row[4]) <= 16]
    if [int(row[4]) for row in initial] != list(range(1, len(initial) + 1)):
        raise GraphError("AI singleton call trace is missing or out of order")
    callers = sorted({row[0] for row in initial})
    companion_callers = [c for c in callers if c.startswith(
        "Judgment_SP_E2_P.TheWorld:PersistentLevel.GearAI_")]
    if len(companion_callers) < 3:
        raise GraphError("missing three original companion AI callers")
    spawners = re.findall(r"\[JUDGAI\] smart-spawner instance=(\S+) class=(\S+) cdo=(\d+)", text)
    if len(spawners) != 1 or spawners[0][1:] != ("GearGame.SmartSpawner", "0"):
        raise GraphError("missing live original SmartSpawner instance")
    if re.search(r"\[JUDGBIND\]\[STUB\] cls=(?:AISystem#\d+ func=GetInstance|SmartSpawner#\d+ func=SetInstance)(?:\s|$)", text):
        raise GraphError("prototype accessor still used the generic native fallback")
    if "Function GearGame.GearAI_COGGear:Possess:0046" in text:
        raise GraphError("companion possession still reports the null AI system")
    return {"status": "experimental-accessor-layer-only", "singleton": instance,
            "rooted": True, "is_class_default_object": False,
            "companion_callers": companion_callers, "reported_calls": len(calls),
            "smart_spawner": spawners[0][0],
            "native_initialization_pending": partial[0][3].split(","),
            "native_tick_implemented": False, "map_cleanup_verified": False,
            "encounter_verified": False}


def audit_director_initialization(text, smart_spawner=None):
    """Verify the original four-state initialization, without claiming activation."""
    if "-JUDGAIDIRECTORINIT" not in text:
        if "[JUDGDIRECTOR]" in text:
            raise GraphError("director initialization ran without its explicit flag")
        return None
    partial = re.findall(
        r"\[JUDGDIRECTOR\]\[PARTIAL\] director=(\S+) class=(\S+) spawner=(\S+) "
        r"fsm=(\S+) cdo=(\d+) auto-setup=(\d+) running=(\d+) native-pending=(\S+)", text)
    if len(partial) != 1:
        raise GraphError("missing or repeated director initialization disclosure")
    director, cls, spawner, fsm, cdo, auto_setup, running, pending = partial[0]
    if (cls, cdo, auto_setup, running, pending) != (
            "GearGame.AIDirector", "0", "1", "0",
            "DirectorTick,FSMTick,PacingCallbacks,ETQQueries"):
        raise GraphError("director initialization changed activation or pending-work contract")
    if not director.startswith("Transient.AIDirector_") or not spawner.startswith("Transient.SmartSpawner_"):
        raise GraphError("missing live transient director/spawner objects")
    if smart_spawner is not None and spawner != smart_spawner:
        raise GraphError("director parent differs from the live singleton spawner")
    summaries = re.findall(
        r"\[JUDGDIRECTOR\] fsm-init fsm=(\S+) class=(\S+) outer=(\S+) owner=(\S+) "
        r"script-owner=(\S+) states=(\d+) transitions=(\d+) delegates=(\d+) "
        r"status=(\d+) script-init=(\d+) activate=(\d+)", text)
    if summaries != [(fsm, "GearGame.FSM_AIDirector", director, director, director,
                      "4", "4", "12", "1", "1", "0")]:
        raise GraphError("director machine lacks original owner, bindings or initialized status")
    if not fsm.startswith(director + ":FSM_AIDirector_"):
        raise GraphError("director machine path does not match its actual outer")
    states = re.findall(
        r"\[JUDGDIRECTOR\] state fsm=(\S+) index=(\d+) name=(\S+) enter=(\S+) "
        r"enter-bound=(\d+) leave=(\S+) leave-bound=(\d+) transitions=(\d+)", text)
    transitions = re.findall(
        r"\[JUDGDIRECTOR\] transition fsm=(\S+) state=(\d+) index=(\d+) "
        r"condition=(\S+) bound=(\d+) target=(\S+) target-index=(-?\d+)", text)
    names = ("BuildUp", "PeakSustain", "PeakFade", "Relax")
    expected_states = [(fsm, str(i), name, name + "OnEnter", "1", name + "OnLeave", "1", "1")
                       for i, name in enumerate(names)]
    expected_transitions = [(fsm, str(i), "0", name + "Condition", "1",
                             names[(i + 1) % 4], str((i + 1) % 4))
                            for i, name in enumerate(names)]
    if states != expected_states or transitions != expected_transitions:
        raise GraphError("director state names, delegate bindings or transition indices differ from original defaults")
    if re.search(r"\[JUDGBIND\]\[STUB\] cls=AIDirector#\d+ func=Init(?:\s|$)", text):
        raise GraphError("director initializer still used the generic native fallback")
    return {"status": "experimental-director-initialization-only",
            "director": director, "smart_spawner": spawner, "fsm": fsm,
            "states": list(names), "transition_indices": [1, 2, 3, 0],
            "bound_delegates": 12, "original_script_owner_verified": True,
            "initialized_status": 1, "auto_level_marker_setup_enabled": True,
            "running": False, "activated": False,
            "pacing_callbacks_implemented": False,
            "native_implementation_pending": pending.split(","),
            "encounter_verified": False}


def audit_companion_squads(text, player_controller):
    enabled = "-JUDGAISQUADTRACE" in text
    if not enabled:
        if "[JUDGAISQUAD]" in text:
            raise GraphError("squad probe ran without its explicit flag")
        return None
    rows = re.findall(
        r"\[JUDGAISQUAD\] controller=(\S+) pawn=(\S+) squad-readable=(\d+) squad=(\S+) "
        r"pri-readable=(\d+) pri=(\S+) team-readable=(\d+) team=(\S+) "
        r"leader-readable=(\d+) leader=(\S+) members-readable=(\d+) members=(-?\d+) self-index=(-?\d+)", text)
    summary = re.findall(r"\[JUDGAISQUAD\] snapshot controllers=(\d+) scanned=(\d+) limit=(\d+) game-time=([0-9.]+)", text)
    if len(rows) != 3 or len(summary) != 1 or summary[0][:3] != ("3", "4", "0") or float(summary[0][3]) < 30:
        raise GraphError("missing complete companion membership snapshot after startup")
    if len({r[0] for r in rows}) != 3 or len({r[1] for r in rows}) != 3 or len({r[5] for r in rows}) != 3:
        raise GraphError("companion controller/pawn/PRI identities are not distinct")
    for row in rows:
        if not row[0].startswith("Judgment_SP_E2_P.TheWorld:PersistentLevel.GearAI_"):
            raise GraphError("squad controller is outside the original mission")
        if any(row[i] != "1" for i in (2, 4, 6, 8, 10)) or any(row[i] == "None" for i in (1, 3, 5, 7, 9)):
            raise GraphError("unreadable or absent companion membership dependency")
        if row[9] != player_controller or row[11] != "4":
            raise GraphError("squad leader/size differs from the original startup fixture")
    if len({r[3] for r in rows}) != 1 or len({r[7] for r in rows}) != 1:
        raise GraphError("companions do not share one squad and team")
    if sorted(int(r[12]) for r in rows) != [1, 2, 3]:
        raise GraphError("companions are absent from distinct squad member entries")
    return {"squad": rows[0][3], "team": rows[0][7], "leader": player_controller,
            "array_entries": 4, "verified_ai_members": [
                {"controller": r[0], "pawn": r[1], "pri": r[5], "member_index": int(r[12])}
                for r in sorted(rows)], "snapshot_game_seconds": float(summary[0][3]),
            "player_array_entry_verified": False, "movement_or_encounter_verified": False}


def audit_log(text, graphs):
    if "-JUDGSEQUENCETRACE" not in text or "[JUDGSEQ] trace-limit" in text:
        raise GraphError("missing or truncated campaign execution trace")
    if "Critical: appError called:" in text:
        raise GraphError("runtime fatal error")
    native_loads = re.findall(r"\[JUDGPRELOAD\] leave exp=\d+ obj=\S+ consumed=(\d+) size=(\d+)", text)
    if not native_loads or any(a != b for a, b in native_loads):
        raise GraphError("missing or mismatched native loads")
    nodes = {package: {node["path"]: node for node in graph.values()} for package, graph in graphs.items()}

    def find_node(runtime_path):
        package, _, path = runtime_path.partition(".")
        if package == "Judgment_SP_E2_P":
            package = "SP_E2_P"
        path = path.replace(":", ".")
        if package not in nodes or path not in nodes[package]:
            raise GraphError(f"runtime trace outside audited graphs: {runtime_path}")
        return package, path, nodes[package][path]

    observed, counts = {}, Counter()
    op_pattern = re.compile(r"\[JUDGSEQ\] (activate|complete) op=(\S+) class=(\S+) count=(\d+) active=(\d+) latent=(\d+) inputs=(\d+) outputs=(\d+)")
    for match in op_pattern.finditer(text):
        phase, path, cls, _, _, _, inputs, outputs = match.groups()
        package, relative, node = find_node(path)
        if node["class"] != cls:
            raise GraphError("runtime operation class differs from source graph")
        for field, count in [("InputLinks", int(inputs)), ("OutputLinks", int(outputs))]:
            stored = node["properties"].get(field)
            if stored is not None and len(stored["value"]) != count:
                raise GraphError("runtime connector count differs from source graph")
        observed.setdefault((package, phase, relative), match.start())
        counts[phase] += 1
    if not counts["activate"] or not counts["complete"]:
        raise GraphError("campaign trace contains no executed operations")
    output_count = 0
    for match in re.finditer(r'\[JUDGSEQ\] output op=(\S+) index=(\d+) desc="([^"]*)" targets=(\d+)', text):
        _, _, node = find_node(match[1])
        outputs = node["properties"].get("OutputLinks", {}).get("value", [])
        index = int(match[2])
        if index >= len(outputs):
            raise GraphError("runtime output outside source connectors")
        output = outputs[index]
        if output.get("LinkDesc", {}).get("value", "") != match[3] or len(output.get("Links", {}).get("value", [])) != int(match[4]):
            raise GraphError("runtime output differs from original graph")
        output_count += 1
    for match in re.finditer(r'\[JUDGSEQ\] input op=(\S+) index=(\d+) desc="([^"]*)"', text):
        _, _, node = find_node(match[1])
        inputs = node["properties"].get("InputLinks", {}).get("value", [])
        index = int(match[2])
        if index >= len(inputs) or inputs[index].get("LinkDesc", {}).get("value", "") != match[3]:
            raise GraphError("runtime input differs from original graph")
    previous = -1
    for phase, path in REQUIRED:
        position = observed.get(("SP_E2_P", phase, path))
        if position is None or position <= previous:
            raise GraphError(f"startup milestone missing or out of order: {phase} {path}")
        previous = position
    for name in ("SeqAct_AIFactory_0", "SeqAct_AIFactory_1", "SeqAct_AIFactory_6", "SeqAct_AIFactory_7"):
        path = BASE + "Spawn_COG_Squad." + name
        if ("SP_E2_P", "activate", path) not in observed:
            raise GraphError("missing original squad factory activation")
        if not re.search(r'\[JUDGSEQ\] output op=Judgment_SP_E2_P\.TheWorld:PersistentLevel\.Main_Sequence\.Spawn_COG_Squad\.' + name + r' index=0 desc="All Spawned" targets=1', text):
            raise GraphError("squad factory did not emit All Spawned")
    objective_path = BASE + "MISSION_OBJECTIVES.SeqAct_ManageObjectives_1"
    objective_name = nodes["SP_E2_P"][objective_path]["properties"]["ObjectiveName"]["value"]
    state = re.search(r"\[JUDGSEQ\] objective-state op=\S+\.SeqAct_ManageObjectives_1 manager=(\S+) readable=1 count=1\r?\n[^\n]*\[JUDGSEQ\] objective-entry index=0 name=(\S+) completed=0 failed=0", text)
    if not state or state[2] != objective_name:
        raise GraphError("first objective is absent, unreadable or does not match source")
    ticks = re.findall(r"\[([0-9.]+)\].*\[JUDGPROTO\] tick-end serial=\d+ game-time=([0-9.]+) levels=(\d+)", text)
    if not ticks or float(ticks[-1][1]) < 30 or int(ticks[-1][2]) != 7:
        raise GraphError("world did not continue ticking with seven levels")
    stubs = {}
    for match in re.finditer(r"\[JUDGBIND\]\[STUB\] cls=([^# ]+)#\d+ func=(\S+)[^\r\n]* count=(\d+)", text):
        key = match[1] + "." + match[2]
        stubs[key] = max(stubs.get(key, 0), int(match[3]))
    warnings = Counter(re.findall(r"ScriptWarning:[^\n]*\n[^\n]*\n\s*Function ([^\r\n]+)", text))
    ai_layer = audit_ai_accessor_layer(text)
    return {
        "milestone": "original-startup-and-first-active-objective",
        "exact_native_loads": len(native_loads), "operation_reports": dict(counts),
        "validated_output_reports": output_count, "objective_manager": state[1],
        "active_objective": objective_name, "last_tick_wall_seconds": float(ticks[-1][0]),
        "last_tick_game_seconds": float(ticks[-1][1]), "loaded_levels": int(ticks[-1][2]),
        "native_fallbacks": dict(sorted(stubs.items())),
        "fallback_counts_are_reported_thresholds": True,
        "script_warnings_by_function": dict(warnings.most_common()),
        "experimental_ai_accessor_layer": ai_layer,
        "experimental_director_initialization": audit_director_initialization(
            text, ai_layer["smart_spawner"] if ai_layer else None),
        "companion_squad_membership": audit_companion_squads(text, state[1].rsplit(".", 1)[0]),
        "checkpoint_save_restore_verified": False, "encounter_verified": False,
    }


def validate(log_path, fixtures=FIXTURES):
    reports, graphs = {}, {}
    for package, artifact in ARTIFACTS.items():
        source = fixtures / (package + ".xxx.unc")
        converted = fixtures / (package + "." + artifact + ".le.xxx")
        staged_name = "Judgment_SP_E2_P" if package == "SP_E2_P" else package
        staged = Path(r"C:\Games\Gears 3 Files\Judgment Port Workspace\GearGame\Content\Maps") / (staged_name + ".gear")
        if staged.read_bytes() != converted.read_bytes():
            raise GraphError("staged mission package differs from audited artifact")
        report = compare(source.read_bytes(), converted.read_bytes(),
                         json.loads((fixtures / (package + ".xxx.json")).read_text(encoding="utf-8")),
                         json.loads((fixtures / (package + "." + artifact + ".manifest.json")).read_text(encoding="utf-8")))
        graphs[package] = report.pop("graph")
        reports[package] = report
    raw = Path(log_path).read_bytes()
    runtime = audit_log(raw.decode("utf-8", errors="replace"), graphs)
    return {"graphs": reports, "runtime": runtime, "log": str(log_path),
            "log_sha256": hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise GraphError("refusing to overwrite retained evidence")
    report = validate(args.log)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.quiet:
        print("PASS: original campaign startup and first active objective; " + str(args.output))
    else:
        print(json.dumps(report["runtime"], indent=2))


if __name__ == "__main__":
    main()
