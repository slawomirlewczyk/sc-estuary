"""plugin://script.sc.widgets/?w=<n> – lists the items of widget n.

Every path of the widget (e.g. page 1 and page 2 of "Na czasie") is read with
JSON-RPC Files.GetDirectory and the results are joined into one list.
Folders ("next page") are dropped from every page except the last one and
always come after the movies. With "Sort by rating" movies are ordered from the
highest rating (Filmweb, else IMDb, else the add-on's own).
With the skin setting "Hide duplicate movies" a movie already shown by a higher
widget is left out of lower ones; with "Hide watched movies" anything known as
watched is left out: playcount > 0 from the add-on (FanFilm in Trakt mode) or
an IMDb id from watched.all_ids() (FanFilm's local marks, our own, library).

Speed: a widget is drawn at once from the list saved last time; if that list is
older than STALE_AFTER the service fetches a fresh one in the background and
reloads the widgets only when something changed.
"""
import json
import re
from urllib.parse import parse_qs

import xbmc
import xbmcgui
import xbmcplugin

from . import ratings, store, watched

PROPERTIES = [
    "title", "originaltitle", "year", "plot", "plotoutline", "tagline", "rating", "votes",
    "genre", "director", "writer", "studio", "country", "mpaa", "runtime", "premiered",
    "trailer", "imdbnumber", "uniqueid", "playcount", "lastplayed", "resume", "art", "thumbnail", "fanart", "file",
]
MINIMAL_PROPERTIES = ["title", "art", "thumbnail", "fanart", "file", "playcount"]
# FanFilm's "next page" link: "?action=moviePage"
NEXT_PAGE_PATH = re.compile(r"action=\w*page\b", re.I)


def run(argv):
    handle = int(argv[1])
    query = parse_qs(argv[2].lstrip("?"))
    try:
        n = int(query.get("w", ["0"])[0])
    except ValueError:
        n = 0

    widgets = store.load()
    if not 1 <= n <= len(widgets):
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    widget = widgets[n - 1]
    xbmcplugin.setContent(handle, "movies")
    xbmcplugin.setPluginCategory(handle, widget["label"])

    cached = store.load_entries(n, widget["paths"])
    if cached is None:
        entries = widget_entries(widget)  # first time: nothing saved yet, fetch now
        store.save_entries(n, widget["paths"], entries)
    else:
        entries, age = cached
        if age > STALE_AFTER:
            store.request_refresh([n])  # draw now, refresh in the background

    # "Hide duplicate movies": skip anything an earlier (higher) widget already shows
    hidden = set()
    if xbmc.getCondVisibility("Skin.HasSetting(sc_hide_duplicates)"):
        for k in range(1, n):
            hidden.update(seen_keys(k, widgets[k - 1]))

    hide_watched = xbmc.getCondVisibility("Skin.HasSetting(sc_hide_watched)")
    watched_ids = watched.all_ids()
    rating_data = None
    if xbmc.getCondVisibility("Skin.HasSetting(sc_filmweb_ratings)"):
        rating_data = ratings.load()
        imdbs = [k[5:] for k in map(movie_key, entries) if k and k.startswith("imdb:")]
        if ratings.missing(rating_data, imdbs):
            store.request_refresh(["ratings"])  # looked up in the background

    shown = set()
    skipped = {"watched": 0, "duplicate": 0}
    movies, folders = [], []
    for entry in entries:
        if is_folder_entry(entry):
            folders.append(entry)  # e.g. "next page": never between movies, see below
            continue
        if hide_watched and is_watched(entry, watched_ids):
            skipped["watched"] += 1
            continue
        key = movie_key(entry)
        if key and (key in shown or key in hidden):
            skipped["duplicate"] += 1
            continue
        if key:
            shown.add(key)
        movies.append(entry)

    sort_by_rating = xbmc.getCondVisibility("Skin.HasSetting(sc_sort_rating)")
    if sort_by_rating:
        movies.sort(key=lambda e: sort_rating(e, rating_data), reverse=True)  # stable: ties keep order
    # folders go after the movies; a joined widget keeps only the last page's "next page"
    if len(widget["paths"]) > 1:
        folders = folders[-1:]
    for entry in movies + folders:
        is_folder = is_folder_entry(entry)
        li = to_listitem(entry, is_folder, rating_data, not is_folder and is_watched(entry, watched_ids))
        xbmcplugin.addDirectoryItem(handle, entry["file"], li, is_folder)

    by_addon = sum(1 for e in entries if int(e.get("playcount") or 0) > 0)
    watched_total = sum(1 for e in entries if not is_folder_entry(e) and is_watched(e, watched_ids))
    store.event(f'widget {n} "{widget["label"]}": {len(entries)} items, {watched_total} watched '
              f'({by_addon} marked by the add-on), hidden: {skipped["watched"]} watched, {skipped["duplicate"]} duplicate '
              f'(hide watched={hide_watched}, hide duplicates={bool(hidden) or None}, '
              f'sort by rating={sort_by_rating}, folders shown={len(folders)})')
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)


