"""plugin://script.sc.widgets/?w=<n> – lists the items of widget n.

Every path of the widget (e.g. page 1 and page 2 of "Na czasie") is read with
JSON-RPC Files.GetDirectory and the results are joined into one list.
"Next page" tiles are dropped from every page except the last one.
"""
import json
import re
from urllib.parse import parse_qs

import xbmc
import xbmcgui
import xbmcplugin

from . import store

PROPERTIES = [
    "title", "originaltitle", "year", "plot", "plotoutline", "tagline", "rating", "votes",
    "genre", "director", "writer", "studio", "country", "mpaa", "runtime", "premiered",
    "trailer", "imdbnumber", "uniqueid", "playcount", "art", "thumbnail", "fanart", "file",
]
MINIMAL_PROPERTIES = ["title", "art", "thumbnail", "fanart", "file"]
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

    paths = widgets[n - 1]["paths"]
    xbmcplugin.setContent(handle, "movies")
    xbmcplugin.setPluginCategory(handle, widgets[n - 1]["label"])

    seen = set()
    for index, path in enumerate(paths):
        last_page = index == len(paths) - 1
        for entry in get_directory(path):
            if not last_page and is_next_page(entry):
                continue
            url = entry.get("file", "")
            if not url or url in seen:
                continue
            seen.add(url)
            is_folder = entry.get("filetype") == "directory"
            xbmcplugin.addDirectoryItem(handle, url, to_listitem(entry, is_folder), is_folder)

    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)


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


def to_listitem(entry, is_folder):
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
    if entry.get("rating"):
        tag.setRating(float(entry["rating"]), int(entry.get("votes") or 0) if str(entry.get("votes") or "0").isdigit() else 0)
    if entry.get("runtime"):
        tag.setDuration(int(entry["runtime"]))
    if entry.get("playcount"):
        tag.setPlaycount(int(entry["playcount"]))
    if entry.get("uniqueid"):
        tag.setUniqueIDs({k: str(v) for k, v in entry["uniqueid"].items() if v})

    if not is_folder:
        # The source add-on was called from outside its own window, so (like FanFilm)
        # it built playable items; Kodi will ask it to resolve the stream on click.
        li.setProperty("IsPlayable", "true")
    return li
