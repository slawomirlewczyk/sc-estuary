"""Diagnostics: what every watched-status source reports, shown and written to the log.

Manage widgets > Diagnostics, or RunScript(script.sc.widgets,diagnose).
Also saved to addon_data/script.sc.widgets/diagnostics.txt.
"""
import os
import time

import xbmc
import xbmcaddon
import xbmcgui

from . import plugin, store, watched

SAMPLE = 12  # movies listed per widget


def run():
    lines = []
    add = lines.append
    add(f"script.sc.widgets {store.ADDON.getAddonInfo('version')}, "
        f"skin {xbmc.getSkinDir()}, Kodi {xbmc.getInfoLabel('System.BuildVersion')}")
    add(f"hide watched={xbmc.getCondVisibility('Skin.HasSetting(sc_hide_watched)')}, "
        f"hide duplicates={xbmc.getCondVisibility('Skin.HasSetting(sc_hide_duplicates)')}")
    try:
        ff = xbmcaddon.Addon("plugin.video.fanfilm")
        settings = {k: ff.getSetting(k) for k in ("indicators", "indicators.alt", "trakt.scrobble")}
        add(f"FanFilm {ff.getAddonInfo('version')}, trakt user set={bool(ff.getSetting('trakt.user'))}, {settings}")
    except RuntimeError:
        add("FanFilm: not installed")

    own = watched.load_own()
    meta = watched.metahandler_ids()
    lib = watched.library_ids()
    kodi_files = {watched.normalize_url(u) for u in watched.kodi_db_plugin_files()}
    add(f"metahandler db exists={os.path.exists(watched.METAHANDLER_DB)}, watched there={len(meta)}")
    add(f"own marks={len(own)}, Kodi library watched={len(lib)}")
    add(f"Kodi video db {watched.kodi_db_file()}: watched plugin files={len(kodi_files)}")
    add(f"own marks file: {watched.OWN_FILE} exists={os.path.exists(watched.OWN_FILE)}, "
        f"data dir writable={os.access(store.DATA_DIR, os.W_OK)}")
    ids = watched.all_ids()
    events = store.recent_events()
    add("")
    add(f"== last events ({len(events)})")
    lines.extend("  " + e for e in events[-25:])

    for n, widget in enumerate(store.load(), 1):
        add("")
        add(f'== widget {n} "{widget["label"]}" ({len(widget["paths"])} page(s))')
        cached = store.load_entries(n, widget["paths"])
        if cached:
            add(f"saved list: {len(cached[0])} items, {int(cached[1])} s old, "
                f"playcount>0: {sum(1 for e in cached[0] if int(e.get('playcount') or 0) > 0)}")
        started = time.time()
        fresh = plugin.widget_entries(widget)
        movies = [e for e in fresh if not plugin.is_folder_entry(e)]
        add(f"fetched now: {len(fresh)} items in {time.time() - started:.1f} s, "
            f"playcount>0: {sum(1 for e in movies if int(e.get('playcount') or 0) > 0)}, "
            f"watched by any source: {sum(1 for e in movies if plugin.is_watched(e, ids))}")
        for e in movies[:SAMPLE]:
            key = plugin.movie_key(e) or "-"
            imdb = key[5:] if key.startswith("imdb:") else ""
            where = [name for name, s in (("own", own), ("meta", meta), ("lib", lib)) if imdb in s]
            if watched.normalize_url(e.get("file", "")) in kodi_files:
                where.append("kodidb")
            add(f"  {(e.get('title') or e.get('label') or '')[:30]:30} {key:16} "
                f"playcount={e.get('playcount')} lastplayed={e.get('lastplayed') or '-'} "
                f"resume={(e.get('resume') or {}).get('position', '-')} in={','.join(where) or '-'}")
        if movies:
            add(f"  first file: {movies[0].get('file', '')[:160]}")

    text = "\n".join(lines)
    store.log("diagnostics:\n" + text)
    try:
        with open(os.path.join(store.DATA_DIR, "diagnostics.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    xbmcgui.Dialog().textviewer(store.lang(32033), text, usemono=True)
