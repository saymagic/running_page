#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXPORT_DATA_DIR="${PROJECT_ROOT}/apple_health_export"

check_command() {
    if command -v "$1" &>/dev/null; then
        return 0
    else
        return 1
    fi
}

step_1_check_prerequisites() {
    info "Step 1/6: Checking prerequisites..."

    local missing=()

    if ! check_command python3; then
        missing+=("python3")
    else
        local py_major py_minor
        py_major=$(python3 -c 'import sys; print(sys.version_info.major)')
        py_minor=$(python3 -c 'import sys; print(sys.version_info.minor)')
        if [[ "$py_major" -lt 3 ]] || { [[ "$py_major" -eq 3 ]] && [[ "$py_minor" -lt 9 ]]; }; then
            err "Python 3.9+ required, found ${py_major}.${py_minor}"
            missing+=("python3>=3.9")
        else
            ok "Python ${py_major}.${py_minor}"
        fi
    fi

    if ! check_command uv; then
        warn "uv not found, will install via official installer"
    else
        ok "uv $(uv --version 2>/dev/null | awk '{print $2}')"
    fi

    if ! check_command git; then
        missing+=("git")
    else
        ok "Git $(git --version | awk '{print $3}')"
    fi

    if ! check_command node; then
        missing+=("node")
    else
        ok "Node $(node -v)"
    fi

    if ! check_command pnpm; then
        warn "pnpm not found, will install via corepack"
    else
        ok "pnpm $(pnpm -v)"
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        err "Missing required commands: ${missing[*]}"
        echo ""
        echo "Install them with:"
        echo "  macOS:  brew install ${missing[*]}"
        echo "  Ubuntu: sudo apt-get install ${missing[*]}"
        exit 1
    fi

    ok "All prerequisites met"
}

step_2_setup_python() {
    info "Step 2/6: Setting up Python environment (uv)..."

    cd "$PROJECT_ROOT"

    if ! check_command uv; then
        info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
        if ! check_command uv; then
            err "Failed to install uv. Please install manually: https://docs.astral.sh/uv/"
            exit 1
        fi
        ok "uv installed successfully"
    fi

    info "Installing Python dependencies via uv sync..."
    uv sync

    ok "Python dependencies installed via uv"
}

step_3_setup_node() {
    info "Step 3/6: Setting up Node.js environment..."

    cd "$PROJECT_ROOT"

    if ! check_command pnpm; then
        npm install -g corepack@latest
        corepack enable pnpm
        ok "pnpm installed via corepack"
    fi

    pnpm install --frozen-lockfile 2>/dev/null || pnpm install

    ok "Node.js dependencies installed"
}

step_4_setup_export_data() {
    info "Step 4/6: Setting up Apple Health export data..."

    mkdir -p "$EXPORT_DATA_DIR"

    local found=0
    if [[ -f "${EXPORT_DATA_DIR}/export.xml" ]]; then
        ok "Found export.xml in ${EXPORT_DATA_DIR}"
        found=1
    elif [[ -f "${EXPORT_DATA_DIR}/apple_health_export/export.xml" ]]; then
        ok "Found export.xml in ${EXPORT_DATA_DIR}/apple_health_export"
        found=1
    else
        for f in "${EXPORT_DATA_DIR}"/*.zip; do
            if [[ -f "$f" ]]; then
                info "Found zip archive: $f"
                info "It will be auto-extracted during sync"
                found=1
                break
            fi
        done
    fi

    if [[ $found -eq 0 ]]; then
        echo ""
        warn "No Apple Health export data found yet."
        echo ""
        echo "Option 1: Export from iPhone (Manual)"
        echo "  1. Open the 'Health' app on your iPhone"
        echo "  2. Tap your profile picture (top right)"
        echo "  3. Scroll down and tap 'Export All Health Data'"
        echo "  4. Save the export.zip file"
        echo "  5. Transfer it to this computer (AirDrop, iCloud, etc.)"
        echo "  6. Place the export.zip or extracted folder in:"
        echo "     ${EXPORT_DATA_DIR}/"
        echo ""
        echo "Option 2: Export via privacy.apple.com (Browser Automation)"
        echo "  Run the web export script to automate the process:"
        echo "     uv run python run_page/apple_health_web_export.py"
        echo "  Or with Apple ID credentials:"
        echo "     uv run python run_page/apple_health_web_export.py --apple-id you@example.com --password"
        echo ""
        echo "Supported formats:"
        echo "  - export.zip (compressed Apple Health export)"
        echo "  - export.xml (uncompressed XML file)"
        echo "  - Directory containing export.xml"
        echo ""
        read -rp "Press Enter to continue setup, or Ctrl+C to exit and add data first..."
    fi

    ok "Export data directory ready at ${EXPORT_DATA_DIR}"
}

step_5_sync_data() {
    info "Step 5/6: Syncing Apple Watch data..."

    cd "$PROJECT_ROOT"

    local export_path="$EXPORT_DATA_DIR"

    if [[ -f "${EXPORT_DATA_DIR}/export.xml" ]]; then
        export_path="$EXPORT_DATA_DIR"
    elif [[ -d "${EXPORT_DATA_DIR}/apple_health_export" ]]; then
        export_path="${EXPORT_DATA_DIR}/apple_health_export"
    fi

    if [[ -f "${export_path}/export.xml" ]] || [[ -f "${export_path}" ]]; then
        uv run python run_page/apple_health_sync.py "$export_path"
        ok "Apple Health data synced successfully"
    else
        warn "No export data available yet. Skipping sync."
        info "You can run sync later with:"
        info "  uv run python run_page/apple_health_sync.py /path/to/export"
    fi
}

step_6_build_and_preview() {
    info "Step 6/6: Building and launching preview..."

    cd "$PROJECT_ROOT"

    if [[ -f "src/static/activities.json" ]]; then
        ok "activities.json generated"
    else
        warn "activities.json not found - build may show empty data"
    fi

    pnpm build

    ok "Build complete!"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ok "Apple Watch + running_page setup complete!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Quick Start Commands:"
    echo ""
    echo "  # Web export (browser automation via privacy.apple.com):"
    echo "  uv run python run_page/apple_health_web_export.py"
    echo ""
    echo "  # Sync Apple Health data:"
    echo "  uv run python run_page/apple_health_sync.py ${EXPORT_DATA_DIR}"
    echo ""
    echo "  # Start dev server:"
    echo "  pnpm develop"
    echo ""
    echo "  # Generate SVG posters:"
    echo "  uv run python run_page/gen_svg.py --from-db --type github --output assets/github.svg"
    echo ""
    echo "  # Production build:"
    echo "  pnpm build"
    echo ""
    echo "Data files location:"
    echo "  Database:       run_page/data.db"
    echo "  Activities:     src/static/activities.json"
    echo "  Health export:  ${EXPORT_DATA_DIR}/"
    echo ""
}

main() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Apple Watch + running_page - One-Click Setup"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    step_1_check_prerequisites
    step_2_setup_python
    step_3_setup_node
    step_4_setup_export_data
    step_5_sync_data
    step_6_build_and_preview
}

main "$@"
