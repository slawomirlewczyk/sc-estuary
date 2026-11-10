"""Which movies are watched, by IMDb id, from every place that knows it.

FanFilm (2023, "ptw") reports playcount in its lists only in Trakt mode. In the
default "local" mode every list says unwatched and the marks live in
script.module.metahandler's database instead, so widgets also read:
- metahandler's video_cache.db (movie_meta.overlay = 7 means watched),
- our own marks (widget context menu, movies played to 85 %+),
- Kodi's video library (movies with playcount > 0).
"""
import json
import os
import sqlite3
import time

import xbmc
import xbmcvfs

from . import store

OWN_FILE = os.path.join(store.DATA_DIR, "watched.json")
METAHANDLER_DB = xbmcvfs.translatePath(
    "special://profile/addon_data/script.module.metahandler/meta_cache/video_cache.db")
WATCHED_SHARE = 0.85  # same threshold FanFilm uses during playback


def load_own():
    try:
        with open(OWN_FILE, encoding="utf-8") as f:
            return dict(json.load(f).get("movies") or {})
    except (OSError, ValueError):
        return {}


def mark(imdb, watched=True):
    """Remember (or forget) a movie as watched in our own list."""
    if not str(imdb).startswith("tt"):
        return False
    movies = load_own()
    if watched == (imdb in movies):
        return False
    if watched:
        movies[imdb] = int(time.time())
    else:
        movies.pop(imdb, None)
    try:
        os.makedirs(store.DATA_DIR, exist_ok=True)
        tmp = OWN_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"movies": movies}, f)
        os.replace(tmp, OWN_FILE)
    except OSError as e:
        store.log(f"cannot save {OWN_FILE}: {e}", xbmc.LOGWARNING)
        return False
    store.log(f"{imdb} marked {'watched' if watched else 'unwatched'}")
    return True


def metahandler_ids():
    """Movies FanFilm marked watched locally (metahandler's SQLite cache)."""
    if not os.path.exists(METAHANDLER_DB):
        return set()
    try:
        con = sqlite3.connect(f"file:{METAHANDLER_DB}?mode=ro", uri=True, timeout=2)
        try:
            rows = con.execute("SELECT imdb_id FROM movie_meta WHERE overlay = 7").fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        store.log(f"cannot read metahandler watched marks: {e}", xbmc.LOGWARNING)
        return set()
    return {str(r[0]) for r in rows if str(r[0] or "").startswith("tt")}


def library_ids():
    """Watched movies in Kodi's own video library."""
    request = {
        "jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.GetMovies",
        "params": {"properties": ["uniqueid", "imdbnumber"],
                   "filter": {"field": "playcount", "operator": "greaterthan", "value": "0"}},
    }
    try:
        response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
    except ValueError:
        return set()
    ids = set()
    for movie in (response.get("result") or {}).get("movies") or []:
        imdb = str((movie.get("uniqueid") or {}).get("imdb") or movie.get("imdbnumber") or "")
        if imdb.startswith("tt"):
            ids.add(imdb)
    return ids


def all_ids():
    """IMDb ids of every movie known as watched (without the add-on's own playcount)."""
    return set(load_own()) | metahandler_ids() | library_ids()


class PlaybackTracker:
    """Marks a movie watched in our list once 85 % of it was played.

    FanFilm puts the playing movie's ids in the home window property
    "script.trakt.ids"; the player's info tag is the fallback.
    """

    def __init__(self, player):
        self.player = player
        self.imdb = None
        self.done = False

    def tick(self):
        """Call about once a second; returns True when a movie was just marked."""
        if not self.player.isPlayingVideo():
            self.imdb, self.done = None, False
            return False
        imdb = self._current_imdb()
        if imdb != self.imdb:
            self.imdb, self.done = imdb, False
        if not imdb or self.done:
            return False
        try:
            total = self.player.getTotalTime()
            position = self.player.getTime()
        except RuntimeError:
            return False
        if total > 0 and position / total >= WATCHED_SHARE:
            self.done = True
            return mark(imdb)
        return False

    def _current_imdb(self):
        try:
            ids = json.loads(xbmc.getInfoLabel("Window(10000).Property(script.trakt.ids)") or "{}")
            if str(ids.get("imdb") or "").startswith("tt"):
                return ids["imdb"]
        except (ValueError, AttributeError):
            pass
        try:
            tag = self.player.getVideoInfoTag()
            for imdb in (tag.getUniqueID("imdb"), tag.getIMDBNumber()):
                if str(imdb or "").startswith("tt"):
                    return imdb
        except RuntimeError:
            pass
        return None
