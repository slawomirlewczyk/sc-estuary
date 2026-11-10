"""Widget list persistence and syncing it to the skin.

Widgets live in addon_data/script.sc.widgets/widgets.json:
    {"widgets": [{"label": "Na czasie", "paths": ["plugin://...", "plugin://...page=2"]}]}

The skin only reads skin strings, so after every change we write, for slot n:
    sc_mw<n>_path  = plugin://script.sc.widgets/?w=<n>&t=<token>   (or reset)
    sc_mw<n>_label = widget label
A new token on each change makes Kodi reload the widget instead of using its cache.
"""
import hashlib
import json
import os
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon("script.sc.widgets")
ADDON_ID = "script.sc.widgets"
SLOTS = 20  # widget rows defined in the skin's Home.xml
DEFAULT_MAX = 20
DATA_DIR = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}/")
DATA_FILE = os.path.join(DATA_DIR, "widgets.json")
CACHE_DIR = os.path.join(DATA_DIR, "cache")  # last list of each widget


def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[{ADDON_ID}] {msg}", level)


EVENTS_FILE = os.path.join(DATA_DIR, "events.log")
EVENTS_KEEP = 80


def event(msg):
    """Log and append to events.log (last EVENTS_KEEP lines), shown in Diagnostics."""
    log(msg)
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            with open(EVENTS_FILE, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
        lines.append(f"{time.strftime('%m-%d %H:%M:%S')} {msg}")
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines[-EVENTS_KEEP:]) + "\n")
    except OSError as e:
        log(f"cannot write {EVENTS_FILE}: {e}", xbmc.LOGWARNING)


def recent_events():
    try:
        with open(EVENTS_FILE, encoding="utf-8") as f:
            return f.read().splitlines()
    except OSError:
        return []


def lang(string_id):
    return ADDON.getLocalizedString(string_id)


def load():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        widgets = [
            {"label": str(w.get("label") or ""), "paths": [str(p) for p in w.get("paths", []) if p]}
            for w in data.get("widgets", [])
        ]
        return [w for w in widgets if w["paths"]]
    except FileNotFoundError:
        return _migrate_v1()
    except (OSError, ValueError) as e:
        log(f"cannot read {DATA_FILE}: {e}", xbmc.LOGERROR)
        return []


def save(widgets):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"widgets": widgets}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DATA_FILE)
    sync_skin(widgets)


def sync_skin(widgets, only=None):
    """Point the skin at the widgets; with only = slot numbers, reload just those."""
    token = str(int(time.time() * 1000))
    for n in range(1, SLOTS + 1):
        if only is not None:
            if n in only and n <= len(widgets):
                xbmc.executebuiltin(f'Skin.SetString(sc_mw{n}_path,"plugin://{ADDON_ID}/?w={n}&t={token}")')
            continue
        if n <= len(widgets):
            path = f"plugin://{ADDON_ID}/?w={n}&t={token}"
            xbmc.executebuiltin(f'Skin.SetString(sc_mw{n}_path,"{path}")')
            xbmc.executebuiltin(f'Skin.SetString(sc_mw{n}_label,"{_esc(widgets[n - 1]["label"])}")')
        else:
            xbmc.executebuiltin(f"Skin.Reset(sc_mw{n}_path)")
            xbmc.executebuiltin(f"Skin.Reset(sc_mw{n}_label)")


def max_widgets():
    raw = xbmc.getInfoLabel("Skin.String(sc_max_widgets)")
    try:
        return max(1, min(SLOTS, int(raw)))
    except ValueError:
        return DEFAULT_MAX


def _esc(text):
    # builtin params are quoted; keep quotes and backslashes from breaking them
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _migrate_v1():
    """SC Estuary 1.0.0 kept up to 3 widgets directly in skin strings."""
    widgets = []
    for n in (1, 2, 3):
        path = xbmc.getInfoLabel(f"Skin.String(sc_movies_widget{n}_path)")
        if path:
            label = xbmc.getInfoLabel(f"Skin.String(sc_movies_widget{n}_label)")
            widgets.append({"label": label, "paths": [path]})
    if widgets:
        log(f"migrated {len(widgets)} widget(s) from SC Estuary 1.0.0")
        save(widgets)
        for n in (1, 2, 3):
            xbmc.executebuiltin(f"Skin.Reset(sc_movies_widget{n}_path)")
            xbmc.executebuiltin(f"Skin.Reset(sc_movies_widget{n}_label)")
    return widgets



def _cache_file(n):
    return os.path.join(CACHE_DIR, f"w{n}.json")


def _paths_sig(paths):
    return hashlib.sha1("\n".join(paths).encode("utf-8")).hexdigest()


def save_entries(n, paths, entries):
    """Save what widget n lists, so it can be drawn instantly next time."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = _cache_file(n) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"sig": _paths_sig(paths), "time": time.time(), "entries": entries}, f)
        os.replace(tmp, _cache_file(n))
    except OSError as e:
        log(f"cannot save widget {n}: {e}", xbmc.LOGWARNING)


def entries_mtime(n):
    try:
        return os.path.getmtime(_cache_file(n))
    except OSError:
        return None


def load_entries(n, paths):
    """(entries, age in seconds) saved for widget n with the same pages, else None."""
    try:
        with open(_cache_file(n), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if data.get("sig") != _paths_sig(paths):
        return None
    return data.get("entries") or [], time.time() - data.get("time", 0)


def clear_cache():
    try:
        for name in os.listdir(CACHE_DIR):
            os.remove(os.path.join(CACHE_DIR, name))
    except OSError:
        pass


REFRESH_PROP = "sc_widgets_refresh"


def request_refresh(numbers, notify=False):
    """Ask the service to re-fetch widgets in the background ("all" or numbers)."""
    win = xbmcgui.Window(10000)
    queued = set(filter(None, win.getProperty(REFRESH_PROP).split(",")))
    queued.update(str(n) for n in numbers)
    if notify:
        queued.add("notify")
    win.setProperty(REFRESH_PROP, ",".join(sorted(queued)))


def take_refresh_requests():
    win = xbmcgui.Window(10000)
    queued = set(filter(None, win.getProperty(REFRESH_PROP).split(",")))
    win.clearProperty(REFRESH_PROP)
    return queued
