"""Which movies are watched, by IMDb id, from every place that knows it.

FanFilm (2023, "ptw") reports playcount in its lists only in Trakt mode. In the
default "local" mode every list says unwatched and the marks live in
script.module.metahandler's database instead, so widgets also read:
- metahandler's video_cache.db (movie_meta.overlay = 7 means watched),
- our own marks (widget context menu, movies played to 85 %+),
- Kodi's video library (movies with playcount > 0),
- Kodi's video database for plugin files (Kodi marks a played plugin item by its
  URL; FanFilm 2026 leaves playcount unset and its window shows Kodi's mark,
  but JSON-RPC lists - what widgets read - do not include it).
"""
import json
import os
import re
import sqlite3
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import xbmc
import xbmcvfs

from . import store

OWN_FILE = os.path.join(store.DATA_DIR, "watched.json")
METAHANDLER_DB = xbmcvfs.translatePath(
    "special://profile/addon_data/script.module.metahandler/meta_cache/video_cache.db")
WATCHED_SHARE = 0.85  # same threshold FanFilm uses during playback
KODI_DB_DIR = xbmcvfs.translatePath("special://database/")
URL_PREFIX = "url:"  # all_ids() also holds "url:<normalized plugin URL>" entries
VOLATILE_PARAMS = {"t"}  # FanFilm 2023 adds a per-listing t=<time>
IMDB_IN_URL = re.compile(r"[?&/]imdb[=/](tt\d+)")


def normalize_url(url):
    """Plugin URL without parameters that change on every listing."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in VOLATILE_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(query)))


def kodi_db_file():
    try:
        names = [n for n in os.listdir(KODI_DB_DIR) if re.fullmatch(r"MyVideos\d+\.db", n)]
    except OSError:
        return None
    if not names:
        return None
    return os.path.join(KODI_DB_DIR, max(names, key=lambda n: int(re.sub(r"\D", "", n))))


def kodi_db_plugin_files():
    """Plugin URLs Kodi itself has marked watched (files.playCount > 0)."""
    path = kodi_db_file()
    if not path:
        return set()
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        try:
            rows = con.execute("SELECT strFilename FROM files WHERE playCount > 0 "
                               "AND strFilename LIKE 'plugin://%'").fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        store.log(f"cannot read Kodi video database: {e}", xbmc.LOGWARNING)
        return set()
    return {str(r[0]) for r in rows}


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
    """Every movie known as watched (without the add-on's own playcount):
    IMDb ids, plus "url:<normalized URL>" for plugin files Kodi marked."""
    ids = set(load_own()) | metahandler_ids() | library_ids()
    for url in kodi_db_plugin_files():
        ids.add(URL_PREFIX + normalize_url(url))
        m = IMDB_IN_URL.search(url)
        if m:
            ids.add(m.group(1))
    return ids


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
