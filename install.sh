#!/bin/sh

set -eu

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

info() {
  printf '%s\n' "$1"
}

AKI_REPO_URL="https://github.com/Akicoders/aki.git"

# When this script is piped straight into a shell (curl -fsSL .../install.sh |
# sh), there is no local checkout yet: $0 is not a real script path (it's
# "sh", "/dev/stdin", or similar), and even when it does resolve to a path,
# that directory may just hold this one file, not a full clone. Detect that
# case by checking for pyproject.toml next to the script; if it's missing,
# clone the repo into ./aki in the current directory and re-run install.sh
# from inside the clone. A normal `sh install.sh` run from an existing clone
# always finds pyproject.toml next to it and skips this entirely.
self_clone_if_needed() {
  candidate_dir=""
  case "$0" in
    */*)
      candidate_dir="$(CDPATH= cd -- "$(dirname "$0")" 2>/dev/null && pwd)" || candidate_dir=""
      ;;
  esac

  if [ -n "$candidate_dir" ] && [ -f "$candidate_dir/pyproject.toml" ]; then
    return 0
  fi

  info "Standalone run detected (no local Aki checkout next to this script)."

  command -v git >/dev/null 2>&1 || fail "git is required to clone Aki. Install git and re-run."

  if [ -d "aki" ]; then
    if [ -f "aki/pyproject.toml" ]; then
      info "Found an existing ./aki checkout; using it."
    else
      fail "./aki already exists but doesn't look like an Aki checkout. Remove or rename it, then re-run."
    fi
  else
    info "Cloning Aki into ./aki..."
    git clone --depth 1 "$AKI_REPO_URL" aki || fail "git clone failed."
  fi

  cd aki || fail "Could not enter ./aki after cloning."
  info "Continuing install from ./aki..."
  exec sh install.sh "$@"
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

# Resolve the freshly-installed `aki` tool shim. `uv tool install` puts it on
# $HOME/.local/bin by default, but that directory may not be on PATH yet in
# the current shell (e.g. first-ever install, before a new shell is opened).
# Falls back to invoking it through `uv tool run`, which finds the installed
# tool without needing PATH to be updated.
resolve_aki_cmd() {
  uv_bin_local="$1"

  if command -v aki >/dev/null 2>&1; then
    printf '%s\n' "aki"
    return 0
  fi

  if [ -x "$HOME/.local/bin/aki" ]; then
    printf '%s\n' "$HOME/.local/bin/aki"
    return 0
  fi

  printf '%s\n' "$uv_bin_local tool run aki"
  return 0
}

# Run `aki setup` (config bootstrap + doctor, same essential-check split as
# `_ESSENTIAL_DOCTOR_CHECKS` in src/agentos/cli/main.py) and fail the install
# if it reports unhealthy. A missing Qwen API key is a warning inside `aki
# setup` itself, not a hard failure, so this mirrors that behavior exactly
# instead of reimplementing pass/fail criteria here.
run_self_verify() {
  verify_label="$1"
  aki_cmd="$(resolve_aki_cmd "$uv_bin")"

  info "Running aki setup to verify the $verify_label..."
  # shellcheck disable=SC2086
  if ! $aki_cmd setup; then
    fail "aki setup reported the installation is unhealthy (see checks above). $verify_label did not complete cleanly."
  fi
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
  #
  # --force alone only replaces the entry point/shim; it does not force uv
  # to re-resolve or refetch dependency versions, so a previously cached
  # resolution can survive a "fresh" tool install. --reinstall implies
  # --refresh and forces every package in the tool's environment to be
  # re-resolved and reinstalled, which is what actually eliminates stale
  # dependency risk (this is the root cause of the tree-sitter/textual
  # error that only `aki update` used to fix). `uv tool uninstall` first is
  # unnecessary on top of --reinstall: it would only remove the shim before
  # recreating it, which --force already does.
  info "Re-installing aki as a uv tool..."
  "$uv_bin" tool install --editable . --force --reinstall || fail "uv tool install failed."

  run_self_verify "update"

  info "Aki updated successfully."
  exit 0
}

if [ "${1:-}" = "--update" ]; then
  do_update
fi

self_clone_if_needed "$@"

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

# See the comment in do_update() above the equivalent tool-install call:
# --reinstall (on top of --force) is what actually guarantees a clean,
# non-stale dependency resolution for the installed tool environment.
info "Installing aki as a global uv tool..."
"$uv_bin" tool install --editable . --force --reinstall || fail "uv tool install failed."

if [ -f ".env" ]; then
  info ".env already exists; leaving it unchanged."
else
  cp ".env.example" ".env"
  info "Created .env from .env.example."
fi

printf '\n'
run_self_verify "install"

printf '\nNext steps:\n'
printf '1. aki --help\n'
printf '2. aki mcp-config opencode\n'

if ! command -v uv >/dev/null 2>&1; then
  printf '\nNote: uv is installed at %s but is not on your PATH in this shell yet.\n' "$uv_bin"
  printf 'Open a new shell or add %s to PATH before running the commands above.\n' "$(dirname "$uv_bin")"
fi

printf '\nNote: install.sh does not modify OpenCode, Claude Code, or any other host MCP configuration files.\n'
printf 'Use `aki mcp-config <host>` to print a snippet and add it to your host config manually.\n'
