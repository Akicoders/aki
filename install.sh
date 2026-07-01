#!/bin/sh

set -eu

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

info() {
  printf '%s\n' "$1"
}

resolve_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return 0
  fi

  if [ -x "$HOME/.local/bin/uv" ]; then
    printf '%s\n' "$HOME/.local/bin/uv"
    return 0
  fi

  return 1
}

do_update() {
  script_dir="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
  cd "$script_dir"

  if [ ! -f ".env" ] && [ ! -f "uv.lock" ]; then
    fail "Aki does not appear to be installed here (no .env or uv.lock found). Run install.sh without --update first."
  fi

  if ! uv_bin="$(resolve_uv)"; then
    fail "uv is required for --update but was not found."
  fi

  if [ -d ".git" ] && command -v git >/dev/null 2>&1; then
    info "Pulling latest changes..."
    git pull || fail "git pull failed."
  else
    info "Not a git repository; skipping git pull."
  fi

  info "Running uv sync --all-extras..."
  "$uv_bin" sync --all-extras || fail "uv sync --all-extras failed."

  # Re-register the uv tool shim: editable installs pick up code changes
  # automatically, but re-running this is cheap and keeps the shim valid
  # if metadata (entry points, deps) changed.
  info "Re-installing aki as a uv tool..."
  "$uv_bin" tool install --editable . --force || fail "uv tool install failed."

  info "Aki updated successfully."
  exit 0
}

if [ "${1:-}" = "--update" ]; then
  do_update
fi

os_name="$(uname -s 2>/dev/null || printf 'unknown')"
case "$os_name" in
  Linux|Darwin) ;;
  *) fail "Unsupported OS: $os_name. install.sh currently supports Linux and macOS." ;;
esac

script_dir="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
cd "$script_dir"

if command -v python3 >/dev/null 2>&1; then
  python_bin="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  python_bin="$(command -v python)"
else
  fail "Python 3.11+ is required, but no python3 or python executable was found."
fi

python_version="$($python_bin -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
$python_bin -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
  || fail "Python 3.11+ is required. Found Python $python_version at $python_bin."

if ! uv_bin="$(resolve_uv)"; then
  info "uv not found. Installing it with Astral's installer..."

  command -v mktemp >/dev/null 2>&1 || fail "mktemp is required to install uv safely."
  tmp_installer="$(mktemp "${TMPDIR:-/tmp}/uv-installer.XXXXXX")"
  cleanup() {
    rm -f "$tmp_installer"
  }
  trap cleanup EXIT HUP INT TERM

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://astral.sh/uv/install.sh -o "$tmp_installer" \
      || fail "Failed to download the uv installer with curl."
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$tmp_installer" https://astral.sh/uv/install.sh \
      || fail "Failed to download the uv installer with wget."
  else
    fail "uv is required and neither curl nor wget is available to install it."
  fi

  sh "$tmp_installer" || fail "Astral's uv installer failed."
  uv_bin="$(resolve_uv)" || fail "uv was installed, but it is not available in PATH or at $HOME/.local/bin/uv."
fi

info "Using Python $python_version at $python_bin"
info "Using uv at $uv_bin"

[ -f ".env.example" ] || fail "Missing .env.example in the project root."

info "Running uv sync --all-extras..."
"$uv_bin" sync --all-extras || fail "uv sync --all-extras failed."

info "Installing aki as a global uv tool..."
"$uv_bin" tool install --editable . --force || fail "uv tool install failed."

if [ -f ".env" ]; then
  info ".env already exists; leaving it unchanged."
else
  cp ".env.example" ".env"
  info "Created .env from .env.example."
fi

printf '\nNext steps:\n'
printf '1. aki --help\n'
printf '2. aki mcp-config opencode\n'

if ! command -v uv >/dev/null 2>&1; then
  printf '\nNote: uv is installed at %s but is not on your PATH in this shell yet.\n' "$uv_bin"
  printf 'Open a new shell or add %s to PATH before running the commands above.\n' "$(dirname "$uv_bin")"
fi

printf '\nNote: install.sh does not modify OpenCode, Claude Code, or any other host MCP configuration files.\n'
printf 'Use `aki mcp-config <host>` to print a snippet and add it to your host config manually.\n'
