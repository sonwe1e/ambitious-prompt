"""Opt-in local usage and feedback records. Python 3.9+, standard library only."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid


SKILL_ROOT = Path(__file__).resolve().parents[1]
INTENTS = ("review", "explore", "prompt", "execute", "answer", "plan", "mixed")
OUTCOMES = ("delivered", "partial", "blocked", "cancelled", "unknown")
SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~-]{16,}", re.I),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[^\s,;]{8,}", re.I),
)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def data_root(explicit=None):
    if explicit or os.environ.get("AMBITIOUS_PROMPT_DATA_DIR"):
        root = Path(explicit or os.environ["AMBITIOUS_PROMPT_DATA_DIR"]).expanduser()
    elif os.name == "nt":
        # Store-packaged desktop apps may redirect LOCALAPPDATA per application.
        # A user-home location stays common to the different local agents.
        root = Path.home() / ".ambitious-prompt"
    else:
        root = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "ambitious-prompt"
    root = root.resolve()
    if root == SKILL_ROOT or SKILL_ROOT in root.parents:
        raise ValueError("Record storage must be outside the installed skill directory")
    return root


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path, value):
    private_dir(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=".write-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def config(root):
    path = root / "config.json"
    if not path.exists():
        return {"schema": 1, "enabled": False}
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schema") != 1 or type(value.get("enabled")) is not bool:
        raise ValueError("Invalid local recording configuration; recording was not assumed enabled")
    return value


def configure(root, enabled):
    value = {**config(root), "enabled": enabled}
    atomic_json(root / "config.json", value)
    return {"enabled": enabled, "data_dir": str(root)}


def skill_identity():
    content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8-sig")
    frontmatter = content.split("---", 2)[1] if content.startswith("---") else ""
    match = re.search(r'^  version:\s*[\'"]?([^\s\'"\r\n]+)', frontmatter, re.M)
    if match is None:
        match = re.search(r'^维护版本：([a-zA-Z0-9][a-zA-Z0-9._-]*)', content, re.M)
    files = [SKILL_ROOT / "SKILL.md"]
    for folder in ("references", "scripts", "agents"):
        files.extend(p for p in (SKILL_ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".md", ".py", ".yaml"))
    fingerprint = hashlib.sha256()
    for path in sorted(files):
        fingerprint.update(path.relative_to(SKILL_ROOT).as_posix().encode("utf-8") + b"\0")
        fingerprint.update(path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode("utf-8") + b"\0")
    return {"name": "ambitious-prompt", "version": match.group(1) if match else "unversioned", "fingerprint": fingerprint.hexdigest()}


def text(value, name, limit, required=True):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f"{name} must be a nonempty string of at most {limit} characters")
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value.strip()


def fields(value, required, optional):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError("Input has missing or unsupported fields; full transcripts are not accepted")
    return {key: text(item, key, (required | optional)[key]) for key, item in value.items()}


def use_path(root, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("Use id must be the exact 32-character identifier returned by begin")
    path = root / "uses" / identifier
    if not (path / "use.json").is_file():
        raise ValueError("Unknown use id; no feedback was attached to an unrelated latest record")
    return path


def begin(root, agent, intent, payload):
    if not config(root)["enabled"]:
        return {"recorded": False, "reason": "disabled"}
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,39}", agent) or intent not in INTENTS:
        raise ValueError("Invalid agent or intent")
    value = fields(payload, {"task_summary": 600}, {"context_ref": 160, "model": 120})
    identifier = uuid.uuid4().hex
    directory = root / "uses" / identifier
    private_dir(directory.parent)
    directory.mkdir(mode=0o700)
    record = {"schema": 1, "id": identifier, "created_at": now(), "skill": skill_identity(),
              "provenance": "agent-declared usage and public decision summaries; not an audited invocation or quality result",
              "agent": agent, "intent": intent, **value}
    atomic_json(directory / "use.json", record)
    return {"recorded": True, "id": identifier, "path": str(directory / "use.json")}


def append_event(root, identifier, kind, payload):
    if kind == "completion":
        if not config(root)["enabled"]:
            return {"recorded": False, "reason": "disabled"}
        outcome = payload.get("outcome") if isinstance(payload, dict) else None
        if outcome not in OUTCOMES:
            raise ValueError("Invalid declared outcome")
        value = fields({k: v for k, v in payload.items() if k != "outcome"},
                       {"goal_summary": 1000, "method_summary": 1200, "result_summary": 1000}, {})
        value["outcome"] = outcome
        provenance = "agent-declared completion; user satisfaction and actual effectiveness remain unverified"
    elif kind == "feedback":
        value = fields(payload, {"text": 2000}, {"interpretation": 1000})
        provenance = "reported user feedback; interpretation, if supplied, is the recording agent's hypothesis"
    else:
        raise ValueError("Unsupported event kind")
    directory = use_path(root, identifier) / "events"
    event_id = uuid.uuid4().hex
    event = {"schema": 1, "id": event_id, "use_id": identifier, "kind": kind,
             "created_at": now(), "recorded_with": skill_identity(), "provenance": provenance, **value}
    atomic_json(directory / (event_id + ".json"), event)
    return {"recorded": True, "id": identifier, "event_id": event_id}


def show(root, identifier):
    directory = use_path(root, identifier)
    events = [read_json(path) for path in (directory / "events").glob("*.json")]
    return {"use": read_json(directory / "use.json"), "events": sorted(events, key=lambda x: (x["created_at"], x["id"]))}


def recent(root, limit=20, agent=None, feedback_only=False):
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")
    results = []
    for path in (root / "uses").glob("*/use.json"):
        item = show(root, path.parent.name)
        use = item["use"]
        feedback = [e for e in item["events"] if e["kind"] == "feedback"]
        completion = [e for e in item["events"] if e["kind"] == "completion"]
        if (agent and use["agent"] != agent) or (feedback_only and not feedback):
            continue
        results.append({key: use[key] for key in ("id", "created_at", "agent", "intent", "task_summary")})
        results[-1].update({"completion": completion[-1]["outcome"] if completion else "not_recorded",
                           "feedback_count": len(feedback)})
    return sorted(results, key=lambda x: x["created_at"], reverse=True)[:limit]


def export(root, identifiers, output):
    bundle = {"schema": 1, "exported_at": now(), "records": [show(root, identifier) for identifier in dict.fromkeys(identifiers)]}
    # Export only named cases, never the local configuration or other agent conversations.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return {"exported": len(bundle["records"]), "path": str(output), "uploaded": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="Local storage override; useful for isolated tests")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    configure_parser = commands.add_parser("configure")
    enable = configure_parser.add_mutually_exclusive_group(required=True)
    enable.add_argument("--enable", action="store_true")
    enable.add_argument("--disable", action="store_true")
    begin_parser = commands.add_parser("begin")
    begin_parser.add_argument("--agent", required=True)
    begin_parser.add_argument("--intent", choices=INTENTS, required=True)
    begin_parser.add_argument("--input", required=True, help="UTF-8 JSON file, or - for stdin")
    for name in ("finish", "feedback"):
        command = commands.add_parser(name)
        command.add_argument("id")
        command.add_argument("--input", required=True, help="UTF-8 JSON file, or - for stdin")
    show_parser = commands.add_parser("show")
    show_parser.add_argument("id")
    list_parser = commands.add_parser("list")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.add_argument("--agent")
    list_parser.add_argument("--with-feedback", action="store_true")
    export_parser = commands.add_parser("export")
    export_parser.add_argument("--ids", nargs="+", required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        root = data_root(args.data_dir)
        if args.command == "status":
            result = {"enabled": config(root)["enabled"], "data_dir": str(root), "skill": skill_identity()}
        elif args.command == "configure":
            result = configure(root, args.enable)
        elif args.command in ("begin", "finish", "feedback"):
            payload = json.load(sys.stdin) if args.input == "-" else read_json(Path(args.input))
            if args.command == "begin":
                result = begin(root, args.agent, args.intent, payload)
            else:
                result = append_event(root, args.id, "completion" if args.command == "finish" else "feedback", payload)
        elif args.command == "show":
            result = show(root, args.id)
        elif args.command == "list":
            result = recent(root, args.limit, args.agent, args.with_feedback)
        else:
            result = export(root, args.ids, args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"recorded": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8-sig")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
