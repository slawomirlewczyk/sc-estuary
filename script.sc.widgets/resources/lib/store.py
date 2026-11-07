"""Widget list persistence and syncing it to the skin.

Widgets live in addon_data/script.sc.widgets/widgets.json:
    {"widgets": [{"label": "Na czasie", "paths": ["plugin://...", "plugin://...page=2"]}]}

The skin only reads skin strings, so after every change we write, for slot n:
    sc_mw<n>_path  = plugin://script.sc.widgets/?w=<n>&t=<token>   (or reset)
    sc_mw<n>_label = widget label
A new token on each change makes Kodi reload the widget instead of using its cache.
"""
import json
import os
import time

import xbmc
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon("script.sc.widgets")
ADDON_ID = "script.sc.widgets"
SLOTS = 20  # widget rows defined in the skin's Home.xml
DEFAULT_MAX = 20
DATA_DIR = xbmcvfs.translatePath(f"special://profile/addon_data/{ADDON_ID}/")
DATA_FILE = os.path.join(DATA_DIR, "widgets.json")


def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[{ADDON_ID}] {msg}", level)


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


def sync_skin(widgets):
    token = str(int(time.time() * 1000))
    for n in range(1, SLOTS + 1):
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
