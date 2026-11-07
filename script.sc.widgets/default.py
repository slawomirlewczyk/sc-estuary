"""Entry point: plugin mode (widget content) or script mode (skin actions)."""
import sys

from resources.lib import actions, plugin

if len(sys.argv) >= 2 and sys.argv[1].lstrip("-").isdigit():
    # plugin://script.sc.widgets/?w=1 -> argv = [base_url, handle, '?w=1']
    plugin.run(sys.argv)
else:
    # RunScript(script.sc.widgets,add) -> argv = ['default.py', 'add']
    actions.run(sys.argv[1] if len(sys.argv) > 1 else "manage")
