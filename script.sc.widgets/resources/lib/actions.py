"""Skin actions: RunScript(script.sc.widgets,add|manage|setmax)."""
import xbmc
import xbmcgui

from . import store

L = store.lang


def run(action):
    if action == "add":
        add_current_folder()
    elif action == "setmax":
        set_max()
    elif action == "refresh":
        refresh()
    elif action == "migrate":
        store.load()  # converts SC Estuary 1.0.0 skin strings on first read
    else:
        manage()


def current_folder():
    path = xbmc.getInfoLabel("Container.FolderPath")
    label = (xbmc.getInfoLabel("Container.PluginCategory")
             or xbmc.getInfoLabel("Container.FolderName"))
    return path, label


def describe(widget):
    pages = len(widget["paths"])
    return widget["label"] if pages == 1 else f'{widget["label"]}  [{L(32010).format(pages)}]'


def add_current_folder():
    path, suggested = current_folder()
    if not path.startswith("plugin://"):
        xbmcgui.Dialog().notification(L(32000), L(32011), xbmcgui.NOTIFICATION_WARNING)
        return

    widgets = store.load()
    for w in widgets:
        if path in w["paths"]:
            xbmcgui.Dialog().notification(L(32000), L(32012).format(w["label"]))
            return

    # Ask: new widget, or append this folder (e.g. page 2) to an existing one
    choice = 0
    if widgets:
        options = [L(32013)] + [L(32014).format(describe(w)) for w in widgets]
        choice = xbmcgui.Dialog().select(L(32001), options)
        if choice < 0:
            return

    if choice == 0:
        if len(widgets) >= store.max_widgets():
            xbmcgui.Dialog().ok(L(32000), L(32015).format(store.max_widgets()))
            return
        label = xbmcgui.Dialog().input(L(32016), defaultt=suggested)
        if not label:
            return
        widgets.append({"label": label, "paths": [path]})
        store.save(widgets)
        xbmcgui.Dialog().notification(L(32000), L(32017).format(label))
    else:
        widget = widgets[choice - 1]
        widget["paths"].append(path)
        store.save(widgets)
        xbmcgui.Dialog().notification(L(32000), L(32018).format(widget["label"]))


def manage():
    while True:
        widgets = store.load()
        if not widgets:
            xbmcgui.Dialog().ok(L(32000), L(32019))
            return
        options = [f"[B]{L(32028)}[/B]"] + [describe(w) for w in widgets]
        choice = xbmcgui.Dialog().select(L(32002), options)
        if choice < 0:
            return
        if choice == 0:
            refresh()
            return
        manage_widget(widgets, choice - 1)


def manage_widget(widgets, i):
    widget = widgets[i]
    actions = [("rename", L(32020))]
    if i > 0:
        actions.append(("up", L(32021)))
    if i < len(widgets) - 1:
        actions.append(("down", L(32022)))
    if len(widget["paths"]) > 1:
        actions.append(("droppage", L(32023)))
    actions.append(("delete", L(32024)))

    pick = xbmcgui.Dialog().select(describe(widget), [a[1] for a in actions])
    if pick < 0:
        return
    action = actions[pick][0]

    if action == "rename":
        label = xbmcgui.Dialog().input(L(32016), defaultt=widget["label"])
        if not label:
            return
        widget["label"] = label
    elif action == "up":
        widgets[i - 1], widgets[i] = widgets[i], widgets[i - 1]
    elif action == "down":
        widgets[i + 1], widgets[i] = widgets[i], widgets[i + 1]
    elif action == "droppage":
        widget["paths"].pop()
    elif action == "delete":
        if not xbmcgui.Dialog().yesno(L(32000), L(32025).format(widget["label"])):
            return
        widgets.pop(i)
    store.save(widgets)


def set_max():
    current = str(store.max_widgets())
    value = xbmcgui.Dialog().numeric(0, L(32026).format(store.SLOTS), current)
    if not value:
        return
    number = max(1, min(store.SLOTS, int(value)))
    xbmc.executebuiltin(f"Skin.SetString(sc_max_widgets,{number})")
    widgets = store.load()
    if len(widgets) > number:
        xbmcgui.Dialog().ok(L(32000), L(32027).format(len(widgets), number))


# Add-ons that keep their own list cache, and the plugin call that clears it
CACHE_CLEARERS = {
    "plugin.video.fanfilm": "plugin://plugin.video.fanfilm/?action=clearCache",
}


def refresh():
    """Clear source add-on caches (FanFilm asks to confirm), then reload all widgets."""
    widgets = store.load()
    sources = {p.split("/")[2] for w in widgets for p in w["paths"] if p.startswith("plugin://")}
    monitor = xbmc.Monitor()
    for addon_id, url in CACHE_CLEARERS.items():
        if addon_id in sources and xbmc.getCondVisibility(f"System.AddonIsEnabled({addon_id})"):
            xbmc.executebuiltin(f"RunPlugin({url})")
            _wait_for_confirmation(monitor)
    store.sync_skin(widgets)  # new token in every widget path -> Kodi reloads them
    xbmcgui.Dialog().notification(L(32000), L(32029))


def _wait_for_confirmation(monitor):
    """RunPlugin is async: wait for the add-on's yes/no dialog to open and close."""
    dialog_open = "Window.IsActive(yesnodialog)"
    for _ in range(30):  # up to 3 s for the dialog to show up
        if xbmc.getCondVisibility(dialog_open) or monitor.waitForAbort(0.1):
            break
    while xbmc.getCondVisibility(dialog_open):
        if monitor.waitForAbort(0.2):
            return
    monitor.waitForAbort(1.5)  # let the add-on finish deleting its cache
