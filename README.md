# FEELWORLD-05 → Teleprompter Controller

Makes the **FEELWORLD-05 Bluetooth remote** work as a keyboard/scroll controller for web-based teleprompters (tested with [telepromptermirror.com](https://telepromptermirror.com/telepromptersoftware.htm)).

Windows natively registers the device as a game controller and ignores its buttons in browser apps. This tool connects directly over BLE GATT, reads the proprietary `E619` service, and injects keyboard/mouse events via `pynput`.

---

## Hardware

- FEELWORLD-05 Bluetooth remote — find your MAC in Windows Bluetooth settings or `bluetoothctl` on Linux
- Bluetooth 4.0+ adapter
- Windows 10+ or Linux with BlueZ

---

## Quick start (Python)

```bash
# 1. Create virtualenv and install deps
python -m venv venv

# Windows
venv\Scripts\pip install -r requirements.txt

# Linux
venv/bin/pip install -r requirements.txt

# 2. Pair the remote via OS Bluetooth settings (do this once)

# 3. Map your buttons
python diagnose.py       # Windows
# or
venv/bin/python diagnose.py  # Linux

# 4. Run the controller
python controller.py
```

Click into the browser/teleprompter window, then use the remote.

---

## Quick start (standalone executable, no Python needed)

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole controller.py
```

Distribute `dist/controller.exe` (Windows) or `dist/controller` (Linux) together with `mapping.json`.

---

## Button mapping

Run `diagnose.py` → option **2** to interactively map each button:

```
--- [OK]  [space]  —  Start / Stop
    Press [OK] on the remote...
    >>> DETECTED  char:1002  byte[7]  bit7  mask=0x80
    Trzymaj i PUSC [OK] (recording 1.5s)...
    Recorded 4 events:
      char:1002 byte[7] bit7 mask=0x80  press=1x  release=1x  <<
    This bit has PRESS and RELEASE — trigger selectable.
    Action [space]? Enter=yes / other / x=skip:
    Trigger [P]ress/[R]elease (Enter=press): r
```

Saved to `mapping.json`. Analog axes are auto-detected including direction.

### Default mapping

| Button       | Action        | Description        |
|--------------|---------------|--------------------|
| OK           | `space`       | Start / Stop       |
| Menu         | `f11`         | Fullscreen toggle  |
| Back/On      | `escape`      | Rewind to start    |
| A            | `left`        | Slower             |
| B            | `right`       | Faster             |
| X            | `up`          | Font size up       |
| Y            | `down`        | Font size down     |
| Analog up    | `scroll_up`   | Scroll up          |
| Analog down  | `scroll_down` | Scroll down        |

Available actions: `space` `left` `right` `up` `down` `escape` `f11` `scroll_up` `scroll_down`

---

## Device discovery

Both `diagnose.py` and `controller.py` find the remote automatically — no MAC address configuration needed:

1. **Cache hit** — if `device_mac.txt` exists, the stored address is verified via a 5-second BLE scan. If the remote is nearby, startup takes ~1 second.
2. **Service scan** — scans for a device advertising the proprietary `E619` service UUID (up to 10 s).
3. **Name fallback** — scans for a device whose name contains "feelworld" (up to 10 s).

The discovered address is saved to `device_mac.txt` for next time. Delete this file to force a fresh scan.

---

## Configuration

Edit the constants at the top of `controller.py`:

```python
AXIS_THRESHOLD  = 60    # how far to push analog before it triggers
AXIS_RELEASE    = 30    # hysteresis: how close to center = released
AXIS_DEBOUNCE_MS = 180  # ms to wait before first fire (filters accidental touches)
AXIS_REPEAT_MS  = 300   # ms between repeats while held
SCROLL_AMOUNT   = 2     # scroll clicks per event
```

---

## Autostart

### Windows — run at login (no window)

```bat
schtasks /create /tn "FEELWORLD Controller" ^
  /tr "C:\path\to\pilot_feelworld_as_keyboard\start.bat" ^
  /sc onlogon /f
```

Or place `start.bat` in `shell:startup`.

### Linux — systemd user service

```bash
# Edit feelworld.service: set correct WorkingDirectory path
cp feelworld.service ~/.config/systemd/user/
systemctl --user enable feelworld
systemctl --user start feelworld

# Check status
systemctl --user status feelworld
```

On Linux the device must be paired first:
```bash
bluetoothctl
> pair F0:19:88:22:AD:C1
> trust F0:19:88:22:AD:C1
```

---

## How it works

The FEELWORLD-05 exposes a proprietary GATT service (`00001000-e619-419b-bc43-821e71a409b7`) with two notify characteristics:

- `CHAR_1001` — auxiliary data
- `CHAR_1002` — button + analog state (main)

The OS locks the standard HID service (`0x1812`) but the E619 service is freely accessible. The controller subscribes to BLE notifications on both characteristics and translates bit-level changes to keyboard/mouse events.

Analog axis events use debounce + hysteresis to prevent phantom triggers on release.

---

## Files

| File | Purpose |
|------|---------|
| `diagnose.py` | Interactive button mapper → writes `mapping.json` |
| `controller.py` | Main controller, reads `mapping.json` |
| `mapping.json` | Your button → action mapping (generated) |
| `device_mac.txt` | BLE address cache (generated, safe to delete) |
| `start.bat` | Windows background launcher |
| `feelworld.service` | Linux systemd unit |
| `requirements.txt` | Python dependencies |

---

## Requirements

- Python 3.10+
- `bleak >= 0.21` — cross-platform BLE
- `pynput >= 1.7` — keyboard/mouse injection
