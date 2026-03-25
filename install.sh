#!/usr/bin/env bash
# FEELWORLD-05 Controller – Installer (Linux)
set -euo pipefail

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'
B='\033[0;34m'; C='\033[0;36m'; W='\033[1;37m'; N='\033[0m'

ok()   { echo -e "${G}  [OK]${N} $*";   _beep_ok;  }
err()  { echo -e "${R}[ERROR]${N} $*"; _beep_err; exit 1; }
info() { echo -e "${B}  [..]${N} $*"; }
warn() { echo -e "${Y}   [!]${N} $*"; }

_beep() {
    local freq=${1:-800} dur_ms=${2:-150}
    if command -v speaker-test &>/dev/null; then
        ( speaker-test -t sine -f "$freq" -l 1 -P 1 &>/dev/null & \
          sleep "$(echo "scale=3; $dur_ms/1000" | bc)"; kill $! 2>/dev/null ) 2>/dev/null || true
    else
        printf '\a' 2>/dev/null || true
        sleep 0.1
    fi
}

_beep_ok()    { _beep 880 100; sleep 0.05; _beep 1047 150; }
_beep_err()   { _beep 200 300; sleep 0.1;  _beep 150 500;  }
_beep_start() { _beep 523 100; sleep 0.05; _beep 659 100; sleep 0.05; _beep 784 200; }
_beep_done()  { _beep 523 80; sleep 0.04; _beep 659 80; sleep 0.04; _beep 784 80; sleep 0.04; _beep 1047 350; }

echo
echo -e "${W} ==========================================${N}"
echo -e "${W}   FEELWORLD-05  Controller  Installer${N}"
echo -e "${W} ==========================================${N}"
echo
_beep_start

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo
info "[1/4] Checking Python..."
if ! command -v python3 &>/dev/null; then
    err "Python3 not found. Install it:\n  sudo apt install python3 python3-venv\n  or: sudo dnf install python3"
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=${PY_VER%%.*}
PY_MINOR=${PY_VER##*.}

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    err "Python 3.10+ required, you have $(python3 --version). Please upgrade."
fi
ok "$(python3 --version)"

echo
info "[2/4] Virtual environment..."
if [ -f "venv/bin/python" ]; then
    ok "venv already exists"
else
    python3 -m venv venv 2>/dev/null || \
        err "venv module missing. Install it:\n  sudo apt install python3-venv"
    ok "venv created"
fi

echo
info "[3/4] Installing dependencies (bleak, pynput)..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt || err "Dependency installation failed."
ok "Dependencies installed"

echo
info "[4/4] Verifying imports..."
venv/bin/python - <<'EOF'
import bleak, pynput, importlib.metadata
print(f"  [OK] bleak {importlib.metadata.version('bleak')}  |  pynput OK")
EOF
ok "bleak/pynput OK"

if command -v bluetoothctl &>/dev/null; then
    if bluetoothctl show 2>/dev/null | grep -q "Powered: yes"; then
        ok "Bluetooth powered on"
    else
        warn "Bluetooth may be off -- run: sudo bluetoothctl power on"
    fi

    if ! groups | grep -qE "(bluetooth|plugdev)"; then
        warn "Add your user to the bluetooth group (requires re-login):"
        echo  "      sudo usermod -aG bluetooth $USER"
    else
        ok "Bluetooth permissions OK"
    fi

    if [ ! -f "device_mac.txt" ]; then
        echo
        echo -e "${C}  If the remote has not been paired yet:${N}"
        echo    "    bluetoothctl"
        echo    "    > scan on"
        echo    "    > pair XX:XX:XX:XX:XX:XX"
        echo    "    > trust XX:XX:XX:XX:XX:XX"
        echo    "    > scan off"
        echo    "    > exit"
        echo
        read -rp "  Remote paired? Press Enter to continue..."
    fi
else
    warn "bluetoothctl not found. Install: sudo apt install bluetooth bluez"
fi

echo
_beep_done
echo -e "${W} ==========================================${N}"
echo -e "${G}   Done! Launching controller...${N}"
echo -e "${W} ==========================================${N}"
echo
echo    "  Click on the teleprompter browser window,"
echo    "  then use the remote. Ctrl+C to stop."
echo

venv/bin/python controller.py
