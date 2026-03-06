#!/usr/bin/env python3
"""
SSH Hosts Browser — serves a searchable web UI for your SSH config.

Usage:
    SSH_CONFIG_DIR=~/.ssh/config.d ./ssh-session-manager.py
    SSH_CONFIG_DIR=~/.ssh/config.d SSH_HOSTS_PORT=8888 python3 ssh-session-manager.py

Environment variables:
    SSH_CONFIG_DIR  — path to directory containing SSH config files (default: ~/.ssh/config.d)
    SSH_HOSTS_PORT  — port to serve on (default: 8822)
"""

import os
import re
import json
import http.server
import socketserver
from pathlib import Path
from urllib.parse import urlparse

CONFIG_DIR = os.environ.get("SSH_CONFIG_DIR", os.path.expanduser("~/.ssh/config.d"))
PORT = int(os.environ.get("SSH_HOSTS_PORT", 8822))
SCRIPT_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_ssh_config(text: str) -> list[dict]:
    hosts = []
    current = None
    pending_description = ""
    pending_env = ""
    pending_urls: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("##"):
            pending_description = line[2:].strip()
            continue
        if line.upper().startswith("#ENV:"):
            pending_env = line[5:].strip()
            continue
        if line.upper().startswith("#URL:"):
            url_val = line[5:].strip()
            if "::" in url_val:
                url_name, url_href = url_val.split("::", 1)
                url_entry = {"name": url_name.strip(), "url": url_href.strip()}
            else:
                url_entry = {"name": "Link", "url": url_val}
            pending_urls.append(url_entry)
            continue
        if line.startswith("#"):
            continue
        match = re.match(r"^(\w[\w-]*)\s+(.*)", line)
        if not match:
            continue
        key, value = match.group(1).lower(), match.group(2).strip()
        if key == "host":
            names = [n for n in value.split() if "*" not in n and "?" not in n]
            for name in names:
                current = {
                    "name": name,
                    "hostname": "",
                    "user": "",
                    "port": "22",
                    "identityFile": "",
                    "description": pending_description,
                    "env": pending_env,
                    "urls": list(pending_urls),
                }
                hosts.append(current)
            pending_description = ""
            pending_env = ""
            pending_urls = []
            if not names:
                current = None
        elif current:
            if key == "hostname":
                current["hostname"] = value
            elif key == "user":
                current["user"] = value
            elif key == "port":
                current["port"] = value
            elif key == "identityfile":
                current["identityFile"] = value
    return hosts


