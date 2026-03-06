#!/usr/bin/env bash
# ssh-session-manager.sh — macOS wrapper to run ssh-session-manager.py in the background

set -euo pipefail

_SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$_SOURCE" ]]; do
    _DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
    _SOURCE="$(readlink "$_SOURCE")"
    [[ "$_SOURCE" != /* ]] && _SOURCE="$_DIR/$_SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$_SOURCE")" && pwd)"
unset _SOURCE _DIR
PY_SCRIPT="$SCRIPT_DIR/ssh-session-manager.py"
PID_FILE="${TMPDIR:-/tmp}/ssh-session-manager.pid"
LOG_FILE="$HOME/Library/Logs/ssh-session-manager.log"
PORT="${SSH_HOSTS_PORT:-8822}"

_is_running() {
    [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

cmd_start() {
    if _is_running; then
        echo "Already running (PID $(cat "$PID_FILE"))"
        return 0
    fi
    mkdir -p "$(dirname "$LOG_FILE")"
    nohup python3 "$PY_SCRIPT" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Started (PID $!) — http://localhost:$PORT"
    echo "Logs: $LOG_FILE"
}

cmd_stop() {
    if ! _is_running; then
        echo "Not running"
        [[ -f "$PID_FILE" ]] && rm -f "$PID_FILE"
        return 0
    fi
    kill "$(cat "$PID_FILE")"
    rm -f "$PID_FILE"
    echo "Stopped"
}

cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

cmd_status() {
    if _is_running; then
        echo "Running (PID $(cat "$PID_FILE")) — http://localhost:$PORT"
    else
        echo "Stopped"
    fi
}

cmd_logs() {
    if [[ ! -f "$LOG_FILE" ]]; then
        echo "No log file at $LOG_FILE"
        return 1
    fi
    tail -f "$LOG_FILE"
}

cmd_open() {
    open "http://localhost:$PORT"
}

cmd_install() {
    local plist_src="$SCRIPT_DIR/com.local.ssh-session-manager.plist"
    local plist_dst="$HOME/Library/LaunchAgents/com.local.ssh-session-manager.plist"

    if [[ ! -f "$plist_src" ]]; then
        echo "Plist not found: $plist_src"
        return 1
    fi

    cp "$plist_src" "$plist_dst"
    launchctl load "$plist_dst"
    echo "Installed and loaded LaunchAgent — will auto-start on login"
}

cmd_uninstall() {
    local plist_dst="$HOME/Library/LaunchAgents/com.local.ssh-session-manager.plist"

    if [[ ! -f "$plist_dst" ]]; then
        echo "LaunchAgent not installed"
        return 0
    fi

    launchctl unload "$plist_dst"
    rm -f "$plist_dst"
    echo "Uninstalled LaunchAgent"
}

usage() {
    cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  start      Start in background
  stop       Stop background process
  restart    Restart background process
  status     Show running status
  logs       Tail the log file
  open       Open in browser
  install    Install as a macOS LaunchAgent (auto-start on login)
  uninstall  Remove macOS LaunchAgent

Environment variables:
  SSH_CONFIG_DIR   Path to SSH config dir (default: ~/.ssh/config.d)
  SSH_HOSTS_PORT   Port to serve on (default: 8822)
EOF
}

case "${1:-}" in
    start)     cmd_start ;;
    stop)      cmd_stop ;;
    restart)   cmd_restart ;;
    status)    cmd_status ;;
    logs)      cmd_logs ;;
    open)      cmd_open ;;
    install)   cmd_install ;;
    uninstall) cmd_uninstall ;;
    *)         usage; exit 1 ;;
esac
