from pathlib import Path
import html
import json
import os

from .models import now


def report_data(session, include_sensitive=False):
    data = session.to_dict()
    data["exported"] = now()
    data["include_sensitive"] = include_sensitive
    if not include_sensitive:
        data["scope"] = {**data["scope"], "interface": "[omitted]", "bssid": "[omitted]"}
        data["notes"] = ["Notes omitted. Use a full private export to include notes and raw output."]
        data["engine_args"] = []
        data["engine_workdir"] = "[omitted]"
        data["records"] = [{k: v for k, v in r.items() if k not in {"argv", "output", "cwd", "steps"}}
                           for r in data["records"]]
    return data


def export(session, destination, include_sensitive=False):
    path = Path(destination).expanduser().resolve()
    if path.suffix not in {".json", ".html"}:
        raise ValueError("Choose a .json or .html output filename.")
    data = report_data(session, include_sensitive)
    if path.suffix == ".json":
        body = json.dumps(data, indent=2)
    else:
        esc = lambda x: html.escape(str(x))
        cards = []
        for r in data["records"]:
            raw = ""
            if include_sensitive:
                directory = f'Working directory: {esc(r["cwd"])}\n' if r.get("cwd") else ""
                raw = f'<pre>{directory}{esc(json.dumps(r.get("argv", [])))}\n\n{esc(r.get("output", ""))}</pre>'
            cards.append(f'<article><h2>{esc(r["title"])}</h2><p>{esc(r["status"])} · {esc(r.get("elapsed", 0))} seconds · {esc(r.get("effect", ""))}</p>{raw}</article>')
        body = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HIFI session report</title>
<style>body{{background:#0a0f15;color:#dee8f3;font:16px/1.6 system-ui;margin:40px auto;max-width:980px;padding:0 24px}}h1{{font-size:44px;letter-spacing:.06em}}h1 span{{color:#65f6ba}}article{{background:#111b27;border:1px solid #26364b;border-radius:12px;padding:20px;margin:18px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;color:#b4cedd}}small{{color:#92a7ba}}</style>
<small>D3FAULTH / WIRELESS WORKBENCH</small><h1>HI<span>FI</span> · SESSION REPORT</h1>
<p>{'SIMULATED DEMO DATA' if session.demo else 'RECORDED SESSION'} · {esc(session.id)} · {esc(session.created)}</p>
<p>{'Full private export: contains sensitive output.' if include_sensitive else 'Summary export: identifiers, commands, raw output and notes omitted.'}</p>
<p>A completed command is not proof of network security or a successful authentication.</p>
<pre>{esc(json.dumps(data['scope'], indent=2))}</pre>{''.join(cards)}
<h2>Notes</h2><pre>{esc(chr(10).join(data['notes']))}</pre></html>'''
    # Never silently overwrite a prior report.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(body)
    return path
