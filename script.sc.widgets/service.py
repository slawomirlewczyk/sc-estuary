"""Reload widgets after playback so "Hide watched movies" drops what was just watched."""
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
    while not monitor.abortRequested():
        if monitor.waitForAbort(2):
            break
        if not monitor.pending or player.isPlaying():
            continue
        # give the source add-on (e.g. FanFilm) time to save the watched mark
        if monitor.waitForAbort(5):
            break
        monitor.pending = False
        if xbmc.getCondVisibility("Skin.HasSetting(sc_hide_watched)"):
            widgets = store.load()
            if widgets:
                store.clear_seen()
                store.sync_skin(widgets)
                store.log("widgets reloaded after playback")


if __name__ == "__main__":
    main()
