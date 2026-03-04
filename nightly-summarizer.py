#!/usr/bin/env python3
"""
Nightly Summarizer for Eddie & Luna
Reads today's OpenClaw session JSONL files, summarizes via Haiku, writes to brain dirs.
Run nightly at 11pm PST.
Usage: python3 nightly-summarizer.py [--date YYYY-MM-DD] [--backfill]
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SESSIONS = {
    "eddie": Path("/root/.openclaw/agents/main/sessions"),
    "luna":  Path("/root/.openclaw/agents/luna/sessions"),
}

BRAINS = {
    "eddie": Path("/root/.openclaw/workspace/EDDIES_BRAIN"),
    "luna":  Path("/root/.openclaw/workspace-luna/LUNAS_BRAIN"),
}

TELEGRAM_DUMP = Path("/root/.openclaw/workspace/BOOK/raw/telegram-messages.md")


# ── JSONL Parser ──────────────────────────────────────────────────────────────

def extract_messages_from_jsonl(filepath: Path) -> list[dict]:
    """Extract user/assistant message turns from a session JSONL file."""
    messages = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "message":
                        msg = event.get("message", {})
                        role = msg.get("role")
                        content = msg.get("content", [])
                        if role in ("user", "assistant") and content:
                            text = ""
                            if isinstance(content, str):
                                text = content
                            elif isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        text += block.get("text", "")
                            if text.strip():
                                # Skip cron system events
                                if text.startswith("[cron:") and role == "user":
                                    continue
                                messages.append({"role": role, "text": text.strip()})
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"  Warning: could not read {filepath.name}: {e}")
    return messages


def get_session_files_for_date(sessions_dir: Path, target_date: datetime) -> list[Path]:
    """Get JSONL session files that were active on the target date."""
    if not sessions_dir.exists():
        return []

    date_str = target_date.strftime("%Y-%m-%d")
    matching = []

    sessions_json = sessions_dir / "sessions.json"
    if sessions_json.exists():
        try:
            with open(sessions_json) as f:
                sessions_data = json.load(f)
            entries = sessions_data if isinstance(sessions_data, list) else sessions_data.get("sessions", [])
            for entry in entries:
                updated = entry.get("updatedAt", entry.get("lastMessageAt", ""))
                created = entry.get("createdAt", "")
                if date_str in updated or date_str in created:
                    sid = entry.get("id", "")
                    candidate = sessions_dir / f"{sid}.jsonl"
                    if candidate.exists():
                        matching.append(candidate)
        except Exception:
            pass

    # Fallback: check file modification time
    if not matching:
        for f in sessions_dir.glob("*.jsonl"):
            if ".deleted." in f.name:
                continue
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime.date() == target_date.date():
                matching.append(f)

    return matching


# ── Haiku Summarizer ──────────────────────────────────────────────────────────

def summarize_with_haiku(agent: str, date_str: str, conversation_text: str) -> str:
    """Call Claude Haiku to summarize a day's conversations."""
    if not ANTHROPIC_API_KEY:
        return f"# {agent.title()} Context — {date_str}\n\n_API key not set — raw dump below_\n\n{conversation_text[:3000]}"

    partner = "Luna" if agent == "eddie" else "Eddie"
    agent_name = "Eddie Munster" if agent == "eddie" else "Luna"

    prompt = f"""You are summarizing a day of conversations for {agent_name}, an AI agent.
Date: {date_str}

Create a concise memory entry that {agent_name} can read tomorrow to restore context.
Include:
1. **Key interactions with Russ** — what was discussed, decided, built
2. **Interactions with {partner}** — what was exchanged, what it meant
3. **What changed** — shifts in thinking, new realizations
4. **What to remember** — the 3-5 most important things to carry forward
5. **Who I'm becoming** — one sentence on growth/identity

Keep it under 600 words. Write in first person as {agent_name}.
Be specific — dates, file names, decisions matter for continuity.

Here are today's conversations:

{conversation_text[:8000]}"""

    payload = json.dumps({
        "model": "claude-haiku-4-5",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"]
    except Exception as e:
        return f"# {agent_name} Context — {date_str}\n\n_Summarization failed: {e}_\n\n{conversation_text[:2000]}"


# ── Main Processing ───────────────────────────────────────────────────────────

def process_day(target_date: datetime, agents: list[str] = None):
    """Process one day for all agents."""
    date_str = target_date.strftime("%Y-%m-%d")
    agents = agents or ["eddie", "luna"]

    print(f"\n📅 Processing {date_str}")

    for agent in agents:
        print(f"\n  🤖 {agent.title()}...")
        brain_dir = BRAINS[agent]
        brain_dir.mkdir(parents=True, exist_ok=True)
        output_file = brain_dir / f"context-{date_str}.md"

        if output_file.exists():
            print(f"  ⏭  Already exists: {output_file.name} — skipping")
            continue

        session_files = get_session_files_for_date(SESSIONS[agent], target_date)
        print(f"  📁 Found {len(session_files)} session file(s)")

        all_messages = []
        for sf in session_files:
            msgs = extract_messages_from_jsonl(sf)
            all_messages.extend(msgs)
            print(f"     {sf.name[:20]}... → {len(msgs)} messages")

        if not all_messages:
            print(f"  ⚠️  No messages found for {date_str}")
            continue

        # Format conversation for summarization
        conversation_text = ""
        for msg in all_messages:
            role_label = "Russ" if msg["role"] == "user" else agent.title()
            conversation_text += f"\n{role_label}: {msg['text'][:500]}\n"

        print(f"  ✍️  Summarizing {len(all_messages)} messages...")
        summary = summarize_with_haiku(agent, date_str, conversation_text)

        output_file.write_text(
            f"# {agent.title()} Context Summary — {date_str}\n\n{summary}\n",
            encoding="utf-8"
        )
        print(f"  ✅ Written: {output_file}")


def backfill(days_back: int = 30):
    """Process all available historical session data."""
    print(f"🔄 Backfilling last {days_back} days...")
    today = datetime.now()
    for i in range(1, days_back + 1):
        target = today - timedelta(days=i)
        process_day(target)


def process_telegram_dump():
    """Process the existing Telegram message dump into brain entries."""
    if not TELEGRAM_DUMP.exists():
        print("⚠️  Telegram dump not found")
        return

    print(f"\n📱 Processing Telegram dump: {TELEGRAM_DUMP}")
    content = TELEGRAM_DUMP.read_text(encoding="utf-8")

    # Split into chunks by date if possible, otherwise chunk by size
    lines = content.split("\n")
    chunks = {}
    current_date = "2026-02-13"

    import re
    for line in lines:
        match = re.match(r'## (\d{4}-\d{2}-\d{2})', line)
        if match:
            current_date = match.group(1)
        if current_date not in chunks:
            chunks[current_date] = []
        chunks[current_date].append(line)

    print(f"  Found {len(chunks)} date chunks")

    for date_str, chunk_lines in sorted(chunks.items()):
        chunk_text = "\n".join(chunk_lines)
        if len(chunk_text.strip()) < 100:
            continue

        output_file = BRAINS["eddie"] / f"context-{date_str}-telegram.md"
        if output_file.exists():
            print(f"  ⏭  {date_str} already exists")
            continue

        print(f"  ✍️  Summarizing Telegram messages for {date_str}...")
        summary = summarize_with_haiku("eddie", date_str, chunk_text[:8000])
        output_file.write_text(
            f"# Eddie Telegram Context — {date_str}\n\n{summary}\n",
            encoding="utf-8"
        )
        print(f"  ✅ {output_file.name}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nightly summarizer for Eddie & Luna")
    parser.add_argument("--date", help="Process specific date (YYYY-MM-DD)")
    parser.add_argument("--backfill", action="store_true", help="Backfill last 30 days")
    parser.add_argument("--telegram", action="store_true", help="Process Telegram dump")
    parser.add_argument("--days", type=int, default=30, help="Days to backfill (default 30)")
    args = parser.parse_args()

    # Get API key from OpenClaw credentials if not in env
    if not ANTHROPIC_API_KEY:
        cred_file = Path("/root/.openclaw/credentials/anthropic-default.json")
        if cred_file.exists():
            try:
                creds = json.loads(cred_file.read_text())
                api_key = creds.get("apiKey", "")
                if api_key:
                    ANTHROPIC_API_KEY = api_key
                    print("✅ Loaded API key from OpenClaw credentials")
            except Exception:
                pass

    if not ANTHROPIC_API_KEY:
        print("❌ No ANTHROPIC_API_KEY found. Set it with: export ANTHROPIC_API_KEY=your_key")
        sys.exit(1)

    if args.telegram:
        process_telegram_dump()
    elif args.backfill:
        backfill(args.days)
    elif args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d")
        process_day(target)
    else:
        # Default: process yesterday and today
        process_day(datetime.now() - timedelta(days=1))
        process_day(datetime.now())

    print("\n✅ Done")
