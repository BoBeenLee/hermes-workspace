#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET_PROFILE="${HERMES_TARGET:-}"
for ((i = 1; i <= $#; i++)); do
  if [[ "${!i}" == "--target-profile" ]]; then
    j=$((i + 1))
    TARGET_PROFILE="${!j:-}"
  fi
done

resolve_env_file() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf '%s\n' "$path"
  else
    printf '%s\n' "$ROOT_DIR/$path"
  fi
}

if [[ -n "$TARGET_PROFILE" ]]; then
  TARGET_PROFILE_FILE="$(resolve_env_file "$TARGET_PROFILE")"
  if [[ ! -f "$TARGET_PROFILE_FILE" ]]; then
    echo "target profile not found: $TARGET_PROFILE_FILE" >&2
    exit 2
  fi
  # shellcheck disable=SC1090
  source "$TARGET_PROFILE_FILE"
elif [[ -f "$ROOT_DIR/.env" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
elif [[ -f "$ROOT_DIR/config/example.env" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/config/example.env"
fi

HOST="${HERMES_REMOTE_HOST:-replace-me-host}"
USER_NAME="${HERMES_REMOTE_USER:-hermes}"
KEY_PATH="${HERMES_SSH_KEY:-}"
CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-8}"

usage() {
  cat <<'EOF'
Usage: scripts/hermes/doctor.sh [options]

Diagnose a Hermes Agent SSH target and install.

Options:
  --target-profile PATH  Source a target profile before applying CLI overrides
  --host HOST            SSH host, alias, or IP
  --user USER            SSH user
  --key PATH             SSH private key path
  --timeout SEC          SSH connect timeout
  -h, --help             Show this help

Defaults come from HERMES_TARGET, .env, or config/example.env. Built-in
fallbacks are placeholders, not a runnable host. Secrets and OAuth auth files
are not read.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target-profile)
      shift 2
      ;;
    --host)
      HOST="${2:?missing value for --host}"
      shift 2
      ;;
    --user)
      USER_NAME="${2:?missing value for --user}"
      shift 2
      ;;
    --key)
      KEY_PATH="${2:?missing value for --key}"
      shift 2
      ;;
    --timeout)
      CONNECT_TIMEOUT="${2:?missing value for --timeout}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

SSH_OPTS=(
  -o BatchMode=yes
  -o ConnectTimeout="$CONNECT_TIMEOUT"
)
if [ -n "$KEY_PATH" ]; then
  SSH_OPTS=(-i "$KEY_PATH" -o IdentitiesOnly=yes "${SSH_OPTS[@]}")
fi
if [[ "$HOST" == *@* ]]; then
  TARGET="$HOST"
else
  TARGET="${USER_NAME}@${HOST}"
fi

section() {
  printf '\n== %s ==\n' "$1"
}

check_local_key() {
  section "local ssh key"
  if [ -z "$KEY_PATH" ]; then
    echo "key: ssh-config/default"
    echo "public key: skipped because no explicit HERMES_SSH_KEY or --key was provided"
    return 0
  fi
  if [ ! -f "$KEY_PATH" ]; then
    echo "missing: $KEY_PATH"
    return 1
  fi

  chmod 600 "$KEY_PATH" 2>/dev/null || true
  echo "key: $KEY_PATH"

  if ssh-keygen -y -f "$KEY_PATH" >/dev/null 2>&1; then
    echo "public key: readable without passphrase prompt"
  else
    echo "public key: failed to read non-interactively"
    return 1
  fi

  if [ -f "${KEY_PATH}.pub" ]; then
    ssh-keygen -lf "${KEY_PATH}.pub"
  else
    ssh-keygen -y -f "$KEY_PATH" | ssh-keygen -lf -
  fi
}

run_remote() {
  ssh "${SSH_OPTS[@]}" "$TARGET" "$@"
}