def host_to_config_block(h: dict) -> str:
    """Serialize a host dict back to SSH config file format."""
    lines = []
    if h.get("description"):
        lines.append(f"## {h['description']}")
    if h.get("env"):
        lines.append(f"#ENV: {h['env']}")
    for u in h.get("urls", []):
        lines.append(f"#URL: {u['name']}::{u['url']}")
    lines.append(f"Host {h['name']}")
    if h.get("hostname"):
        lines.append(f"  HostName {h['hostname']}")
    if h.get("user"):
        lines.append(f"  User {h['user']}")
    port = h.get("port", "22")
    if port and str(port) != "22":
        lines.append(f"  Port {port}")
    if h.get("identityFile"):
        lines.append(f"  IdentityFile {h['identityFile']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File-level helpers
# ---------------------------------------------------------------------------

def _safe_path(filename: str) -> Path | None:
    """Return resolved Path for filename inside CONFIG_DIR, or None if unsafe."""
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return None
    config_path = Path(CONFIG_DIR)
    if config_path.is_file():
        return config_path if config_path.name == filename else None
    target = config_path / filename
    try:
        target.resolve().relative_to(config_path.resolve())
    except ValueError:
        return None
    return target


def load_hosts_grouped() -> list[dict]:
    config_path = Path(CONFIG_DIR)
    groups = []
    seen: set[str] = set()

    def _dedup(hosts):
        result = []
        for h in hosts:
            if h["name"] not in seen:
                seen.add(h["name"])
                result.append(h)
        return result

    if config_path.is_file():
        hosts = _dedup(parse_ssh_config(config_path.read_text()))
        groups.append({"file": config_path.name, "hosts": hosts})
    elif config_path.is_dir():
        for filepath in sorted(config_path.iterdir()):
            if filepath.is_file() and not filepath.name.startswith(".") and filepath.suffix != ".template":
                try:
                    hosts = _dedup(parse_ssh_config(filepath.read_text()))
                    if hosts:
                        groups.append({"file": filepath.name, "hosts": hosts})
                except Exception as e:
                    print(f"⚠ Skipping {filepath}: {e}")
    else:
        print(f"⚠ SSH_CONFIG_DIR '{CONFIG_DIR}' not found — serving empty host list")

    return groups


def load_all_hosts() -> list[dict]:
    all_hosts = [h for g in load_hosts_grouped() for h in g["hosts"]]
    all_hosts.sort(key=lambda h: h["name"].lower())
    return all_hosts


def list_config_files() -> list[str]:
    """Return all config filenames currently in CONFIG_DIR."""
    config_path = Path(CONFIG_DIR)
    if config_path.is_file():
        return [config_path.name]
    if config_path.is_dir():
        return sorted(
            f.name for f in config_path.iterdir()
            if f.is_file() and not f.name.startswith(".") and f.suffix != ".template"
        )
    return []


def _rewrite_file(path: Path, hosts: list[dict]):
    """Write a list of host dicts back to a config file."""
    blocks = [host_to_config_block(h) for h in hosts]
    path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""))


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def add_host(filename: str, host: dict) -> tuple[bool, str]:
    config_path = Path(CONFIG_DIR)

    if config_path.is_file():
        if config_path.name != filename:
            return False, "Config is a single file; use its filename"
        target = config_path
    else:
        target = _safe_path(filename)
        if target is None:
            return False, "Invalid filename"
        target.parent.mkdir(parents=True, exist_ok=True)

    all_hosts = load_all_hosts()
    if any(h["name"] == host["name"] for h in all_hosts):
        return False, f"Host '{host['name']}' already exists"

    block = host_to_config_block(host)
    existing = target.read_text() if target.exists() else ""
    separator = "\n\n" if existing.strip() else ""
    target.write_text(existing.rstrip() + separator + block + "\n")
    return True, "Host added"


def update_host(filename: str, original_name: str, host: dict) -> tuple[bool, str]:
    target = _safe_path(filename)
    if target is None or not target.exists():
        return False, "File not found"

    hosts = parse_ssh_config(target.read_text())
    if not any(h["name"] == original_name for h in hosts):
        return False, f"Host '{original_name}' not found in {filename}"

    if host["name"] != original_name:
        all_hosts = load_all_hosts()
        if any(h["name"] == host["name"] for h in all_hosts):
            return False, f"Host '{host['name']}' already exists"

    new_hosts = [host if h["name"] == original_name else h for h in hosts]
    _rewrite_file(target, new_hosts)
    return True, "Host updated"


def delete_host(filename: str, host_name: str) -> tuple[bool, str]:
    target = _safe_path(filename)
    if target is None or not target.exists():
        return False, "File not found"

    hosts = parse_ssh_config(target.read_text())
    new_hosts = [h for h in hosts if h["name"] != host_name]
    if len(new_hosts) == len(hosts):
        return False, f"Host '{host_name}' not found in {filename}"

    _rewrite_file(target, new_hosts)
    return True, "Host deleted"


def create_config_file(filename: str) -> tuple[bool, str]:
    """Create a new empty config file in CONFIG_DIR."""
    config_path = Path(CONFIG_DIR)
    if config_path.is_file():
        return False, "CONFIG_DIR is a single file, cannot create new groups"
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return False, "Invalid filename"
    if not filename.endswith(".conf"):
        filename = filename + ".conf"
    target = config_path / filename
    if target.exists():
        return False, f"File '{filename}' already exists"
    config_path.mkdir(parents=True, exist_ok=True)
    target.touch()
    return True, filename


