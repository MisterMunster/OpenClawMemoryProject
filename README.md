# OpenClaw Memory Project

Persistent memory system for OpenClaw AI agents (Eddie & Luna).

## Components
- `memory_server.py` — FastAPI service serving boot context at /boot?agent=eddie
- `nightly-summarizer.py` — Processes session logs into brain entries nightly
- `setup-longterm.py` — One-time installer for long-term memory system
- `memory-server.service` — Systemd service definition

## Endpoints
- GET /boot?agent=eddie — Full boot context for Eddie
- GET /boot?agent=luna — Full boot context for Luna
- GET /status — Health check
- POST /memory — Write a memory entry

## Usage
Store something permanently: tell agent "store this in long term memory: [fact]"
