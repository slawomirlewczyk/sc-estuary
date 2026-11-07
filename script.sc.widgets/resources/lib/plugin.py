"""plugin://script.sc.widgets/?w=<n> – lists the items of widget n.

Every path of the widget (e.g. page 1 and page 2 of "Na czasie") is read with
JSON-RPC Files.GetDirectory and the results are joined into one list.
"Next page" tiles are dropped from every page except the last one.
With the skin setting "Hide duplicate movies" a movie already shown by a higher
widget is left out of lower ones; with "Hide watched movies" anything the
source add-on marks as watched (playcount > 0) is left out.

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

from . import ratings, store

PROPERTIES = [
    "title", "originaltitle", "year", "plot", "plotoutline", "tagline", "rating", "votes",
    "genre", "director", "writer", "studio", "country", "mpaa", "runtime", "premiered",
    "trailer", "imdbnumber", "uniqueid", "playcount", "art", "thumbnail", "fanart", "file",
]
MINIMAL_PROPERTIES = ["title", "art", "thumbnail", "fanart", "file", "playcount"]
# FanFilm: "?action=moviePage"; other add-ons usually label it "Next page" / "Następna strona"
NEXT_PAGE_PATH = re.compile(r"action=\w*page\b", re.I)
NEXT_PAGE_LABEL = re.compile(r"nast[eę]pn|next|dalej|>>|»|›", re.I)


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
    rating_data = None
    if xbmc.getCondVisibility("Skin.HasSetting(sc_filmweb_ratings)"):
        rating_data = ratings.load()
        imdbs = [k[5:] for k in map(movie_key, entries) if k and k.startswith("imdb:")]
        if ratings.missing(rating_data, imdbs):
            store.request_refresh(["ratings"])  # looked up in the background

    shown = set()
    skipped = {"watched": 0, "duplicate": 0}
    for entry in entries:
        if hide_watched and entry.get("filetype") != "directory" and int(entry.get("playcount") or 0) > 0:
            skipped["watched"] += 1
            continue
        key = movie_key(entry)
        if key and (key in shown or key in hidden):
            skipped["duplicate"] += 1
            continue
        if key:
            shown.add(key)
        url = entry["file"]
        is_folder = entry.get("filetype") == "directory"
        xbmcplugin.addDirectoryItem(handle, url, to_listitem(entry, is_folder, rating_data), is_folder)

    watched_total = sum(1 for e in entries if int(e.get("playcount") or 0) > 0)
    store.log(f'widget {n} "{widget["label"]}": {len(entries)} items, {watched_total} marked watched '
              f'by the add-on, hidden: {skipped["watched"]} watched, {skipped["duplicate"]} duplicate '
              f'(hide watched={hide_watched}, hide duplicates={bool(hidden) or None})')
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)


def widget_entries(widget):
    """All entries of a widget's pages, "next page" tiles only from the last page."""
    paths = widget["paths"]
    result = []
    for index, path in enumerate(paths):
        last_page = index == len(paths) - 1
        for entry in get_directory(path):
            if not entry.get("file") or (not last_page and is_next_page(entry)):
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
    if entry.get("filetype") == "directory":
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


def is_next_page(entry):
    if entry.get("filetype") != "directory":
        return False
    return bool(NEXT_PAGE_PATH.search(entry.get("file", "")) or
                NEXT_PAGE_LABEL.search(entry.get("label", "")))


def to_listitem(entry, is_folder, rating_data=None):
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
    if entry.get("playcount"):
        tag.setPlaycount(int(entry["playcount"]))
    if entry.get("uniqueid"):
        tag.setUniqueIDs({k: str(v) for k, v in entry["uniqueid"].items() if v})

    if key.startswith("imdb:") and entry.get("file", "").startswith("plugin://plugin.video.fanfilm/"):
        imdb = key[5:]
        watched = int(entry.get("playcount") or 0) > 0
        li.addContextMenuItems([(
            store.lang(32031 if watched else 32030),
            f"RunScript(script.sc.widgets,fanfilm_playcount,{imdb},{6 if watched else 7})",
        )])

    if not is_folder:
        # The source add-on was called from outside its own window, so (like FanFilm)
        # it built playable items; Kodi will ask it to resolve the stream on click.
        li.setProperty("IsPlayable", "true")
    return li