def widget_entries(widget):
    """All entries of a widget's pages, "next page" tiles only from the last page."""
    paths = widget["paths"]
    result = []
    for index, path in enumerate(paths):
        last_page = index == len(paths) - 1
        for entry in get_directory(path):
            # only the last page keeps folders ("next page"); earlier pages give just movies
            if not entry.get("file") or (not last_page and is_folder_entry(entry)):
                continue
            result.append(entry)
    return result


STALE_AFTER = 2 * 60  # seconds before a saved widget list is refreshed in the background


def seen_keys(k, widget):
    """Movie keys of widget k, from its saved list (fetched now if never saved)."""
    cached = store.load_entries(k, widget["paths"])
    if cached is None:
        entries = widget_entries(widget)
        store.save_entries(k, widget["paths"], entries)
    else:
        entries = cached[0]
    return [key for key in map(movie_key, entries) if key]


def signature(entries):
    """What the widget shows; FanFilm play URLs carry a per-call t=, so not the URL."""
    return [(movie_key(e) or e.get("label"), int(e.get("playcount") or 0)) for e in entries]


IMDB_RE = re.compile(r"[?&]imdb=(tt\d+)")
TMDB_RE = re.compile(r"[?&]tmdb=(\d+)")


def movie_key(entry):
    """Identity of a movie across add-on lists; None for folders (e.g. next page)."""
    if is_folder_entry(entry):
        return None
    ids = entry.get("uniqueid") or {}
    imdb = str(ids.get("imdb") or entry.get("imdbnumber") or "")
    if not imdb.startswith("tt"):
        m = IMDB_RE.search(entry.get("file", ""))
        imdb = m.group(1) if m else ""
    if imdb:
        return f"imdb:{imdb}"
    tmdb = str(ids.get("tmdb") or "")
    if not tmdb:
        m = TMDB_RE.search(entry.get("file", ""))
        tmdb = m.group(1) if m else ""
    if tmdb and tmdb != "0":
        return f"tmdb:{tmdb}"
    title = (entry.get("title") or entry.get("label") or "").strip().lower()
    return f"title:{title}|{entry.get('year') or ''}" if title else f"url:{entry['file']}"


def is_watched(entry, watched_ids):
    """Watched per the add-on (playcount) or per watched.all_ids() (by IMDb id)."""
    if int(entry.get("playcount") or 0) > 0:
        return True
    key = movie_key(entry) or ""
    if key.startswith("imdb:") and key[5:] in watched_ids:
        return True
    return bool(entry.get("file")) and watched.URL_PREFIX + watched.normalize_url(entry["file"]) in watched_ids


def get_directory(path):
    for props in (PROPERTIES, MINIMAL_PROPERTIES):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "Files.GetDirectory",
            "params": {"directory": path, "media": "video", "properties": props},
        }
        response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
        if "result" in response:
            return response["result"].get("files") or []
        store.log(f"GetDirectory {path} failed: {response.get('error')}", xbmc.LOGWARNING)
    return []


