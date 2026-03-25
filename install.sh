#!/usr/bin/env bash
# FEELWORLD-05 Controller – Installer (Linux)
set -euo pipefail

# ── Kolory ────────────────────────────────────────────────
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'
B='\033[0;34m'; C='\033[0;36m'; W='\033[1;37m'; N='\033[0m'

ok()   { echo -e "${G}  [OK]${N} $*";   _beep_ok;  }
err()  { echo -e "${R}[BLAD]${N} $*";   _beep_err; exit 1; }
info() { echo -e "${B}  [..]${N} $*"; }
warn() { echo -e "${Y}   [!]${N} $*"; }

# ── Dzwiek (terminal bell + speaker-test jesli dostepny) ──
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

_beep_ok() {
    _beep 880 100; sleep 0.05; _beep 1047 150
}

_beep_err() {
    _beep 200 300; sleep 0.1; _beep 150 500
}

_beep_start() {
    _beep 523 100; sleep 0.05; _beep 659 100; sleep 0.05; _beep 784 200
}

_beep_done() {
    _beep 523 80; sleep 0.04
    _beep 659 80; sleep 0.04
    _beep 784 80; sleep 0.04
    _beep 1047 350
}

# ── Naglowek ──────────────────────────────────────────────
echo
echo -e "${W} ==========================================${N}"
echo -e "${W}   FEELWORLD-05  Controller  Installer${N}"
echo -e "${W} ==========================================${N}"
echo
_beep_start

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Krok 1: Python 3.10+ ──────────────────────────────────
echo
info "[1/4] Sprawdzam Python..."
if ! command -v python3 &>/dev/null; then
    err "Python3 nie zainstalowany. Zainstaluj:\n  sudo apt install python3 python3-venv\n  lub: sudo dnf install python3"
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=${PY_VER%%.*}
PY_MINOR=${PY_VER##*.}

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    err "Wymagany Python 3.10+, masz $(python3 --version). Zaktualizuj Python."
fi
ok "$(python3 --version)"

# ── Krok 2: venv ──────────────────────────────────────────
echo
info "[2/4] Srodowisko wirtualne..."
if [ -f "venv/bin/python" ]; then
    ok "venv juz istnieje"
else
    python3 -m venv venv 2>/dev/null || \
        err "Brak modulu venv. Zainstaluj:\n  sudo apt install python3-venv"
    ok "venv utworzone"
fi

# ── Krok 3: Zaleznosci ────────────────────────────────────
echo
info "[3/4] Instaluje zaleznosci (bleak, pynput)..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt || err "Instalacja zaleznosci nie powiodla sie."
ok "Zaleznosci zainstalowane"

# ── Krok 4: Test importow + Bluetooth ─────────────────────
echo
info "[4/4] Sprawdzam czy wszystko dziala..."

venv/bin/python - <<'EOF'
import bleak, pynput
print(f"  [OK] bleak {bleak.__version__}  |  pynput OK")
EOF
ok "Import bleak/pynput OK"

if command -v bluetoothctl &>/dev/null; then
    if bluetoothctl show 2>/dev/null | grep -q "Powered: yes"; then
        ok "Bluetooth wlaczony"
    else
        warn "Bluetooth moze byc wylaczony — sprawd: sudo bluetoothctl power on"
    fi

    # Uprawnienia
    if ! groups | grep -qE "(bluetooth|plugdev)"; then
        warn "Dodaj uzytkownika do grupy bluetooth (wymaga ponownego logowania):"
        echo  "      sudo usermod -aG bluetooth $USER"
    else
        ok "Uprawnienia Bluetooth OK"
    fi

    # Przypomnienie o parowaniu
    if [ ! -f "device_mac.txt" ]; then
        echo
        echo -e "${C}  Jesli pilot nie byl jeszcze sparowany:${N}"
        echo    "    bluetoothctl"
        echo    "    > scan on"
        echo    "    > pair XX:XX:XX:XX:XX:XX"
        echo    "    > trust XX:XX:XX:XX:XX:XX"
        echo    "    > scan off"
        echo    "    > exit"
        echo
        read -rp "  Pilot sparowany? Wcisnij Enter aby kontynuowac..."
    fi
else
    warn "bluetoothctl nie znaleziony. Zainstaluj: sudo apt install bluetooth bluez"
fi

echo
_beep_done
echo -e "${W} ==========================================${N}"
echo -e "${G}   Instalacja zakonczona! Uruchamiam...${N}"
echo -e "${W} ==========================================${N}"
echo
echo    "  Kliknij w okno przegladarki z teleprompterem,"
echo    "  potem uzywaj pilota.  Ctrl+C aby zatrzymac."
echo

venv/bin/python controller.py
