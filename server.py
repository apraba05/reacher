#!/usr/bin/env python3
"""Offline Creator CRM agent demo: SQLite + MCP-style tools + streamed traces."""
import json
import os
import re
import sqlite3
import time
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent
DB = ROOT / "creators.db"
PORT = int(os.environ.get("PORT", "8000"))

CREATORS = [
    ("Maya Chen", "active", 1, 3, 84200), ("Jordan Blake", "active", 3, 1, 71900),
    ("Priya Shah", "active", 2, 4, 63800), ("Leo Martinez", "waiting", 18, 5, 42100),
    ("Avery Brooks", "active", 5, 2, 39600), ("Nia Okafor", "stalled", 27, 6, 31400),
    ("Theo Kim", "active", 4, 2, 28700), ("Sofia Rossi", "waiting", 12, 4, 24600),
    ("Eli Morgan", "stalled", 35, 3, 21800), ("Amara Wilson", "active", 6, 1, 19400),
    ("Finn O'Brien", "waiting", 16, 5, 17100), ("Zara Patel", "stalled", 42, 7, 14300),
    ("Noah Williams", "active", 8, 2, 11900), ("Lina Park", "waiting", 21, 4, 8700),
    ("Mateo Silva", "stalled", 51, 6, 5200),
]

def init_db():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS creators (
      name TEXT PRIMARY KEY, status TEXT, last_contact TEXT,
      samples_sent INTEGER, gmv_last_30d INTEGER)""")
    if con.execute("SELECT COUNT(*) FROM creators").fetchone()[0] == 0:
        today = date.today()
        con.executemany("INSERT INTO creators VALUES (?,?,?,?,?)", [
            (name, status, str(today - timedelta(days=days)), samples, gmv)
            for name, status, days, samples, gmv in CREATORS
        ])
    con.commit(); con.close()

def rows(sql, args=()):
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    out = [dict(r) for r in con.execute(sql, args).fetchall()]
    con.close(); return out

def get_creator(name):
    found = rows("SELECT * FROM creators WHERE lower(name)=lower(?)", (name,))
    return found[0] if found else None

def list_top_by_gmv(n):
    return rows("SELECT * FROM creators ORDER BY gmv_last_30d DESC LIMIT ?", (max(1, min(n, 15)),))

def list_stalled_creators(days):
    cutoff = str(date.today() - timedelta(days=days))
    return rows("SELECT * FROM creators WHERE last_contact <= ? ORDER BY last_contact", (cutoff,))

def plan(question):
    q = question.lower()
    n_match = re.search(r"(?:top|best)\s+(\d+)", q)
    days_match = re.search(r"(\d+)\s*days?", q)
    name = next((x[0] for x in CREATORS if x[0].lower() in q), None)
    calls = []
    if name or any(x in q for x in ("tell me about", "look up", "profile")):
        calls.append(("get_creator", {"name": name or "Maya Chen"}))
    if any(x in q for x in ("gmv", "top", "best", "revenue", "perform")):
        calls.append(("list_top_by_gmv", {"n": int(n_match.group(1)) if n_match else 5}))
    if any(x in q for x in ("stall", "follow up", "overdue", "contact", "sample")):
        calls.append(("list_stalled_creators", {"days": int(days_match.group(1)) if days_match else 14}))
    return calls or [("list_top_by_gmv", {"n": 5})]

def call_tool(name, args):
    return {"get_creator": lambda: get_creator(args["name"]),
            "list_top_by_gmv": lambda: list_top_by_gmv(args["n"]),
            "list_stalled_creators": lambda: list_stalled_creators(args["days"])}[name]()

def money(v): return f"${v:,.0f}"

def answer(question, results):
    parts = []
    for tool, args, data in results:
        if tool == "get_creator":
            if data: parts.append(f"{data['name']} is {data['status']} with {money(data['gmv_last_30d'])} GMV in the last 30 days, {data['samples_sent']} samples sent, and last contact on {data['last_contact']}.")
        elif tool == "list_top_by_gmv":
            names = ", ".join(f"{r['name']} ({money(r['gmv_last_30d'])})" for r in data)
            parts.append(f"The GMV leaders are {names}.")
        elif tool == "list_stalled_creators":
            names = ", ".join(f"{r['name']} ({r['last_contact']}, {r['samples_sent']} samples)" for r in data)
            parts.append(f"Creators needing follow-up: {names}." if data else "No creators cross that follow-up threshold.")
    if len(results) > 1:
        top = results[0][2] if results[0][0] == "list_top_by_gmv" else []
        stalled = results[-1][2] if results[-1][0] == "list_stalled_creators" else []
        overlap = [r["name"] for r in top if any(s["name"] == r["name"] for s in stalled)]
        if overlap: parts.append("Priority action: re-engage " + ", ".join(overlap) + "—they combine meaningful GMV with stalled outreach.")
    return " ".join(parts)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send_json(self, obj, status=200):
        raw = json.dumps(obj).encode(); self.send_response(status)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw)))
        self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            raw = (ROOT / "index.html").read_bytes(); self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(raw)))
            self.end_headers(); self.wfile.write(raw); return
        if parsed.path == "/api/creators": return self.send_json(rows("SELECT * FROM creators ORDER BY gmv_last_30d DESC"))
        if parsed.path == "/api/stats":
            data = rows("SELECT COUNT(*) creators, SUM(gmv_last_30d) gmv, SUM(samples_sent) samples FROM creators")[0]
            data["stalled"] = len(list_stalled_creators(14)); return self.send_json(data)
        if parsed.path == "/api/ask": return self.stream_ask(parse_qs(parsed.query).get("q", [""])[0], parse_qs(parsed.query).get("fail", ["0"])[0] == "1")
        self.send_error(404)
    def stream_ask(self, question, fail):
        self.send_response(200); self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache"); self.send_header("Connection", "close"); self.end_headers()
        def emit(kind, data, pause=.35):
            self.wfile.write(f"event: {kind}\ndata: {json.dumps(data)}\n\n".encode()); self.wfile.flush(); time.sleep(pause)
        started = time.perf_counter(); emit("stage", {"stage":"thinking", "message":"Agent is parsing intent…"})
        calls = plan(question); emit("plan", {"tools":[x[0] for x in calls], "message":f"Plan: call {len(calls)} CRM tool{'s' if len(calls)>1 else ''}"})
        done = []
        for i, (tool, args) in enumerate(calls):
            emit("tool_start", {"tool":tool,"args":args,"id":i})
            if fail and i == 0:
                emit("tool_error", {"tool":tool,"message":"Bedrock gateway timed out after 800 ms","id":i}, .5)
                emit("fallback", {"message":"Circuit open → switching to local rule-based planner","id":i}, .55)
            t = time.perf_counter(); data = call_tool(tool, args); latency = int((time.perf_counter()-t)*1000)+7+i*4
            done.append((tool,args,data)); emit("tool_result", {"tool":tool,"rows":len(data) if isinstance(data,list) else (1 if data else 0),"data":data,"latency":latency,"id":i})
        emit("stage", {"stage":"composing","message":"Agent is grounding its answer in tool results…"})
        emit("answer", {"answer":answer(question,done),"latency":int((time.perf_counter()-started)*1000),"calls":len(done)}, 0)

if __name__ == "__main__":
    init_db(); print(f"Reacher demo running at http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
