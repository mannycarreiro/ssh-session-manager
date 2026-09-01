# SSH Session Manager

A searchable web UI for your SSH config, served locally via a lightweight Python HTTP server.

## Files

| File | Description |
|------|-------------|
| `ssh-session-manager.py` | Backend: SSH config parsing and HTTP server |
| `index.html` | Frontend: searchable web UI (HTML, CSS, JS) |
| `ssh-session-manager.sh` | macOS wrapper to manage the server as a background process |
| `com.local.ssh-session-manager.plist` | macOS LaunchAgent for auto-start on login |
| `fssh` | Terminal CLI: fuzzy-search your hosts (with comments) and connect via `ssh` |

---

## Features

- **Search** across host aliases, IPs, users, descriptions, and ENV badges
- **Group/folder view** — one folder per config file, collapsible
- **Full CRUD** — add, edit, and delete hosts directly from the UI
- **New Group** — create new config file groups from the UI
- **URL badges** — clickable link buttons per host (e.g. Grafana, Kibana)
- **ENV badges** — color-coded environment labels (PROD, DEV, PAT, etc.)
- **Copy hostname** button and direct SSH/SFTP protocol links per row
- **Dark/light theme** toggle
- **Template files ignored** — `.template` files in the config directory are never loaded

---

## API Endpoints

`ssh-session-manager.py` serves `index.html` from the same directory and exposes the following REST API:

### Hosts

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/hosts` | All SSH hosts grouped by config file |
| `POST` | `/api/hosts` | Add a new host to a config file |
| `PUT` | `/api/hosts/<file>/<name>` | Update an existing host |
| `DELETE` | `/api/hosts/<file>/<name>` | Delete a host |

### Files / Groups

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/files` | List all config filenames in `SSH_CONFIG_DIR` |
| `POST` | `/api/files` | Create a new empty config file (group) |

### Filtering & Config

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/env/<env>` | All hosts matching the given ENV value (case-insensitive) |
| `GET` | `/api/config` | Returns the active `SSH_CONFIG_DIR` path |

#### `GET /api/env/<env>` example

```bash
curl localhost:8822/api/env/PROD
curl localhost:8822/api/env/dev
```

Returns a flat list of host objects whose `env` field matches (case-insensitive). Useful for scripting:

```bash
# Get all PROD hostnames
curl -s localhost:8822/api/env/PROD | python3 -c "import sys,json; [print(h['hostname']) for h in json.load(sys.stdin)]"
```

#### `POST /api/hosts` body

```json
{
  "file": "work.conf",
  "host": {
    "name": "my-server",
    "hostname": "192.168.1.10",
    "user": "ubuntu",
    "port": "22",
    "identityFile": "~/.ssh/id_rsa",
    "description": "Production box",
    "env": "PROD",
    "urls": [
      { "name": "Grafana", "url": "https://grafana.example.com" }
    ]
  }
}
```

#### `POST /api/files` body

```json
{ "filename": "work.conf" }
```

The `.conf` extension is appended automatically if omitted.

---

## Config Files Spec

```
## <Description>
#ENV: <Environment>
#URL: <Button Label>::<URL>
Host <Alias>
  HostName <IP or Hostname>
  User <UserID>
  Port <SSH Port>
  IdentityFile <path to private key>
```

- `##` — sets the description badge shown in the UI
- `#ENV:` — sets the color-coded environment badge (see ENV Colors below)
- `#URL:` — adds a clickable link button; use `Name::https://url` format; multiple lines allowed

All comment directives must appear **before** the `Host` line they apply to.

Files with the `.template` extension are automatically ignored.

**Example:**

```
## Ansible Controller
#ENV: PROD
#URL: Grafana::https://grafana.domain.com
#URL: Kibana::https://kibana.domain.com:5601
Host ansible
  HostName ansible-master.domain.com
  User manny
  Port 22
```

### ENV Colors

| ENV prefix | Color |
|------------|-------|
| `DEV` | Green |
| `SIT` | Orange |
| `PAT`, `DRT` | Yellow |
| `PROD`, `DRP` | Red |
| anything else | Grey |

