# FEELWORLD-05 → Teleprompter Controller

Makes the **FEELWORLD-05 Bluetooth remote** work as a keyboard/scroll controller for web-based teleprompters (tested with [telepromptermirror.com](https://telepromptermirror.com/telepromptersoftware.htm)).

Windows natively registers the device as a game controller and ignores its buttons in browser apps. This tool connects directly over BLE GATT, reads the proprietary `E619` service, and injects keyboard/mouse events via `pynput`.

---

## Quick start

### Windows

```bat
install.bat
```

### Linux

```bash
bash install.sh
```

The installer creates a virtualenv, installs dependencies, verifies imports, and launches the controller. Pair the remote via OS Bluetooth settings before running.

---

## Manual setup

```bash
# Install uv if you don't have it: https://docs.astral.sh/uv/getting-started/installation/
uv sync
uv run controller.py
```

Click into the browser/teleprompter window, then use the remote.

---

## Button mapping

`mapping.json` is a static config file shipped with the repo — no setup needed. All FEELWORLD-05 units send the same bit patterns so this mapping works out of the box.

### Default mapping

| Button       | Action        | Description        |
|--------------|---------------|--------------------|
| OK           | `space`       | Start / Stop       |
| Menu         | `f11`         | Fullscreen toggle  |
| Back/On      | `escape`      | Rewind to start    |
| A            | `left`        | Slower             |
| B            | `right`       | Faster             |
| X            | `scroll_up`   | Scroll up          |
| Y            | `scroll_down` | Scroll down        |
| Analog up    | `scroll_up`   | Scroll up          |
| Analog down  | `scroll_down` | Scroll down        |

Available actions: `space` `left` `right` `up` `down` `escape` `f11` `scroll_up` `scroll_down`

To remap, edit `mapping.json` directly. To re-detect bit patterns on your unit, run `diagnose.py` (see below).

---

## Device discovery

`controller.py` finds the remote automatically — no MAC address configuration needed:

1. **Cache** — if `device_mac.txt` exists, the stored address is verified via a quick BLE scan. If the remote is nearby, startup takes ~1 second.
2. **Service UUID scan** — scans for a device advertising the proprietary `E619` service UUID (10 s).
3. **Name scan** — scans for a device whose name contains "feelworld".
4. **Windows registry** — checks paired BLE devices in `HKLM\SYSTEM\CurrentControlSet\Enum\BTHLE` (works even when the remote is already connected and not advertising).

The discovered address is saved to `device_mac.txt`. Delete this file to force a fresh scan.

---

## Configuration

Edit the constants at the top of `controller.py`:

```python
AXIS_THRESHOLD   = 60    # how far to push analog before it triggers
AXIS_RELEASE     = 30    # hysteresis: how close to center = released
AXIS_DEBOUNCE_MS = 180   # ms to wait before first fire (filters accidental touches)
AXIS_REPEAT_MS   = 300   # ms between repeats while held
SCROLL_AMOUNT    = 2     # scroll clicks per event
```

---

## Autostart

### Windows

Place `start.bat` in the Startup folder:

```
shell:startup
```

### Linux — systemd user service

```bash
mkdir -p ~/.config/systemd/user
sed "s|%h/pilot_feelworld_as_keyboard|$(pwd)|g" \
    feelworld.service > ~/.config/systemd/user/feelworld.service
systemctl --user daemon-reload
systemctl --user enable --now feelworld

# Logs
journalctl --user -u feelworld -f
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
| `controller.py` | Main BLE controller |
| `mapping.json` | Button → action mapping (static config, edit to remap) |
| `install.bat` | Windows installer + launcher |
| `install.sh` | Linux installer + launcher |
| `start.bat` | Windows manual launcher |
| `feelworld.service` | Linux systemd unit |
| `requirements.txt` | Python dependencies |
| `diagnose.py` | Debug tool — raw BLE preview + interactive remapper |
| `device_mac.txt` | BLE address cache (auto-generated, safe to delete) |

---

## Requirements

- [uv](https://docs.astral.sh/uv/) — installed automatically by the installer scripts
- Python 3.10+ — managed automatically by uv
- `bleak >= 0.21` — cross-platform BLE
- `pynput == 1.7.7` — keyboard/mouse injection
