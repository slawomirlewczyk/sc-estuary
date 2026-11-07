"""Reload widgets so "Hide watched movies" drops what was just watched.

Triggers: playback stopped, the video library changed, or coming back to the
home screen from an add-on list (where movies can be marked as watched).
"""
import xbmc

from resources.lib import store


class Monitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.pending = False

    def onNotification(self, sender, method, data):
        if method in ("Player.OnStop", "VideoLibrary.OnUpdate"):
            self.pending = True


def main():
    monitor = Monitor()
    player = xbmc.Player()
    was_in_addon_list = False
    while not monitor.abortRequested():
        if monitor.waitForAbort(1):
            break
        in_addon_list = xbmc.getCondVisibility(
            "Window.IsActive(videos) + !String.IsEmpty(Container.PluginName)")
        if was_in_addon_list and xbmc.getCondVisibility("Window.IsActive(home)"):
            monitor.pending = True  # back on Home after browsing an add-on
        was_in_addon_list = in_addon_list or (was_in_addon_list and
                                              not xbmc.getCondVisibility("Window.IsActive(home)"))
        if not monitor.pending or player.isPlaying():
            continue
        # give the source add-on (e.g. FanFilm) time to save the watched mark
        if monitor.waitForAbort(3):
            break
        monitor.pending = False
        if xbmc.getCondVisibility("Skin.HasSetting(sc_hide_watched)"):
            widgets = store.load()
            if widgets:
                store.clear_seen()
                store.sync_skin(widgets)
                store.log("widgets reloaded (watched marks may have changed)")


if __name__ == "__main__":
    main()
