"""Install this skill and its optional local recorder using Python 3.9+, no dependencies."""

import argparse
import os
from pathlib import Path
import shutil
import sys


SKILL_NAME = "ambitious-prompt"
AGENTS = ("codex", "claude", "dsh", "opencode", "zcode", "workbuddy", "workbuddy-intl")
REPO_ROOT = Path(__file__).resolve().parents[1]


def target_roots(home, env):
    """Use documented roots, preserving an existing legacy Codex installation."""
    legacy_codex = home / ".codex" / "skills"
    codex = (
        Path(env["CODEX_HOME"]).expanduser() / "skills"
        if env.get("CODEX_HOME")
        else legacy_codex
        if (legacy_codex / SKILL_NAME).is_dir()
        else home / ".agents" / "skills"
    )
    return {
        "codex": codex,
        "claude": Path(env.get("CLAUDE_CONFIG_DIR") or home / ".claude").expanduser() / "skills",
        "dsh": Path(env.get("DSH_HOME") or home / ".dsh").expanduser() / "skills",
        "opencode": Path(
            env.get("OPENCODE_CONFIG_DIR")
            or Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "opencode"
        ).expanduser() / "skills",
        "zcode": home / ".zcode" / "skills",
        "workbuddy": home / ".workbuddy" / "skills",
        "workbuddy-intl": home / ".workbuddy-ai" / "skills",
    }


def payload(repo_root):
    """The skill lives at the repo root; LICENSE and NOTICE.md ship beside it."""
    skill = repo_root
    if not (skill / "SKILL.md").is_file():
        raise ValueError(f"Missing skill: {skill}")
    files = {
        p.relative_to(skill): p for p in skill.rglob("*")
        if p.is_file() and "__pycache__" not in p.relative_to(skill).parts
        and p.suffix not in (".pyc", ".pyo")
        and p.relative_to(skill) != Path("scripts") / "install.py"
    }
    for filename in ("LICENSE", "NOTICE.md"):
        source = repo_root / filename
        if not source.is_file():
            raise ValueError(f"Missing distribution file: {source}")
        files[Path(filename)] = source
    return files


def install(repo_root, roots, selected, dry_run=False):
    files = payload(repo_root)
    planned = []
    conflicts = []
    # Preflight every selected target before creating or writing anything.
    for agent in dict.fromkeys(selected):
        target = roots[agent].resolve() / SKILL_NAME
        for relative, source in files.items():
            destination = target / relative
            parent = destination.parent
            while parent != parent.parent:
                if parent.exists() and not parent.is_dir():
                    conflicts.append(str(parent))
                    break
                parent = parent.parent
            if destination.exists() or destination.is_symlink():
                if not destination.is_file() or destination.read_bytes() != source.read_bytes():
                    conflicts.append(str(destination))
        planned.append((agent, target))
    if conflicts:
        raise ValueError(
            "Existing content differs; no files were written. Back up and resolve these paths first:\n"
            + "\n".join(dict.fromkeys(conflicts))
        )
    for agent, target in planned:
        if not dry_run:
            for relative, source in files.items():
                destination = target / relative
                if not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
        print(f"{'PLAN' if dry_run else 'READY'} {agent}: {target}")
    return planned


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents", nargs="+", required=True, choices=(*AGENTS, "all"))
    parser.add_argument("--dry-run", action="store_true", help="Check targets without writing files")
    parser.add_argument("--home", type=Path, help="Use this home directory and ignore environment overrides")
    args = parser.parse_args()
    home = args.home.expanduser().resolve() if args.home else Path.home()
    env = {} if args.home else os.environ
    selected = AGENTS if "all" in args.agents else args.agents
    try:
        install(REPO_ROOT, target_roots(home, env), selected, args.dry_run)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
