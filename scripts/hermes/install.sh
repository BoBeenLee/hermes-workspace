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
DRY_RUN=false
WITH_BROWSER=false

usage() {
  cat <<'EOF'
Usage: scripts/hermes/install.sh [options]

Install or update NousResearch Hermes Agent on an SSH target.

Options:
  --target-profile PATH  Source a target profile before applying CLI overrides
  --host HOST            SSH host, alias, or IP
  --user USER            SSH user
  --key PATH             SSH private key path
  --timeout SEC          SSH connect timeout
  --with-browser         Allow browser tooling installation
  --dry-run              Print the remote actions without changing the target
  -h, --help             Show this help

Defaults come from HERMES_TARGET, .env, or config/example.env. Built-in
fallbacks are placeholders, not a runnable host. Secrets and OAuth auth files
are not copied.
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
    --with-browser)
      WITH_BROWSER=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
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

if [ -n "$KEY_PATH" ] && [ ! -f "$KEY_PATH" ]; then
  echo "Missing SSH key: $KEY_PATH" >&2
  exit 1
fi

INSTALLER_ARGS=(--skip-setup --non-interactive)
if [ "$WITH_BROWSER" = false ]; then
  INSTALLER_ARGS+=(--skip-browser)
fi

printf -v INSTALLER_ARGS_STR '%q ' "${INSTALLER_ARGS[@]}"
INSTALLER_ARGS_STR="${INSTALLER_ARGS_STR% }"

if [ "$DRY_RUN" = true ]; then
  cat <<EOF
Dry run only. No remote changes will be made.

Target:
  ${TARGET}
  target_profile: ${TARGET_PROFILE:-unset}
  ssh_key: ${KEY_PATH:-ssh-config/default}

Remote actions:
  1. Verify SSH connectivity.
  2. Run official Hermes installer with default paths:
     curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- ${INSTALLER_ARGS_STR}
  3. Run:
     ~/.local/bin/hermes doctor

Official paths:
  code: ~/.hermes/hermes-agent
  data/config/session/log: ~/.hermes
  command: ~/.local/bin/hermes

Secrets, provider API keys, OAuth tokens, and ~/.hermes/auth.json must be
configured manually on the target after installation.
EOF
  exit 0
fi

echo "Installing Hermes Agent on ${TARGET}"
ssh "${SSH_OPTS[@]}" "$TARGET" 'whoami && hostname && pwd'

ssh "${SSH_OPTS[@]}" "$TARGET" 'bash -s' -- "${INSTALLER_ARGS[@]}" <<'REMOTE'
set -euo pipefail

INSTALLER_ARGS=("$@")
INSTALL_LOG_DIR="$HOME/.hermes/logs"
INSTALL_LOG="$INSTALL_LOG_DIR/install.log"

mkdir -p "$INSTALL_LOG_DIR"

echo "Running official Hermes installer. Log: $INSTALL_LOG"
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh \
  | bash -s -- "${INSTALLER_ARGS[@]}" 2>&1 \
  | tee "$INSTALL_LOG"

HERMES_CMD=""
if [ -x "$HOME/.local/bin/hermes" ]; then
  HERMES_CMD="$HOME/.local/bin/hermes"
elif command -v hermes >/dev/null 2>&1; then
  HERMES_CMD="$(command -v hermes)"
else
  echo "Hermes command not found after install" >&2
  exit 1
fi

export PATH="$HOME/.local/bin:$HOME/.hermes/node/bin:$HOME/.hermes/hermes-agent/node_modules/.bin:$PATH"

echo "Running hermes doctor via $HERMES_CMD"
"$HERMES_CMD" doctor
REMOTE

echo
echo "Install complete. Run scripts/hermes/doctor.sh to re-check the target."
