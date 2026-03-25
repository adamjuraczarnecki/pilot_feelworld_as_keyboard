"""
FEELWORLD-05 Diagnose -- full read of both characteristics
Listens to CHAR_1001 and CHAR_1002, shows EVERY change in EVERY byte.
Press buttons and observe what changes.
"""

import asyncio
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from bleak import BleakClient, BleakScanner

_MAC_RE = re.compile(r"([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}")


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


SERVICE_UUID = "00001000-e619-419b-bc43-821e71a409b7"
CHAR_1001 = "00001001-e619-419b-bc43-821e71a409b7"
CHAR_1002 = "00001002-e619-419b-bc43-821e71a409b7"
OUTPUT_FILE = Path("mapping.json")
DEVICE_CACHE = Path("device_mac.txt")

# Buttons to map
# Analog stick covers 4 directions (press separately in each direction)
BUTTONS_TO_MAP = [
    ("OK",           "space",       "Start / Stop"),
    ("Menu",         "f11",         "Full screen"),
    ("Back/On",      "escape",      "Rewind to start"),
    ("A",            "left",        "Slower"),
    ("B",            "right",       "Faster"),
    ("X",            "up",          "Bigger font"),
    ("Y",            "down",        "Smaller font"),
    ("Analog-Up",    "scroll_up",   "Scroll up"),
    ("Analog-Down",  "scroll_down", "Scroll down"),
    ("Analog-Left",  "",            "nothing - skip"),
    ("Analog-Right", "",            "nothing - skip"),
]

AVAILABLE_ACTIONS = ["space", "right", "left", "up", "down", "escape", "f11",
                     "scroll_up", "scroll_down"]


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
        return mac  # fallback to string if something goes wrong


async def _find_by_activity() -> str:
    """Detects remote by BLE activity -- asks user to press a button."""
    print("\nRemote not found automatically.")
    print("Turn the remote OFF (if on), wait 3s, then turn it ON.")
    input("Press Enter when remote is OFF...")

    baseline: set[str] = set()

    def _cb_baseline(device, adv):
        baseline.add(device.address)

    print("Memorising devices in range (3s)...", end="", flush=True)
    async with BleakScanner(_cb_baseline):
        await asyncio.sleep(3)
    print(f"  {len(baseline)} devices.")

    print("\nTurn ON the remote and press any button...")

    found_event = asyncio.Event()
    found_dev: list = []

    def _cb_detect(device, adv):
        if device.address not in baseline and not found_event.is_set():
            found_dev.append(device)  # full BLEDevice with WinRT details
            found_event.set()

    async with BleakScanner(_cb_detect):
        try:
            await asyncio.wait_for(found_event.wait(), timeout=30)
        except asyncio.TimeoutError:
            print("[!] Timeout -- no new device detected. Try again.")
            raise SystemExit(1)

    ble_device = found_dev[0]
    name = ble_device.name or "<no name>"
    print(f"\n>>> New device detected: {name!r}  {ble_device.address}")
    ans = input("Is this your FEELWORLD-05 remote? [Y/n]: ").strip().lower()
    if ans in ("n", "no"):
        print("[!] Cancelled.")
        raise SystemExit(1)

    DEVICE_CACHE.write_text(ble_device.address)
    print(f"Saved: {ble_device.address}")
    return ble_device  # BLEDevice from scanner -- skips scan on next connect()


async def find_device() -> str:
    """Returns BLE address of FEELWORLD-05. Caches result in device_mac.txt."""
    # 1. Cache -- fast path
    if DEVICE_CACHE.exists():
        cached = DEVICE_CACHE.read_text().strip()
        if cached:
            print(f"Checking cache: {cached} ...", end="", flush=True)
            dev = await BleakScanner.find_device_by_address(cached, timeout=5.0)
            if dev is not None:
                print("  [OK] (in range)")
                return dev  # BLEDevice with WinRT details
            print("  not found in scan, trying via WinRT...")
            return _make_ble_device(cached)  # skips scan -- works for connected devices

    # 2. BLE scan + Windows registry
    print("Scanning BLE (5s)...")
    discovered = await BleakScanner.discover(timeout=5.0, return_adv=True)

    for addr, (dev, adv) in discovered.items():
        if SERVICE_UUID in (adv.service_uuids or []):
            print(f"[OK] By service UUID: {dev.name!r}  {addr}")
            DEVICE_CACHE.write_text(addr)
            return dev  # BLEDevice with WinRT details

    for addr, (dev, adv) in discovered.items():
        if dev.name and "feelworld" in dev.name.lower():
            print(f"[OK] By name: {dev.name!r}  {addr}")
            DEVICE_CACHE.write_text(addr)
            return dev  # BLEDevice with WinRT details

    for addr, name in _registry_ble_devices():
        if "feelworld" in name.lower():
            print(f"[OK] From registry: {name!r}  {addr}")
            DEVICE_CACHE.write_text(addr)
            return _make_ble_device(addr, name)  # skips scan -- works for connected devices

    # 3. Activity-based detection -- press a button on the remote
    return await _find_by_activity()


