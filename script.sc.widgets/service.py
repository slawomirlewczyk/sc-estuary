"""Background refresh of SC widgets.

Widgets are drawn instantly from their saved lists; this service fetches fresh
lists in the background and reloads the widgets only when something changed.

Refresh triggers:
- a widget drawn from a list older than plugin.STALE_AFTER (asks via a window property),
- "Refresh widgets" and "Mark as watched" actions,
- playback stopped / video library changed,
- coming back to the home screen from an add-on list (movies may be marked there).

A movie played to 85 % is remembered as watched (watched.PlaybackTracker); a
refresh also reloads the widgets when the set of watched movies changed.
"""
import time

import xbmc
import xbmcgui

from resources.lib import plugin, ratings, store, watched

AUTO_MIN_GAP = 30  # seconds between automatic full refreshes
STARTUP_GRACE = 120  # seconds after start without background work (Kodi and add-ons start up)
PAUSE_BETWEEN = 1.0  # seconds between widgets in a refresh, so Kodi stays responsive
WATCHED_PROP = "sc_widgets_watched"  # watched ids the widgets were last drawn with


class Monitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.pending = False

    def onNotification(self, sender, method, data):
        if method in ("Player.OnStop", "VideoLibrary.OnUpdate"):
            self.pending = True


def refresh(numbers, monitor, player):
    """Re-fetch the given widgets ("all" = every widget) one by one, reloading
    each widget that changed; all of them when the watched movies changed."""
    widgets = store.load()
    targets = range(1, len(widgets) + 1) if "all" in numbers else sorted(
        int(n) for n in numbers if n.isdigit() and 1 <= int(n) <= len(widgets))
    started = time.time()
    if watched_changed():
        store.sync_skin(widgets)
    changed = []
    targets = list(targets)
    for i, n in enumerate(targets):
        if monitor.waitForAbort(PAUSE_BETWEEN) or player.isPlaying():
            store.request_refresh(targets[i:])  # finish after playback
            break
        widget = widgets[n - 1]
        fresh = plugin.widget_entries(widget)
        if not fresh:
            continue  # add-on failed or offline: keep showing the saved list
        cached = store.load_entries(n, widget["paths"])
        store.save_entries(n, widget["paths"], fresh)
        if cached is None or plugin.signature(cached[0]) != plugin.signature(fresh):
            changed.append(n)
            # a lower widget hiding duplicates depends on this one: reload those too
            dup = xbmc.getCondVisibility("Skin.HasSetting(sc_hide_duplicates)")
            store.sync_skin(widgets, only=set(range(n, len(widgets) + 1)) if dup else {n})
    store.event(f"background refresh {sorted(numbers)}: changed {changed or 'nothing'}, "
                f"{time.time() - started:.0f} s")
    return bool(changed)


def watched_changed():
    """True when movies were marked (un)watched since the last check."""
    win = xbmcgui.Window(10000)
    now = ",".join(sorted(watched.all_ids(fresh=True)))
    before = win.getProperty(WATCHED_PROP)
    win.setProperty(WATCHED_PROP, now)
    return before != now and bool(before or now)


def update_ratings(monitor, player=None):
    """Filmweb / IMDb ratings for every movie in the saved widget lists."""
    if not xbmc.getCondVisibility("Skin.HasSetting(sc_filmweb_ratings)"):
        return
    widgets = store.load()
    movies = {}
    for n, widget in enumerate(widgets, 1):
        cached = store.load_entries(n, widget["paths"])
        for entry in (cached[0] if cached else []):
            key = plugin.movie_key(entry) or ""
            if key.startswith("imdb:"):
                movies.setdefault(key[5:], {"title": entry.get("title") or entry.get("label"),
                                            "originaltitle": entry.get("originaltitle"),
                                            "year": entry.get("year")})
    if movies and ratings.update(movies, abort=lambda: monitor.abortRequested() or bool(player and player.isPlaying())):
        store.sync_skin(widgets)  # redraw tiles with the new ratings
        store.log(f"ratings updated for {len(movies)} movies")


def main():
    monitor = Monitor()
    player = xbmc.Player()
    tracker = watched.PlaybackTracker(player)
    started = time.time()
    watched_changed()  # remember what the widgets start with
    was_in_addon_list = False
    last_auto = 0.0
    while not monitor.abortRequested():
        if monitor.waitForAbort(1):
            break

        on_home = xbmc.getCondVisibility("Window.IsActive(home)")
        in_addon_list = xbmc.getCondVisibility(
            "Window.IsActive(videos) + !String.IsEmpty(Container.PluginName)")
        if was_in_addon_list and on_home:
            monitor.pending = True  # back on Home after browsing an add-on
        was_in_addon_list = in_addon_list or (was_in_addon_list and not on_home)

        if player.isPlaying():
            tracker.tick()  # widgets reload after Player.OnStop if a movie got marked
            continue
        tracker.tick()

        requests = store.take_refresh_requests()
        if time.time() - started < STARTUP_GRACE and "notify" not in requests:
            if requests:
                store.request_refresh(requests)  # keep them queued until Kodi has settled
            continue
        if monitor.pending and time.time() - last_auto > AUTO_MIN_GAP:
            monitor.pending = False
            if monitor.waitForAbort(2):  # let the add-on save its watched mark
                break
            requests.add("all")
            last_auto = time.time()
        if not requests:
            continue

        notify = "notify" in requests
        want_ratings = "ratings" in requests
        requests -= {"notify", "ratings"}
        if requests:
            refresh(requests, monitor, player)
        if requests or want_ratings:
            update_ratings(monitor, player)
        if notify:
            xbmcgui.Dialog().notification(store.lang(32000), store.lang(32029))


if __name__ == "__main__":
    main()