def is_folder_entry(entry):
    """Folder, or a "next page" link even if reported as a file."""
    return entry.get("filetype") == "directory" or bool(NEXT_PAGE_PATH.search(entry.get("file", "")))


def sort_rating(entry, rating_data=None):
    """Rating used to sort: Filmweb, else IMDb, else the add-on's own; 0 when unknown."""
    key = movie_key(entry) or ""
    if rating_data is not None and key.startswith("imdb:"):
        known = ratings.for_movie(rating_data, key[5:])
        for source in ("filmweb", "imdb"):
            if source in known:
                return known[source][0]
    try:
        return float(entry.get("rating") or 0)
    except (TypeError, ValueError):
        return 0.0


def to_listitem(entry, is_folder, rating_data=None, is_watched_movie=False):
    label = entry.get("label") or entry.get("title") or ""
    li = xbmcgui.ListItem(label, offscreen=True)

    art = dict(entry.get("art") or {})
    if entry.get("thumbnail"):
        art.setdefault("thumb", entry["thumbnail"])
    if entry.get("fanart"):
        art.setdefault("fanart", entry["fanart"])
    if art:
        li.setArt(art)

    tag = li.getVideoInfoTag()
    media_type = entry.get("type")
    tag.setMediaType(media_type if media_type in ("movie", "tvshow", "episode", "season", "musicvideo") else ("" if is_folder else "movie"))
    tag.setTitle(entry.get("title") or label)
    if entry.get("originaltitle"):
        tag.setOriginalTitle(entry["originaltitle"])
    if entry.get("year"):
        tag.setYear(int(entry["year"]))
    for key, setter in (("plot", tag.setPlot), ("plotoutline", tag.setPlotOutline),
                        ("tagline", tag.setTagLine), ("mpaa", tag.setMpaa),
                        ("premiered", tag.setPremiered), ("trailer", tag.setTrailer),
                        ("imdbnumber", tag.setIMDBNumber)):
        if entry.get(key):
            setter(entry[key])
    for key, setter in (("genre", tag.setGenres), ("director", tag.setDirectors),
                        ("writer", tag.setWriters), ("studio", tag.setStudios),
                        ("country", tag.setCountries)):
        value = entry.get(key)
        if value:
            setter(value if isinstance(value, list) else [value])
    votes = str(entry.get("votes") or "0").replace(",", "").replace(" ", "")
    own = (float(entry["rating"]), int(votes) if votes.isdigit() else 0) if entry.get("rating") else None
    extra = {}
    key = movie_key(entry) or ""
    if rating_data is not None and key.startswith("imdb:"):
        extra = ratings.for_movie(rating_data, key[5:])
    if extra:
        # tile shows the default rating: Filmweb, else IMDb; the add-on's (TMDb) stays as extra
        all_ratings = dict(extra)
        if own:
            all_ratings["tmdb"] = own
        tag.setRatings(all_ratings, "filmweb" if "filmweb" in extra else "imdb")
    elif own:
        tag.setRating(own[0], own[1])
    if entry.get("runtime"):
        tag.setDuration(int(entry["runtime"]))
    if is_watched_movie:
        tag.setPlaycount(max(1, int(entry.get("playcount") or 0)))
    if entry.get("uniqueid"):
        tag.setUniqueIDs({k: str(v) for k, v in entry["uniqueid"].items() if v})

    if key.startswith("imdb:") and entry.get("file", "").startswith("plugin://plugin.video.fanfilm/"):
        imdb = key[5:]
        li.addContextMenuItems([(
            store.lang(32031 if is_watched_movie else 32030),
            f"RunScript(script.sc.widgets,fanfilm_playcount,{imdb},{6 if is_watched_movie else 7})",
        )])

    if not is_folder:
        # The source add-on was called from outside its own window, so (like FanFilm)
        # it built playable items; Kodi will ask it to resolve the stream on click.
        li.setProperty("IsPlayable", "true")
    return li