# Cross-platform keyboard input

if sys.platform == "win32":
    import msvcrt as _msvcrt

    def _kbhit() -> bool:
        return bool(_msvcrt.kbhit())

    def _getch() -> str:
        return _msvcrt.getwch()
else:
    import select as _select
    import tty as _tty
    import termios as _termios

    def _kbhit() -> bool:
        return bool(_select.select([sys.stdin], [], [], 0)[0])

    def _getch() -> str:
        fd = sys.stdin.fileno()
        old = _termios.tcgetattr(fd)
        try:
            _tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            _termios.tcsetattr(fd, _termios.TCSADRAIN, old)


# Phase 1: raw preview

async def raw_preview(client: BleakClient):
    """Shows ALL changes from ALL bytes of both chars."""
    print("\n=== Raw preview (Ctrl+C to exit) ===")
    print("Press buttons and observe which bytes change.\n")

    last = {"1001": None, "1002": None}
    uuid_label = {CHAR_1001: "1001", CHAR_1002: "1002"}

    def make_handler(label):
        def handler(characteristic, data: bytearray):
            raw = bytes(data)
            prev = last[label]
            last[label] = raw
            if prev is None or raw == prev:
                return
            hex_new = " ".join(f"{b:02x}" for b in raw)
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] {label}  [{hex_new}]")
            for i, (a, b) in enumerate(zip(prev, raw)):
                if a != b:
                    print(f"         ^ byte[{i}]: {a:02x} -> {b:02x}  "
                          f"(bits: {a:08b} -> {b:08b})")
        return handler

    for uuid, label in uuid_label.items():
        try:
            await client.start_notify(uuid, make_handler(label))
            print(f"  Listening: {uuid}")
        except Exception as e:
            print(f"  [!] No subscription for {uuid}: {e}")
    print()

    try:
        while True:
            await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        for uuid in uuid_label:
            try:
                await client.stop_notify(uuid)
            except Exception:
                pass


# Phase 2: guided mapping

