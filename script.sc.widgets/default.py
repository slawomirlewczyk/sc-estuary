"""Entry point: plugin mode (widget content) or script mode (skin actions)."""
import sys
import traceback

from resources.lib import store

try:
    if len(sys.argv) >= 2 and sys.argv[1].lstrip("-").isdigit():
        # plugin://script.sc.widgets/?w=1 -> argv = [base_url, handle, '?w=1']
        from resources.lib import plugin
        plugin.run(sys.argv)
    else:
        # RunScript(script.sc.widgets,add) -> argv = ['default.py', 'add', ...args]
        store.event(f"action {sys.argv[1:]}")
        from resources.lib import actions
        actions.run(sys.argv[1] if len(sys.argv) > 1 else "manage", sys.argv[2:])
except Exception as e:  # shown in Diagnostics; Kodi's own log keeps the full traceback
    store.event(f"ERROR {type(e).__name__}: {e} | {traceback.format_exc().splitlines()[-3].strip()}")
    raise