def filter_hosts_by_env(env: str) -> list[dict]:
    """Return all hosts whose env matches (case-insensitive)."""
    env_lower = env.lower()
    return [
        h for g in load_hosts_grouped()
        for h in g["hosts"]
        if h.get("env", "").lower() == env_lower
    ]


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/hosts":
            self._json(load_hosts_grouped())
        elif path.startswith("/api/env/"):
            env = path[len("/api/env/"):]
            if not env:
                self._error(400, "Missing environment name")
            else:
                self._json(filter_hosts_by_env(env))
        elif path == "/api/config":
            self._json({"config_dir": CONFIG_DIR})
        elif path == "/api/files":
            self._json(list_config_files())
        else:
            index = SCRIPT_DIR / "index.html"
            payload = index.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(payload))
            self.end_headers()
            self.wfile.write(payload)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/hosts":
            body = self._read_json()
            if body is None:
                return
            filename = body.get("file", "").strip()
            host = body.get("host", {})
            if not filename or not host.get("name"):
                self._error(400, "Missing 'file' or 'host.name'")
                return
            ok, msg = add_host(filename, host)
            if ok:
                self._json({"ok": True, "message": msg}, 201)
            else:
                self._error(400, msg)
        elif path == "/api/files":
            body = self._read_json()
            if body is None:
                return
            filename = body.get("filename", "").strip()
            if not filename:
                self._error(400, "Missing 'filename'")
                return
            ok, result = create_config_file(filename)
            if ok:
                self._json({"ok": True, "filename": result}, 201)
            else:
                self._error(400, result)
        else:
            self._error(404, "Not found")

    def do_PUT(self):
        """Update a host: PUT /api/hosts/<filename>/<host_name>"""
        parts = urlparse(self.path).path.strip("/").split("/", 3)
        # parts: ['api', 'hosts', filename, host_name]
        if len(parts) < 4 or parts[:2] != ["api", "hosts"]:
            self._error(404, "Not found")
            return
        filename, original_name = parts[2], parts[3]
        body = self._read_json()
        if body is None:
            return
        host = body.get("host", {})
        if not host.get("name"):
            self._error(400, "Missing 'host.name'")
            return
        ok, msg = update_host(filename, original_name, host)
        if ok:
            self._json({"ok": True, "message": msg})
        else:
            self._error(400, msg)

    def do_DELETE(self):
        """Delete a host: DELETE /api/hosts/<filename>/<host_name>"""
        parts = urlparse(self.path).path.strip("/").split("/", 3)
        if len(parts) < 4 or parts[:2] != ["api", "hosts"]:
            self._error(404, "Not found")
            return
        filename, host_name = parts[2], parts[3]
        ok, msg = delete_host(filename, host_name)
        if ok:
            self._json({"ok": True, "message": msg})
        else:
            self._error(400, msg)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            raw = self.rfile.read(length)
            return json.loads(raw)
        except Exception:
            self._error(400, "Invalid JSON body")
            return None

    def _json(self, data, status=200):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, code: int, message: str):
        payload = json.dumps({"error": message}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        print(f"  {args[0]}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    config_path = Path(CONFIG_DIR)
    hosts = load_all_hosts()
    rows = [("config", CONFIG_DIR)]
    if config_path.is_dir():
        files = [f for f in config_path.iterdir() if f.is_file() and not f.name.startswith(".") and f.suffix != ".template"]
        rows.append(("files", str(len(files))))
    rows.append(("hosts", str(len(hosts))))
    rows.append(("server", f"http://localhost:{PORT}"))

    label_w = max(len(k) for k, _ in rows)
    val_w   = max(len(v) for _, v in rows)
    inner_w = max(2 + label_w + 3 + val_w, 24)
    val_w   = inner_w - 2 - label_w - 3
    bar     = "─" * inner_w
    title   = "⬡  SSH Hosts Browser"

    print()
    print(f"  ┌{bar}┐")
    print(f"  │  {title}{' ' * (inner_w - 2 - len(title))}│")
    print(f"  ├{bar}┤")
    for key, val in rows:
        print(f"  │  {key:<{label_w}} : {val:<{val_w}}│")
    print(f"  └{bar}┘")
    print()

    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.allow_reuse_address = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Shutting down.")


if __name__ == "__main__":
    main()