---

## Quick Start

```bash
# Start the server in the background
./ssh-session-manager.sh start

# Open in your browser
./ssh-session-manager.sh open
```

---

## `fssh` — Fuzzy-search & connect from the terminal

`fssh` is a standalone CLI (no server needed) that reuses the same config parser as
`ssh-session-manager.py`. It lists every host through [`fzf`](https://github.com/junegunn/fzf),
alias on the left and group/target/ENV/comments on the right, and `ssh`s into whatever you pick.

```bash
# One-time setup: put fssh on PATH and install fzf if needed
brew install fzf
ln -sf "$(pwd)/fssh" /opt/homebrew/bin/fssh   # or anywhere already on your PATH
```

```
HOST                 FILE     USER@HOST:PORT                            ENV   COMMENTS
ansible              Ansible  manny@ansible-master.home.example.com:22        Ansible Controller
pihole               LabVms   manny@pihole-1.home.example.com:22        PROD  Pi-Hole DNS Server
pitest               LabVms   manny@pitest.home.example.com:22          DEV   PiTest Test Server
vultr-rocky-1        vultr    root@45.63.23.216:22                      PROD  Rocky 10 New Jersey [cloud-vultr-rocky-1nj]
```

Type to fuzzy-filter across alias, file, target, ENV, and description/URL comments — press
Enter to `ssh` into the highlighted host, or Esc to cancel.

```
fssh                  fuzzy-pick a host and connect
fssh <query>          pre-fill the fzf search query
fssh -e, --env NAME   only show hosts whose ENV matches NAME (case-insensitive)
fssh -p, --print      print the resolved `ssh` command instead of running it
```

Respects the same `SSH_CONFIG_DIR` environment variable as the server.

---

## Wrapper Commands

```
./ssh-session-manager.sh <command>
```

| Command | Description |
|---------|-------------|
| `start` | Start the server in the background |
| `stop` | Stop the background server |
| `restart` | Restart the background server |
| `status` | Show whether the server is running |
| `logs` | Tail the log file (Ctrl+C to exit) |
| `open` | Open `http://localhost:8822` in the browser |
| `install` | Register as a macOS LaunchAgent (auto-starts on login) |
| `uninstall` | Remove the macOS LaunchAgent |

---

## Configuration

The server is configured via environment variables, either exported in your shell or set in the plist.

| Variable | Default | Description |
|----------|---------|-------------|
| `SSH_CONFIG_DIR` | `~/.ssh/config.d` | Path to your SSH config file or directory |
| `SSH_HOSTS_PORT` | `8822` | Port the web UI is served on |

**Example — custom config path and port:**
```bash
SSH_CONFIG_DIR=~/.ssh/config SSH_HOSTS_PORT=9000 ./ssh-session-manager.sh start
```

---

## Auto-Start on Login (LaunchAgent)

To have the server start automatically every time you log in:

**Install:**
```bash
./ssh-session-manager.sh install
```

This copies the plist to `~/Library/LaunchAgents/` and loads it immediately.

**Uninstall:**
```bash
./ssh-session-manager.sh uninstall
```

> **Note:** If you move the scripts to a different directory after installing the LaunchAgent, uninstall and reinstall so the paths in the plist are updated.

### Manually editing the LaunchAgent

To change the port or config directory for the LaunchAgent, edit `com.local.ssh-session-manager.plist` before running `install`, or edit the installed copy directly:

```bash
open ~/Library/LaunchAgents/com.local.ssh-session-manager.plist
```

Then reload it:
```bash
launchctl unload ~/Library/LaunchAgents/com.local.ssh-session-manager.plist
launchctl load   ~/Library/LaunchAgents/com.local.ssh-session-manager.plist
```

---

## Logs

Logs are written to `~/Library/Logs/ssh-session-manager.log`.

```bash
# Follow live output
./ssh-session-manager.sh logs

# Or view directly
cat ~/Library/Logs/ssh-session-manager.log
```
