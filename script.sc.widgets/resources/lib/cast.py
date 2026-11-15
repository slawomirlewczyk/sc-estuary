"""Cast of widget movies, kept out of the widget lists so tiles draw fast.

The add-on's cast (Files.GetDirectory "cast") is split off the fetched entries
and saved per movie in addon_data/script.sc.widgets/cast/. The Info dialog
loads it only when opened, from its own panel:
    plugin://script.sc.widgets/?cast=<movie key>&tmdb=<id>
A movie the add-on gave no cast for is looked up on TMDb (when a key is set).
"""
import hashlib
import json
import os

import xbmcgui
import xbmcplugin

from . import providers, store

CAST_DIR = os.path.join(store.DATA_DIR, "cast")
MAX_ACTORS = 25


def _file(key):
    return os.path.join(CAST_DIR, hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + ".json")


def _trim(cast):
    result = []
    for i, c in enumerate(cast or []):
        if isinstance(c, dict) and c.get("name"):
            result.append({"name": c["name"], "role": c.get("role") or "",
                           "order": int(c.get("order") if c.get("order") is not None else i),
                           "thumbnail": c.get("thumbnail") or ""})
    return sorted(result, key=lambda c: c["order"])[:MAX_ACTORS]


def load(key):
    try:
        with open(_file(key), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save(key, actors):
    try:
        os.makedirs(CAST_DIR, exist_ok=True)
        if load(key) == actors:
            return
        tmp = _file(key) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(actors, f, ensure_ascii=False)
        os.replace(tmp, _file(key))
    except OSError as e:
        store.log(f"cannot save cast of {key}: {e}")


def split_off(entries, key_of):
    """Remove "cast" from the entries, saving it per movie; returns the entries."""
    for entry in entries:
        actors = _trim(entry.pop("cast", None))
        key = key_of(entry)
        if actors and key and key[:5] in ("imdb:", "tmdb:"):
            save(key, actors)
    return entries


def run(handle, key, tmdb):
    """Plugin listing of a movie's actors for the Info dialog."""
    actors = load(key) if key else None
    if actors is None and store.tmdb_key() and (tmdb or key[:5] in ("imdb:", "tmdb:")):
        try:
            actors = providers.credits(key, tmdb, store.tmdb_key())
            save(key, actors)
        except Exception as e:  # offline / bad key: the dialog just shows no cast
            store.log(f"TMDb cast failed for {key}: {e}")
    for actor in actors or []:
        li = xbmcgui.ListItem(actor["name"], actor.get("role") or "", offscreen=True)
        if actor.get("thumbnail"):
            li.setArt({"thumb": actor["thumbnail"], "icon": actor["thumbnail"]})
        xbmcplugin.addDirectoryItem(handle, f"plugin://{store.ADDON_ID}/?actor", li, False)
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