check_remote() {
  section "remote hermes doctor"
  run_remote 'bash -s' <<'REMOTE'
set -u

export PATH="$HOME/.local/bin:$HOME/.hermes/node/bin:$HOME/.hermes/hermes-agent/node_modules/.bin:$PATH"

print_kv() {
  printf '%s=%s\n' "$1" "$2"
}

command_path() {
  name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    command -v "$name"
  else
    printf 'missing'
  fi
}

print_kv "whoami" "$(whoami)"
print_kv "hostname" "$(hostname)"
print_kv "pwd" "$(pwd)"
print_kv "kernel" "$(uname -s 2>/dev/null || printf unknown)"
print_kv "macos" "$(sw_vers -productVersion 2>/dev/null || printf not-macos)"
if [ -f /etc/os-release ]; then
  . /etc/os-release
  print_kv "linux" "${PRETTY_NAME:-unknown}"
fi

printf '\n-- commands --\n'
for cmd in git python3 node npm launchctl systemctl curl; do
  print_kv "$cmd" "$(command_path "$cmd")"
done

printf '\n-- ssh authorized key fingerprints --\n'
if [ -f "$HOME/.ssh/authorized_keys" ]; then
  ssh-keygen -lf "$HOME/.ssh/authorized_keys" 2>/dev/null || printf 'authorized_keys exists but could not be fingerprinted\n'
else
  printf 'authorized_keys missing\n'
fi

printf '\n-- official install paths --\n'
for path in "$HOME/.hermes" "$HOME/.hermes/hermes-agent" "$HOME/.local/bin/hermes" "$HOME/.hermes/logs/gateway.log"; do
  if [ -e "$path" ]; then
    printf 'present: %s\n' "$path"
  else
    printf 'missing: %s\n' "$path"
  fi
done
if command -v launchctl >/dev/null 2>&1; then
  path="$HOME/Library/LaunchAgents/ai.hermes.gateway.plist"
  if [ -e "$path" ]; then
    printf 'present: %s\n' "$path"
  else
    printf 'missing: %s\n' "$path"
  fi
fi

printf '\n-- managed runtime paths --\n'
for path in "$HOME/.hermes/bin/uv" "$HOME/.hermes/node/bin/node" "$HOME/.hermes/node/bin/npm"; do
  if [ -x "$path" ]; then
    printf 'present: %s\n' "$path"
  else
    printf 'missing: %s\n' "$path"
  fi
done

printf '\n-- git checkout --\n'
if [ -d "$HOME/.hermes/hermes-agent/.git" ]; then
  git -C "$HOME/.hermes/hermes-agent" status --short --branch 2>/dev/null || true
  git -C "$HOME/.hermes/hermes-agent" log --oneline -1 --decorate 2>/dev/null || true
else
  printf 'not installed: ~/.hermes/hermes-agent\n'
fi

printf '\n-- hermes command --\n'
HERMES_CMD=""
if [ -x "$HOME/.local/bin/hermes" ]; then
  HERMES_CMD="$HOME/.local/bin/hermes"
elif command -v hermes >/dev/null 2>&1; then
  HERMES_CMD="$(command -v hermes)"
fi

if [ -n "$HERMES_CMD" ]; then
  print_kv "hermes" "$HERMES_CMD"
  "$HERMES_CMD" --help >/dev/null 2>&1 && printf 'hermes help: ok\n' || printf 'hermes help: failed\n'

  printf '\n-- hermes doctor --\n'
  "$HERMES_CMD" doctor 2>&1 || true

  printf '\n-- gateway status --\n'
  "$HERMES_CMD" gateway status 2>&1 || true
else
  printf 'hermes: missing\n'
fi
REMOTE
}

check_local_key
section "ssh connection"
echo "target: $TARGET"
echo "target_profile: ${TARGET_PROFILE:-unset}"
run_remote 'whoami && hostname && pwd' >/dev/null
echo "ssh: ok"
check_remote
