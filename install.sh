#!/bin/sh
set -eu

# VibeTune cross-platform installer for Linux and macOS.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ashrafpy/vibetune/main/install.sh | sh

VIBETUNE_REPO="${VIBETUNE_REPO:-ashrafpy/vibetune}"
VIBETUNE_REF="${VIBETUNE_REF:-main}"
VIBETUNE_SOURCE="${VIBETUNE_SOURCE:-}"
VIBETUNE_NO_PLAYER="${VIBETUNE_NO_PLAYER:-0}"
VIBETUNE_BIN_DIR="${VIBETUNE_BIN_DIR:-$HOME/.local/bin}"

say() {
    printf '%s\n' "$*"
}

warn() {
    printf 'Warning: %s\n' "$*" >&2
}

err() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        err "Required command '$1' was not found. Please install it and retry."
    fi
}

detect_os() {
    uname_s="$(uname -s 2>/dev/null || printf 'unknown')"
    case "$uname_s" in
        Linux*)  printf 'linux' ;;
        Darwin*) printf 'darwin' ;;
        *)       err "Unsupported OS '$uname_s'. On Windows, use install.ps1 via PowerShell." ;;
    esac
}

detect_arch() {
    uname_m="$(uname -m 2>/dev/null || printf 'unknown')"
    case "$uname_m" in
        x86_64|amd64)   printf 'x86_64' ;;
        aarch64|arm64)  printf 'arm64' ;;
        armv6l|armv7l)  printf 'armv6' ;;
        *)              printf '%s' "$uname_m" ;;
    esac
}

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return 0
    fi
    if [ -x "$HOME/.local/bin/uv" ]; then
        printf '%s\n' "$HOME/.local/bin/uv"
        return 0
    fi
    if [ -x "$HOME/.cargo/bin/uv" ]; then
        printf '%s\n' "$HOME/.cargo/bin/uv"
        return 0
    fi
    return 1
}

ensure_uv() {
    if UV_BIN="$(find_uv)"; then
        printf '%s\n' "$UV_BIN"
        return 0
    fi

    need_cmd curl
    say "Installing uv (Python package & tool manager)..." >&2
    curl -fsSL https://astral.sh/uv/install.sh | sh >&2
    PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    export PATH

    if UV_BIN="$(find_uv)"; then
        printf '%s\n' "$UV_BIN"
        return 0
    fi
    err "uv installation finished, but the 'uv' binary could not be located."
}

install_go_librespot() {
    os_name="$1"
    arch_name="$2"

    if [ "$VIBETUNE_NO_PLAYER" = "1" ]; then
        say "Skipping optional go-librespot local audio engine (VIBETUNE_NO_PLAYER=1)."
        return 0
    fi

    if command -v go-librespot >/dev/null 2>&1 || [ -x "$VIBETUNE_BIN_DIR/go-librespot" ] || [ -x "/opt/homebrew/bin/go-librespot" ]; then
        say "go-librespot is already installed; keeping existing binary."
        return 0
    fi

    if [ "$os_name" = "darwin" ]; then
        if command -v brew >/dev/null 2>&1; then
            say "Installing optional local audio engine (go-librespot) via Homebrew..."
            if brew install go-librespot; then
                say "Installed go-librespot via Homebrew."
            else
                warn "Homebrew install of go-librespot failed. VibeTune still works in --remote-only mode."
            fi
        else
            say "Note: Install Homebrew and run 'brew install go-librespot' for local macOS playback (or use 'vibetune --remote-only')."
        fi
        return 0
    fi

    case "$arch_name" in
        x86_64|arm64|armv6) ;;
        *)
            warn "No prebuilt go-librespot release asset for architecture '$arch_name'. VibeTune will work in --remote-only mode."
            return 0
            ;;
    esac

    if ! command -v curl >/dev/null 2>&1 || ! command -v tar >/dev/null 2>&1; then
        warn "curl and tar are required to download go-librespot. Skipping local audio engine."
        return 0
    fi

    asset_url="https://github.com/devgianlu/go-librespot/releases/latest/download/go-librespot_linux_${arch_name}.tar.gz"
    tmp_dir="$(mktemp -d)"
    say "Installing optional local audio engine (go-librespot for linux/${arch_name})..."

    if curl -fsSL "$asset_url" -o "$tmp_dir/go-librespot.tar.gz" && \
       tar -xzf "$tmp_dir/go-librespot.tar.gz" -C "$tmp_dir" && \
       [ -f "$tmp_dir/go-librespot" ]; then
        mkdir -p "$VIBETUNE_BIN_DIR"
        cp "$tmp_dir/go-librespot" "$VIBETUNE_BIN_DIR/go-librespot"
        chmod +x "$VIBETUNE_BIN_DIR/go-librespot"
        say "Installed go-librespot to $VIBETUNE_BIN_DIR/go-librespot"
    else
        warn "Could not download/extract go-librespot from $asset_url. VibeTune still works in --remote-only mode."
    fi
    rm -rf "$tmp_dir"
}

main() {
    OS_NAME="$(detect_os)"
    ARCH_NAME="$(detect_arch)"

    say "Installing VibeTune for ${OS_NAME}/${ARCH_NAME}..."
    UV_BIN="$(ensure_uv)"

    if [ -n "$VIBETUNE_SOURCE" ]; then
        PKG_SOURCE="$VIBETUNE_SOURCE"
    else
        PKG_SOURCE="https://github.com/${VIBETUNE_REPO}/archive/${VIBETUNE_REF}.tar.gz"
    fi

    say "Installing vibetune CLI via uv..."
    "$UV_BIN" tool install --force --python ">=3.11" "$PKG_SOURCE"
    "$UV_BIN" tool update-shell >/dev/null 2>&1 || true

    install_go_librespot "$OS_NAME" "$ARCH_NAME"

    TOOL_BIN_DIR="${UV_TOOL_BIN_DIR:-$HOME/.local/bin}"
    VIBETUNE_BIN=""
    if [ -x "$TOOL_BIN_DIR/vibetune" ]; then
        VIBETUNE_BIN="$TOOL_BIN_DIR/vibetune"
    elif [ -x "$HOME/.local/bin/vibetune" ]; then
        VIBETUNE_BIN="$HOME/.local/bin/vibetune"
    elif command -v vibetune >/dev/null 2>&1; then
        VIBETUNE_BIN="$(command -v vibetune)"
    fi

    if [ -n "$VIBETUNE_BIN" ]; then
        VER_OUT="$("$VIBETUNE_BIN" --version 2>/dev/null || true)"
        say ""
        say "Successfully installed ${VER_OUT:-VibeTune} at $VIBETUNE_BIN"
    else
        warn "VibeTune was installed, but the 'vibetune' executable was not found on PATH."
    fi

    case ":${PATH}:" in
        *":${TOOL_BIN_DIR}:"*) ;;
        *)
            say ""
            say "Add ${TOOL_BIN_DIR} to your PATH (or restart your shell):"
            say "  export PATH=\"${TOOL_BIN_DIR}:\$PATH\""
            ;;
    esac

    say ""
    say "Next steps:"
    say "  1. Configure Spotify API keys:  vibetune --setup"
    say "  2. (Optional) Local audio auth: vibetune --auth-player"
    say "  3. Launch VibeTune:             vibetune"
}

main "$@"