async def guided_mapping(client: BleakClient, mac: str):
    print("\n=== Guided mapping ===")

    # Calibration: establish TRUE resting state
    # Always overwrite -- we want the LAST received state, not the first
    baseline = {"1001": None, "1002": None}

    def make_bl_handler(label):
        def h(characteristic, data: bytearray):
            baseline[label] = bytes(data)
        return h

    for uuid, label in [(CHAR_1001, "1001"), (CHAR_1002, "1002")]:
        try:
            await client.start_notify(uuid, make_bl_handler(label))
        except Exception as e:
            print(f"  [!] {uuid}: {e}")

    print("Calibrating (2s) -- do not press anything...")
    await asyncio.sleep(2)

    # If device sent nothing, force an event
    if baseline.get("1002") is None:
        print("[!] No BLE data -- nudge the analog stick and release...")
        while baseline.get("1002") is None:
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.3)  # wait for state to stabilise

    for uuid in (CHAR_1001, CHAR_1002):
        try:
            await client.stop_notify(uuid)
        except Exception:
            pass
    for label in ("1001", "1002"):
        if baseline[label] is None:
            baseline[label] = bytes(20)

    print(f"  baseline 1002: [{baseline['1002'].hex(' ')}]\n")
    print("Press each button when prompted.  Enter = skip.\n")

    # Subscribe ONCE for the entire mapping session
    loop = asyncio.get_event_loop()
    cur_event = asyncio.Event()
    cur_result = [None]
    record_active = [False]  # whether we are recording a sequence
    recording = []       # all events from the recording phase

    def make_handler(label):
        def handler(characteristic, data: bytearray):
            raw = bytes(data)
            prev = baseline.get(label)
            baseline[label] = raw
            if prev is None or raw == prev:
                return
            # Only process when looking for first detection or recording
            if cur_result[0] is not None and not record_active[0]:
                return
            changes = []
            for i, (a, b) in enumerate(zip(prev, raw)):
                diff_on = (~a) & b & 0xFF   # bits 0->1 (press)
                diff_off = a & (~b) & 0xFF  # bits 1->0 (release)
                for bit in range(8):
                    m = 1 << bit
                    if diff_on & m:
                        changes.append((label, i, bit, m, "press"))
                    if diff_off & m:
                        changes.append((label, i, bit, m, "release"))
                if a != b and not any(c[1] == i for c in changes):
                    changes.append((label, i, -1, b - a, "axis"))
            # First detection -- set cur_result once
            if cur_result[0] is None:
                hit = next((c for c in changes if c[4] == "press"), None) or \
                    (changes[0] if changes else None)
                if hit:
                    cur_result[0] = hit
                    loop.call_soon_threadsafe(cur_event.set)
            # Record full sequence
            if record_active[0]:
                recording.extend(changes)
        return handler

    for uuid, label in [(CHAR_1001, "1001"), (CHAR_1002, "1002")]:
        try:
            await client.start_notify(uuid, make_handler(label))
        except Exception as e:
            print(f"  [!] {uuid}: {e}")

    mapped = []

    try:
        for btn_name, suggested_action, description in BUTTONS_TO_MAP:
            # reset for each button
            cur_result[0] = None
            cur_event.clear()

            hint = f"  [{suggested_action}]" if suggested_action else ""
            print(f"--- [{btn_name}]{hint}  --  {description}")
            print(f"    Press [{btn_name}] on the remote...  (Enter=skip)",
                  end="", flush=True)

            # polling: wait for BLE or Enter
            start = time.time()
            skipped = False
            while not cur_event.is_set():
                if time.time() - start > 10:
                    break
                if _kbhit():
                    k = _getch()
                    if k in ('\r', '\n'):
                        skipped = True
                        break
                    if k == '\x03':
                        raise KeyboardInterrupt
                await asyncio.sleep(0.03)

            if skipped or cur_result[0] is None:
                print("  [skipped]")
                print()
                continue

            # Detected -- print IMMEDIATELY, then record full sequence
            label_c, byte_idx, bit_idx, val, kind = cur_result[0]

            if kind == "axis":
                print(f"\n    >>> DETECTED  char:{label_c}  byte[{byte_idx}]  "
                      f"delta={val:+d}  (analog axis)")
                print(f"    Hold [{btn_name}] for 1.5s more...", end="", flush=True)
                # Collect samples for 1.5s to determine actual direction
                samples = []
                t_end = time.time() + 1.5
                while time.time() < t_end:
                    await asyncio.sleep(0.05)
                    cur = baseline.get(label_c)
                    if cur and byte_idx < len(cur):
                        samples.append(cur[byte_idx] - 128)
                pos_cnt = sum(1 for s in samples if s > 30)
                neg_cnt = sum(1 for s in samples if s < -30)
                if pos_cnt > neg_cnt:
                    direction = 1
                elif neg_cnt > pos_cnt:
                    direction = -1
                else:
                    direction = 1 if val > 0 else -1  # fallback
                arrow = "up (+)" if direction > 0 else "down (-)"
                print(f"  direction: {arrow}  (pos={pos_cnt} neg={neg_cnt} samples)")
                entry = {"button": btn_name, "char": label_c,
                         "type": "axis", "byte": byte_idx,
                         "direction": direction, "action": ""}

            else:
                print(f"\n    >>> DETECTED  char:{label_c}  byte[{byte_idx}]  "
                      f"bit{bit_idx}  mask={val:#04x}")
                print(f"    Hold and RELEASE [{btn_name}] (recording 1.5s)...",
                      end="", flush=True)

                # BLE handler collects events continuously -- no polling
                record_active[0] = True
                recording.clear()
                await asyncio.sleep(1.5)
                record_active[0] = False
                events = list(recording)

                # Count press and release per (label, byte, bit)
                press_cnt = Counter((l, i, b) for l, i, b, m, d in events if d == "press")
                release_cnt = Counter((l, i, b) for l, i, b, m, d in events if d == "release")
                all_keys = sorted(set(press_cnt) | set(release_cnt),
                                  key=lambda k: -(press_cnt.get(k, 0) + release_cnt.get(k, 0)))

                print(f"\n    Recorded {len(events)} events:")
                for l, i, b in all_keys:
                    p = press_cnt.get((l, i, b), 0)
                    r = release_cnt.get((l, i, b), 0)
                    marker = " <<" if (l, i, b) == (label_c, byte_idx, bit_idx) else ""
                    print(f"      char:{l} byte[{i}] bit{b} mask={1<<b:#04x}"
                          f"  press={p}x  release={r}x{marker}")

                # Choose best bit:
                # Releases are always clean (prev=good state), presses can be noisy
                def score(k):
                    r = release_cnt.get(k, 0)
                    p = press_cnt.get(k, 0)
                    if r == 1 and p >= 1:
                        return 0   # ideal: full cycle
                    if r == 1:
                        return 1   # release only
                    if r > 0:
                        return 2   # multiple releases
                    return 3                          # press only (noise)

                chosen = min(all_keys, key=score) if all_keys else (label_c, byte_idx, bit_idx)

                has_release = release_cnt.get(chosen, 0) > 0
                if has_release:
                    print(f"    This bit has PRESS and RELEASE -- you can choose the trigger.")
                print(f"    Chosen bit: char:{chosen[0]} byte[{chosen[1]}] "
                      f"bit{chosen[2]} mask={1<<chosen[2]:#04x}")

                entry = {"button": btn_name, "char": chosen[0], "type": "button",
                         "byte": chosen[1], "bit": chosen[2],
                         "mask": f"{1 << chosen[2]:#04x}", "action": ""}

            # Ask for action
            if suggested_action:
                ans = input(f"    Action [{suggested_action}]?"
                            f"  Enter=yes / other / x=skip: ").strip()
                if ans.lower() == "x":
                    print("    [skipped]\n")
                    continue
                entry["action"] = ans or suggested_action
            else:
                opts = "/".join(AVAILABLE_ACTIONS)
                ans = input(f"    Action ({opts}) or Enter=skip: ").strip()
                if not ans:
                    print("    [skipped]\n")
                    continue
                entry["action"] = ans

            if kind != "axis":
                trig = input(f"    Trigger [P]ress/[R]elease (Enter=press): ").strip().lower()
                entry["trigger"] = "release" if trig.startswith("r") else "press"

            mapped.append(entry)
            print(f"    OK: [{btn_name}] -> {entry['action']!r}  [{entry.get('trigger', 'press')}]\n")

    finally:
        for uuid in (CHAR_1001, CHAR_1002):
            try:
                await client.stop_notify(uuid)
            except Exception:
                pass

    if not mapped:
        print("Nothing mapped.")
        return []

    mac_addr = mac.address if hasattr(mac, "address") else mac
    output = {
        "_info": {"device": mac_addr, "chars": [CHAR_1001, CHAR_1002],
                  "available_actions": AVAILABLE_ACTIONS},
        "buttons": mapped,
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print("=" * 55)
    print(f"Saved {len(mapped)} buttons -> {OUTPUT_FILE}")
    for b in mapped:
        if b["type"] == "axis":
            print(f"  [{b['button']:12s}]  byte[{b['byte']}] axis  ->  {b['action']!r}")
        else:
            print(f"  [{b['button']:12s}]  byte[{b['byte']}] mask={b['mask']}  ->  {b['action']!r}")
    print("\nRun: python controller.py")
    return mapped


# Main

async def main():
    from bleak.exc import BleakDeviceNotFoundError

    mac = await find_device()

    try:
        async with BleakClient(mac) as client:
            print(f"[OK] Connected to {mac}\n")

            print("What do you want to do?")
            print("  1 - Raw preview (see what each button sends)")
            print("  2 - Guided mapping -> mapping.json")
            choice = input("Choice [1/2]: ").strip()

            if choice == "1":
                await raw_preview(client)
            else:
                await guided_mapping(client, mac)

    except BleakDeviceNotFoundError:
        print(f"\n[!] Cannot connect to {mac}")
        print("    Remote is off or out of range.")
        print("    Delete device_mac.txt and run again to re-detect the device.")
        DEVICE_CACHE.unlink(missing_ok=True)
        raise SystemExit(1)


if __name__ == "__main__":
    print("=" * 55)
    print("  FEELWORLD-05  Diagnose")
    print("=" * 55)
    print()
    asyncio.run(main())
