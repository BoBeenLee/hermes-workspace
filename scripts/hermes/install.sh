#!/usr/bin/env bash
set -euo pipefail

HOST="192.168.0.8"
USER_NAME="bobeenlee"
KEY_PATH="$HOME/.ssh/id_ed25519_bobeenlee_nopass"
CONNECT_TIMEOUT="8"
DRY_RUN=false
WITH_BROWSER=false

usage() {
  cat <<'EOF'
Usage: scripts/hermes/install.sh [options]

Install or update NousResearch Hermes Agent on the Hermes MacBook.

Options:
  --host HOST       SSH host or IP (default: 192.168.0.8)
  --user USER       SSH user (default: bobeenlee)
  --key PATH        SSH private key path (default: ~/.ssh/id_ed25519_bobeenlee_nopass)
  --timeout SEC     SSH connect timeout (default: 8)
  --with-browser    Allow browser tooling installation
  --dry-run         Print the remote actions without changing the target
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
  -i "$KEY_PATH"
  -o IdentitiesOnly=yes
  -o BatchMode=yes
  -o ConnectTimeout="$CONNECT_TIMEOUT"
)
TARGET="${USER_NAME}@${HOST}"

if [ ! -f "$KEY_PATH" ]; then
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
