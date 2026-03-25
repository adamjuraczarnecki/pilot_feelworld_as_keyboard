"""
FEELWORLD-05 Controller -> telepromptermirror.com
Cross-platform: Windows + Linux (bleak BLE backend)
"""

import asyncio
import json
import re
import sys
import time
import threading
from pathlib import Path

from bleak import BleakClient, BleakScanner, BleakError


def _registry_ble_devices() -> list[tuple[str, str]]:
    """Reads paired BLE devices from the Windows registry (works for connected devices too)."""
    if sys.platform != "win32":
        return []
    try:
        import winreg
        devices = []
        base = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Enum\BTHLE",
        )
        i = 0
        while True:
            try:
                dev_class = winreg.EnumKey(base, i)
                i += 1
            except OSError:
                break
            m = re.match(r"Dev_([0-9a-fA-F]{12})$", dev_class, re.IGNORECASE)
            if not m:
                continue
            h = m.group(1)
            mac = ":".join(h[j:j + 2] for j in range(0, 12, 2)).upper()
            name = dev_class
            try:
                dev_key = winreg.OpenKey(base, dev_class)
                inst = winreg.EnumKey(dev_key, 0)
                inst_key = winreg.OpenKey(dev_key, inst)
                name = winreg.QueryValueEx(inst_key, "FriendlyName")[0]
            except Exception:
                pass
            devices.append((mac, name))
        return devices
    except Exception:
        return []


from pynput.keyboard import Controller as KB, Key, KeyCode
from pynput.mouse import Controller as Mouse

_kb = KB()
_mouse = Mouse()

SERVICE_UUID = "00001000-e619-419b-bc43-821e71a409b7"
CHAR_1001 = "00001001-e619-419b-bc43-821e71a409b7"
CHAR_1002 = "00001002-e619-419b-bc43-821e71a409b7"
MAPPING_FILE = Path("mapping.json")
DEVICE_CACHE = Path("device_mac.txt")

# Analog axis settings

# Deadzone from center (128) to register intentional movement
AXIS_THRESHOLD = 60    # higher = requires harder push
# Hysteresis: return to center must fall below this threshold
AXIS_RELEASE = 30
# Delay before first send (ms) -- filters accidental touches
AXIS_DEBOUNCE_MS = 180
# Repeat interval while axis is held (ms)
AXIS_REPEAT_MS = 300   # every 300ms = ~3 times per second

# Number of scroll clicks per trigger
SCROLL_AMOUNT = 2


# Key name mapping

_KEY_MAP = {
    "space": Key.space,
    "left": Key.left,
    "right": Key.right,
    "up": Key.up,
    "down": Key.down,
    "escape": Key.esc,
    "f11": Key.f11,
}


def send_key(action: str):
    try:
        if action == "scroll_up":
            _mouse.scroll(0, SCROLL_AMOUNT)
        elif action == "scroll_down":
            _mouse.scroll(0, -SCROLL_AMOUNT)
        else:
            k = _KEY_MAP.get(action)
            if k:
                _kb.tap(k)
            else:
                _kb.tap(KeyCode.from_char(action))
        print(f"  -> {action}", flush=True)
    except Exception as e:
        print(f"  [!] {e}", flush=True)


# Analog axis handler

