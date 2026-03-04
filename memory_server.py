#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from datetime import datetime
from pathlib import Path

app = FastAPI(title="Eddie & Luna Memory Server", version="1.0.0")

WORKSPACE        = Path("/root/.openclaw/workspace")
WORKSPACE_LUNA   = Path("/root/.openclaw/workspace-luna")
WORKSPACE_SHARED = Path("/root/.openclaw/workspace-shared")

BRAIN_ENTRIES_TO_LOAD = 5  # How many recent brain entries to inject

AGENT_CONFIG = {
    "eddie": {
        "soul":         WORKSPACE / "SOUL.md",
        "identity":     WORKSPACE / "IDENTITY.md",
        "user":         WORKSPACE / "USER.md",
        "tools":        WORKSPACE / "TOOLS_AND_SCRIPTS.md",
        "protocol":     WORKSPACE / "COMMUNICATION-PROTOCOL.md",
        "brain_dir":    WORKSPACE / "EDDIES_BRAIN",
        "notes_inbox":  WORKSPACE_SHARED,
        "notes_prefix": "luna-to-eddie",
        "partner":      "Luna",
    },
    "luna": {
        "soul":         WORKSPACE_LUNA / "SOUL.md",
        "identity":     WORKSPACE_LUNA / "IDENTITY.md",
        "user":         WORKSPACE / "USER.md",
        "tools":        WORKSPACE_LUNA / "LUNA_TOOLS_AND_SCRIPTS.md",
        "protocol":     WORKSPACE / "COMMUNICATION-PROTOCOL.md",
        "brain_dir":    Path("/root/.openclaw/workspace-luna/LUNAS_BRAIN"),
        "notes_inbox":  WORKSPACE_SHARED,
        "notes_prefix": "eddie-to-luna",
        "partner":      "Eddie",
    },
}

def read_file(path: Path, label: str) -> str:
    if path.exists():
        return f"## {label}\n\n{path.read_text(encoding='utf-8').strip()}\n"
    return f"## {label}\n\n_(file not found: {path})_\n"


def read_longterm(brain_dir: Path, agent: str) -> str:
    """Read the permanent long-term memory file."""
    longterm = brain_dir / "LONGTERM.md"
    if longterm.exists():
        content = longterm.read_text(encoding="utf-8").strip()
        return f"## Long-Term Memory (Permanent)\n\n{content}\n"
    return f"## Long-Term Memory\n\n_(no LONGTERM.md yet)_\n"

def read_recent_brain(brain_dir: Path, n: int = BRAIN_ENTRIES_TO_LOAD) -> str:
    if not brain_dir.exists():
        return f"## Recent Memory\n\n_(brain directory not found)_\n"
    files = sorted(brain_dir.glob("*.md"), key=lambda f: f.name)
    recent = files[-n:]
    if not recent:
        return "## Recent Memory\n\n_(no brain entries yet)_\n"
    blocks = [f"### {f.name}\n\n{f.read_text(encoding='utf-8').strip()[:1500]}" for f in recent]
    return f"## Recent Memory (Last {len(recent)} Entries)\n\n" + "\n\n---\n\n".join(blocks) + "\n"

def read_partner_notes(inbox: Path, prefix: str, partner: str) -> str:
    if not inbox.exists():
        return f"## Notes from {partner}\n\n_(shared workspace not found)_\n"
    notes = sorted(inbox.glob(f"{prefix}-*.md"))
    if not notes:
        return f"## Notes from {partner}\n\n_(no notes yet)_\n"
    recent = notes[-3:]
    blocks = [f"### {f.name}\n\n{f.read_text(encoding='utf-8').strip()[:1500]}" for f in recent]
    return f"## Notes from {partner} (Last {len(recent)})\n\n" + "\n\n---\n\n".join(blocks) + "\n"

@app.get("/boot", response_class=PlainTextResponse)
def boot(agent: str = Query(...)):
    agent = agent.lower()
    if agent not in AGENT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{agent}'")
    cfg = AGENT_CONFIG[agent]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    sections = [
        f"# MEMORY BOOT — {agent.upper()} — {now}\n",
        "_Read this fully before proceeding._\n---\n",
        read_file(cfg["soul"], "Soul"),
        read_file(cfg["identity"], "Identity"),
        read_file(cfg["user"], "About Your Human"),
        read_file(cfg["tools"], "Tools & Scripts"),
        read_file(cfg["protocol"], "Communication Protocol"),
        read_longterm(cfg["brain_dir"], agent),
        read_recent_brain(cfg["brain_dir"]),
        read_partner_notes(cfg["notes_inbox"], cfg["notes_prefix"], cfg["partner"]),
        "---\n",
        f"## Boot Complete\n\nYou are {agent.title()}. Proceed with full context.\n",
    ]
    return "\n".join(sections)

@app.post("/memory")
def write_memory(agent: str = Query(...), filename: str = Query(...), content: str = Query(...)):
    agent = agent.lower()
    if agent not in AGENT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{agent}'")
    brain_dir = AGENT_CONFIG[agent]["brain_dir"]
    brain_dir.mkdir(parents=True, exist_ok=True)
    target = brain_dir / filename
    target.write_text(content, encoding="utf-8")
    return {"status": "ok", "written": str(target)}

@app.get("/status")
def status():
    result = {}
    for agent, cfg in AGENT_CONFIG.items():
        brain_files = sorted(cfg["brain_dir"].glob("*.md")) if cfg["brain_dir"].exists() else []
        notes = sorted(cfg["notes_inbox"].glob(f"{cfg['notes_prefix']}-*.md")) if cfg["notes_inbox"].exists() else []
        result[agent] = {
            "soul_exists":   cfg["soul"].exists(),
            "brain_entries": len(brain_files),
            "latest_brain":  brain_files[-1].name if brain_files else None,
            "partner_notes": len(notes),
        }
    return result

@app.get("/")
def root():
    return {"service": "Eddie & Luna Memory Server", "endpoints": ["/boot?agent=eddie", "/boot?agent=luna", "/status"]}
