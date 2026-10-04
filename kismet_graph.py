"""Read a running level's Kismet out of a loader log: what each trigger starts and what enables an event.

python kismet_graph.py <log> events                 every sequence event with its actor's position and counts
python kismet_graph.py <log> who <text> [depth]     ops whose linked variables name an actor; what leads to them
python kismet_graph.py <log> enables <text>         what enables (toggles) an event; remote events followed by name

The log must contain these console dumps (send them through remote.ps1 while the
level is loaded; `kismet_dump.ps1` does it):
    getall SeqVar_Object ObjValue          getall SequenceOp VariableLinks
    getall SequenceOp OutputLinks          getall SequenceOp EventLinks
    getall SequenceOp ActivateCount        getall SequenceObject ObjComment
    getall SequenceEvent Originator        getall SequenceEvent TriggerCount
    getall SequenceEvent MaxTriggerCount   getall SequenceEvent bEnabled
    getall SeqEvent_RemoteEvent EventName  getall SeqAct_ActivateRemoteEvent EventName
    getall Actor Location                  (or the trigger classes of interest)
Later dumps in the same log replace earlier values, so counts are the latest.

Why: the port is tested by teleporting, and a level's scripts assume an order.
Found with it: the dark office floor of SP_E2 was a Matinee ("Flickering light
sequence") waiting for TriggerVolume_1, and the co-op door waits for the remote
event FormersAllDead. A trigger volume's actor Location is its pivot; use
`getall BrushComponent Bounds` for where to stand. Read-only.
"""
import re
import sys
from collections import defaultdict

HEAD = re.compile(r"\] Log: \d+\) (\w+) (\S+)\.(\w+) =(.*)$")
CONT = re.compile(r"^(?:\[\d+\.\d+\] Log: )?\t(.*)$")


def short(name):
    return name.replace("TheWorld:PersistentLevel.Main_Sequence.", "").replace("TheWorld:PersistentLevel.", "")


def refs(text, pattern=r"'([^']+)'"):
    return [short(x) for x in re.findall(pattern, text)]


class Graph:
    def __init__(self, path):
        self.props = defaultdict(dict)      # property -> object -> text
        self.cls = {}
        current = None
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.rstrip("\n")
            head = HEAD.search(line)
            if head:
                cls, obj, prop, value = head.groups()
                obj = short(obj)
                self.cls[obj] = cls
                self.props[prop][obj] = short(value.strip())
                current = (prop, obj)
                continue
            cont = CONT.match(line)
            if cont and current:
                self.props[current[0]][current[1]] += "\n" + short(cont.group(1).strip())
            elif "] " in line:
                current = None
        p = self.props
        self.var_value = {v: (refs(t) or [t])[0] for v, t in p["ObjValue"].items()}
        self.op_vars = {op: [v for group in re.findall(r"LinkedVariables=\(([^)]*)\)", t) for v in refs(group)]
                        for op, t in p["VariableLinks"].items()}
        self.succ, self.pred = defaultdict(list), defaultdict(list)
        for op, t in p["OutputLinks"].items():
            for target in refs(t, r"LinkedOp=\w+'([^']+)'"):
                self.succ[op].append(target)
                self.pred[target].append(op)
        self.event_links = {op: [e for group in re.findall(r"LinkedEvents=\(([^)]*)\)", t) for e in refs(group)]
                            for op, t in p["EventLinks"].items()}
        self.location = {}
        for obj, t in p["Location"].items():
            m = re.search(r"X=(-?[\d.]+),Y=(-?[\d.]+),Z=(-?[\d.]+)", t)
            if m:
                self.location[obj] = tuple(round(float(g)) for g in m.groups())

    def count(self, op):
        return self.props["ActivateCount"].get(op, self.props["TriggerCount"].get(op, "?"))

    def label(self, op):
        comment = self.props["ObjComment"].get(op, "")
        name = self.props["EventName"].get(op, "")
        return f"{self.cls.get(op, '?')} {op} n={self.count(op)}" + (f" '{comment[:40]}'" if comment else "") + \
            (f" event={name}" if name else "")

    def upstream(self, op, depth, limit, seen):
        if op in seen or depth > limit:
            return
        seen.add(op)
        print("  " * depth + self.label(op))
        for p in self.pred.get(op, []):
            self.upstream(p, depth + 1, limit, seen)
        if self.cls.get(op) == "SeqEvent_RemoteEvent":
            name = self.props["EventName"].get(op)
            for other, other_name in self.props["EventName"].items():
                if other_name == name and self.cls.get(other) == "SeqAct_ActivateRemoteEvent":
                    self.upstream(other, depth + 1, limit, seen)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    g = Graph(sys.argv[1])
    mode = sys.argv[2]
    if mode == "events":
        rows = []
        for event, originator in g.props["Originator"].items():
            actor = (refs(originator) or ["None"])[0]
            feeds = ", ".join(f"{g.cls.get(s, '?').replace('SeqAct_', '')}:{g.props['ObjComment'].get(s, '')[:24]}"
                              for s in g.succ.get(event, [])[:4])
            rows.append(f"{event:46s} {actor.split('.')[-1]:28s} {str(g.location.get(actor)):22s} "
                        f"n={g.props['TriggerCount'].get(event)}/{g.props['MaxTriggerCount'].get(event)} "
                        f"en={g.props['bEnabled'].get(event)} -> {feeds}")
        print("\n".join(sorted(rows)))
    elif mode == "who":
        needle, limit = sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 4
        for op in sorted(g.op_vars):
            targets = [g.var_value.get(v, "?") for v in g.op_vars[op] if needle in g.var_value.get(v, "")]
            if targets:
                print("== targets " + ", ".join(t.split(".")[-1] for t in targets))
                g.upstream(op, 0, limit, set())
    elif mode == "enables":
        needle = sys.argv[3]
        for op, events in sorted(g.event_links.items()):
            if any(needle in e for e in events):
                print("== enables " + ", ".join(events))
                g.upstream(op, 0, 8, set())
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