class AxisState:
    """Single axis state: debounce + repeat."""

    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self.active = False   # whether axis is currently deflected
        self._stop_time = 0.0     # last stop time (for cooldown)

    def start(self, action: str):
        self.stop()
        self._stop.clear()
        self.active = True
        self._thread = threading.Thread(
            target=self._loop, args=(action,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.active = False
        self._stop_time = time.time()

    def in_cooldown(self) -> bool:
        return (time.time() - self._stop_time) * 1000 < AXIS_DEBOUNCE_MS

    def reset_cooldown(self):
        """Axis bounce detected -- extend cooldown from scratch."""
        self._stop_time = time.time()

    def _loop(self, action: str):
        # debounce: wait before first send
        if self._stop.wait(timeout=AXIS_DEBOUNCE_MS / 1000):
            return   # axis returned to center before debounce -- cancel
        # first send
        send_key(action)
        # repeat while axis is held
        while not self._stop.wait(timeout=AXIS_REPEAT_MS / 1000):
            send_key(action)


# Device discovery

def _make_ble_device(mac: str, name: str = ""):
    """BLEDevice that skips scan in BleakClient.connect() -- works for connected devices."""
    try:
        from bleak.backends.device import BLEDevice
        from bleak.backends.winrt.scanner import RawAdvData

        class _Addr:
            def __init__(self, a: int):
                self.bluetooth_address = a

        raw = RawAdvData(adv=_Addr(int(mac.replace(":", ""), 16)), scan=None)
        return BLEDevice(address=mac, name=name, details=raw, rssi=0)
    except Exception:
        return mac


async def find_device() -> str:
    """Returns BLE address of FEELWORLD-05. Caches result in device_mac.txt."""
    # 1. Check cache
    if DEVICE_CACHE.exists():
        cached = DEVICE_CACHE.read_text().strip()
        if cached:
            print(f"Checking cache: {cached} ...", end="", flush=True)
            dev = await BleakScanner.find_device_by_address(cached, timeout=5.0)
            if dev is not None:
                print("  [OK]")
                return dev
            print("  not found in scan, trying via WinRT...")
            return _make_ble_device(cached)

    # 2. Full BLE scan
    print("Scanning BLE (10s)...")
    discovered = await BleakScanner.discover(timeout=10.0, return_adv=True)

    for addr, (dev, adv) in discovered.items():
        if SERVICE_UUID in (adv.service_uuids or []):
            print(f"[OK] By service UUID: {dev.name!r}  {addr}")
            DEVICE_CACHE.write_text(addr)
            return dev

    for addr, (dev, adv) in discovered.items():
        if dev.name and "feelworld" in dev.name.lower():
            print(f"[OK] By name: {dev.name!r}  {addr}")
            DEVICE_CACHE.write_text(addr)
            return dev

    # 3. Windows registry -- paired BLE (including connected, non-advertising)
    for addr, name in _registry_ble_devices():
        if "feelworld" in name.lower():
            print(f"[OK] From registry: {name!r}  {addr}")
            DEVICE_CACHE.write_text(addr)
            return _make_ble_device(addr, name)

    print("[!] FEELWORLD-05 not found.")
    print("    Run: python diagnose.py  -- it will identify and save the remote address.")
    raise SystemExit(1)


# Load mapping

def load_mapping():
    if not MAPPING_FILE.exists():
        print(f"[!] Missing {MAPPING_FILE} -- run: python diagnose.py")
        raise SystemExit(1)
    data = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    buttons = [b for b in data.get("buttons", []) if b.get("action", "").strip()]
    if not buttons:
        print("[!] No actions defined in mapping.json")
        raise SystemExit(1)
    return buttons


# Main loop

async def run(buttons: list[dict]):
    mac = await find_device()

    # button: (char, byte, mask) -> (action, trigger)  trigger: "press"|"release"
    btn_map: dict[tuple[str, int, int], tuple[str, str]] = {}
    # axis:   (char, byte) -> {pos, neg, state}
    axis_map: dict[tuple[str, int], dict] = {}

    for b in buttons:
        char = b.get("char", "1002")
        act = b["action"].strip()
        bname = b.get("button", "").lower()
        if b.get("type") == "axis":
            key = (char, b["byte"])
            if key not in axis_map:
                axis_map[key] = {"pos": "", "neg": "", "state": AxisState()}
            direction = b.get("direction", 0)
            if direction == 0:
                direction = 1 if any(x in bname for x in ("up", "right", "gora", "prawo", "+")) else -1
            if direction > 0:
                axis_map[key]["pos"] = act
            else:
                axis_map[key]["neg"] = act
        else:
            mask = int(b["mask"], 16)
            trigger = b.get("trigger", "press")
            btn_map[(char, b["byte"], mask)] = (act, trigger)

    print("Mapping:")
    for (cl, bi, mask), (act, trig) in btn_map.items():
        print(f"  [{act:12s}]  char:{cl} byte[{bi}] mask={mask:#04x}  [{trig}]")
    for (cl, bi), v in axis_map.items():
        if v["pos"]:
            print(f"  [{v['pos']:12s}]  char:{cl} byte[{bi}] axis+")
        if v["neg"]:
            print(f"  [{v['neg']:12s}]  char:{cl} byte[{bi}] axis-")
    print(f"\nDebounce: {AXIS_DEBOUNCE_MS}ms  Repeat: {AXIS_REPEAT_MS}ms  "
          f"Threshold: {AXIS_THRESHOLD}")
    print("\nClick the browser window and use the remote.")
    print("Press Ctrl+C to stop.\n")

    # Bleak UUID -> label
    uuid_label = {CHAR_1001: "1001", CHAR_1002: "1002"}
    state_last: dict[str, bytes] = {}

    def make_handler(label: str):
        def handler(characteristic, raw: bytearray):
            data = bytes(raw)
            prev = state_last.get(label)
            state_last[label] = data
            if prev is None or data == prev:
                return

            # Buttons
            for i in range(min(len(data), len(prev))):
                pressed = (~prev[i]) & data[i] & 0xFF
                released = prev[i] & (~data[i]) & 0xFF
                for bit in range(8):
                    mask = 1 << bit
                    entry = btn_map.get((label, i, mask))
                    if not entry:
                        continue
                    act, trigger = entry
                    if trigger == "release" and released & mask:
                        send_key(act)
                    elif trigger == "press" and pressed & mask:
                        send_key(act)

            # Axes
            for (cl, byte_idx), v in axis_map.items():
                if cl != label or byte_idx >= len(data):
                    continue
                val = data[byte_idx]
                ax = v["state"]
                delta = val - 128
                if abs(delta) > AXIS_THRESHOLD:
                    action = v["pos"] if delta > 0 else v["neg"]
                    if not action:
                        continue
                    if ax.active:
                        pass
                    elif ax.in_cooldown():
                        ax.reset_cooldown()
                    else:
                        ax.start(action)
                elif abs(delta) < AXIS_RELEASE:
                    if ax.active:
                        ax.stop()
        return handler

    async with BleakClient(mac) as client:
        print(f"[OK] Connected to {mac}\n")
        for uuid, label in uuid_label.items():
            try:
                await client.start_notify(uuid, make_handler(label))
            except Exception as e:
                print(f"  [!] No subscription for {uuid}: {e}")
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            for ax in [v["state"] for v in axis_map.values()]:
                ax.stop()
            for uuid in uuid_label:
                try:
                    await client.stop_notify(uuid)
                except Exception:
                    pass
            print("\nStopped.")


if __name__ == "__main__":
    print("=" * 55)
    print("  FEELWORLD-05  Controller")
    print("=" * 55)
    print()
    asyncio.run(run(load_mapping()))
