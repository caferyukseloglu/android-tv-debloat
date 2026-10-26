#!/usr/bin/env python3
"""debloat an Android TV over adb.

Nothing is deleted: packages are disabled for the user, every change is written
to a backup file first, and `restore` undoes it.
"""
import argparse
import datetime
import json
import os
import pathlib
import shlex
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
LISTS = HERE / "lists"
BACKUPS = HERE / "backups"
TIERS = ("safe", "optional")
# Faster UI animations; the old values go into the backup.
TWEAKS = {
    "global/window_animation_scale": "0.5",
    "global/transition_animation_scale": "0.5",
    "global/animator_duration_scale": "0.5",
}


# ---------- adb ----------

def adb(*args):
    try:
        out = subprocess.run(["adb", *args], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        sys.exit("adb not found. Install Android platform-tools and put adb on PATH.")
    except subprocess.TimeoutExpired:
        sys.exit(f"adb {' '.join(args)} timed out; is the TV awake?")
    return (out.stdout + out.stderr).strip()


def sh(cmd):
    return adb("shell", cmd)


def connect(device):
    if device:
        target = device if ":" in device else f"{device}:5555"
        print(adb("connect", target))
        os.environ["ANDROID_SERIAL"] = target
    state = adb("get-state")
    if state != "device":
        sys.exit(f"TV not ready ({state}). Turn on network debugging and accept the prompt on the TV.")


# ---------- parsing (pure, tested) ----------

def parse_packages(text):
    return {line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("package:")}


def parse_rss(ps_text):
    """`ps -A -o RSS,NAME` -> {package: total RSS in KB}, folding `pkg:subprocess` into pkg."""
    rss = {}
    for line in ps_text.splitlines()[1:]:
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            pkg = parts[1].strip().split(":", 1)[0]
            rss[pkg] = rss.get(pkg, 0) + int(parts[0])
    return rss


def parse_kv(text, sep=":"):
    out = {}
    for line in text.splitlines():
        if sep in line:
            k, v = line.split(sep, 1)
            out[k.strip()] = v.strip()
    return out


def kb(value):
    return int(value.split()[0]) if value else 0


def select(entries, tier, only, also=()):
    if only:
        wanted = set(only)
        return [e for e in entries if e["id"] in wanted]
    allowed = TIERS[: TIERS.index(tier) + 1]
    return [e for e in entries if e["tier"] in allowed or e["id"] in set(also)]


# ---------- device ----------

def device_info():
    props = {p: sh(f"getprop {p}") for p in
             ("ro.product.manufacturer", "ro.product.model", "ro.build.version.release")}
    mem = parse_kv(sh("cat /proc/meminfo"))
    vm = parse_kv(sh("cat /proc/vmstat"), sep=" ")
    swapped_mb = (int(vm.get("pswpin", 0)) + int(vm.get("pswpout", 0))) * 4 // 1024
    return {
        "brand": props["ro.product.manufacturer"],
        "model": props["ro.product.model"],
        "android": props["ro.build.version.release"],
        "ram_mb": kb(mem.get("MemTotal")) // 1024,
        "avail_mb": kb(mem.get("MemAvailable")) // 1024,
        "swap_used_mb": (kb(mem.get("SwapTotal")) - kb(mem.get("SwapFree"))) // 1024,
        "swap_io_mb": swapped_mb,
        "uptime": sh("uptime -p 2>/dev/null || uptime"),
    }


def load_list(brand):
    """Generic Android TV list plus the brand's own, e.g. lists/tcl.json."""
    entries = []
    for name in ("android-tv", brand.lower()):
        path = LISTS / f"{name}.json"
        if path.exists():
            entries += json.loads(path.read_text())["packages"]
    return entries


# ---------- commands ----------

def cmd_scan(args):
    info = device_info()
    print(f"\n{info['brand']} {info['model']}  Android {info['android']}  {info['uptime']}")
    print(f"RAM {info['avail_mb']} / {info['ram_mb']} MB free   swap used {info['swap_used_mb']} MB   "
          f"swap traffic since boot {info['swap_io_mb']} MB\n")
    installed = parse_packages(sh("pm list packages"))
    disabled = parse_packages(sh("pm list packages -d"))
    rss = parse_rss(sh("ps -A -o RSS,NAME"))
    entries = [e for e in load_list(info["brand"]) if e["id"] in installed]
    reclaim = {t: 0 for t in TIERS}
    for e in sorted(entries, key=lambda e: (TIERS.index(e["tier"]), e["id"])):
        if e["id"] in disabled:
            state = "off"
        else:
            mb = rss.get(e["id"], 0) // 1024
            state = f"{mb} MB" if mb else "on"
            reclaim[e["tier"]] += mb
        print(f"  {e['tier']:<9}{state:>8}  {e['id']:<48} {e['what']}")
    print(f"\nRunning now: safe {reclaim['safe']} MB, optional {reclaim['optional']} MB")
    print("Next: debloat.py apply            (dry run of the safe tier)")


def cmd_apply(args):
    info = device_info()
    disabled = parse_packages(sh("pm list packages -d"))
    installed = parse_packages(sh("pm list packages"))
    todo = [e for e in select(load_list(info["brand"]), args.tier, args.only, args.also or ())
            if e["id"] in installed and e["id"] not in disabled]
    tweaks = {} if args.no_tweaks else TWEAKS
    # TCL points the screensaver at its Gallery; once that is off, fall back to the system default.
    saver = sh("settings get secure screensaver_components").split("/")[0]
    default_saver = sh("settings get secure screensaver_default_component")
    if saver in disabled | {e["id"] for e in todo} and default_saver != "null":
        tweaks = {**tweaks, "secure/screensaver_components": default_saver}
    for e in todo:
        print(f"  disable  {e['id']:<48} {e['what']}")
    for key, value in tweaks.items():
        print(f"  set      {key} = {value}")
    if not args.yes:
        print(f"\nDry run: {len(todo)} packages. Add --yes to apply.")
        return
    backup = write_backup(info, tweaks)
    for e in todo:
        out = sh(f"pm disable-user --user 0 {e['id']}")
        ok = "disabled-user" in out
        if ok:
            backup["packages"].append(e["id"])
            save(backup)
        print(f"  {'ok  ' if ok else 'FAIL'} {e['id']}" + ("" if ok else f"  ({out})"))
    for key, value in tweaks.items():
        put_setting(key, value)
    print(f"\nBackup: {backup['path']}\nRestart the TV, then run `debloat.py scan` to compare.")


def write_backup(info, tweaks):
    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    settings = {k: sh(f"settings get {k.split('/')[0]} {k.split('/')[1]}") for k in tweaks}
    backup = {"path": str(BACKUPS / f"{serial()}-{stamp}.json"), "device": info["model"],
              "packages": [], "settings": settings}
    save(backup)  # before touching the TV, so a crash mid-way still leaves a restorable file
    return backup


def save(backup):
    pathlib.Path(backup["path"]).write_text(json.dumps(backup, indent=2))


def serial():
    return adb("get-serialno").replace(":", "_")


def put_setting(key, value):
    ns, name = key.split("/")
    sh(f"settings delete {ns} {name}" if value == "null" else f"settings put {ns} {name} {shlex.quote(value)}")


def cmd_restore(args):
    """Replay this TV's backups newest first, so every apply is undone and settings end at their originals."""
    paths = [pathlib.Path(args.backup)] if args.backup else this_tv_backups()
    for path in paths:
        backup = json.loads(path.read_text())
        for pkg in backup["packages"]:
            print(f"  enable   {pkg}  {sh(f'pm enable --user 0 {pkg}')}")
        for key, value in backup["settings"].items():
            put_setting(key, value)
            print(f"  set      {key} = {value}")
        path.rename(path.with_name(path.name + ".restored"))  # never replayed twice
        print(f"Restored {path.name}\n")


def this_tv_backups():
    files = sorted(BACKUPS.glob(f"{serial()}-*.json"), reverse=True)
    if not files:
        sys.exit("No backups for this TV.")
    return files


def main():
    p = argparse.ArgumentParser(description="Debloat an Android TV over adb. Reversible.")
    p.add_argument("-d", "--device", help="TV address, e.g. 192.168.1.80")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", help="show the TV's state and what can be disabled")
    a = sub.add_parser("apply", help="disable packages (dry run unless --yes)")
    a.add_argument("--tier", choices=TIERS, default="safe", help="optional includes safe")
    a.add_argument("--only", nargs="+", metavar="PKG", help="disable just these listed packages")
    a.add_argument("--also", nargs="+", metavar="PKG", help="add these listed packages to the tier")
    a.add_argument("--no-tweaks", action="store_true", help="leave animation speed alone")
    a.add_argument("--yes", action="store_true", help="really apply")
    r = sub.add_parser("restore", help="undo every apply on this TV (or just the given backup file)")
    r.add_argument("backup", nargs="?")
    args = p.parse_args()
    connect(args.device)
    {"scan": cmd_scan, "apply": cmd_apply, "restore": cmd_restore}[args.cmd](args)


if __name__ == "__main__":
    main()
