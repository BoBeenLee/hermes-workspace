#!/usr/bin/env bash
set -euo pipefail

HOST="192.168.0.8"
USER_NAME="bobeenlee"
KEY_PATH="$HOME/.ssh/id_ed25519_bobeenlee_nopass"
CONNECT_TIMEOUT="8"

usage() {
  cat <<'EOF'
Usage: scripts/hermes/doctor.sh [options]

Diagnose the Hermes MacBook SSH path and Hermes Agent install.

Options:
  --host HOST       SSH host or IP (default: 192.168.0.8)
  --user USER       SSH user (default: bobeenlee)
  --key PATH        SSH private key path (default: ~/.ssh/id_ed25519_bobeenlee_nopass)
  --timeout SEC     SSH connect timeout (default: 8)
  -h, --help        Show this help
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
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
  -i "$KEY_PATH"
  -o IdentitiesOnly=yes
  -o BatchMode=yes
  -o ConnectTimeout="$CONNECT_TIMEOUT"
)
TARGET="${USER_NAME}@${HOST}"

section() {
  printf '\n== %s ==\n' "$1"
}

check_local_key() {
  section "local ssh key"
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
print_kv "macos" "$(sw_vers -productVersion 2>/dev/null || printf unknown)"

printf '\n-- commands --\n'
for cmd in git python3 node npm launchctl curl; do
  print_kv "$cmd" "$(command_path "$cmd")"
done

printf '\n-- ssh authorized key fingerprints --\n'
if [ -f "$HOME/.ssh/authorized_keys" ]; then
  ssh-keygen -lf "$HOME/.ssh/authorized_keys" 2>/dev/null || printf 'authorized_keys exists but could not be fingerprinted\n'
else
  printf 'authorized_keys missing\n'
fi

printf '\n-- official install paths --\n'
for path in "$HOME/.hermes" "$HOME/.hermes/hermes-agent" "$HOME/.local/bin/hermes" "$HOME/.hermes/logs/gateway.log" "$HOME/Library/LaunchAgents/ai.hermes.gateway.plist"; do
  if [ -e "$path" ]; then
    printf 'present: %s\n' "$path"
  else
    printf 'missing: %s\n' "$path"
  fi
done

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
run_remote 'whoami && hostname && pwd' >/dev/null
echo "ssh: ok"
check_remote
