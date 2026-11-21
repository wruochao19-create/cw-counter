"""Bounded automatic CSV history. Explicit exports and diagnostics are separate."""
import re
from pathlib import Path

SESSION_LIMIT=15
SESSION_FILE=re.compile(r'^(\d{8}-\d{6}-\d{6})-(events|summary)\.csv$')
active_logs=set()


def prune_sessions(directory,limit=SESSION_LIMIT):
    if limit<1:raise ValueError('Keep at least one session')
    root=Path(directory).resolve()
    groups={}
    deleted=[]
    try:
        paths=list(root.iterdir())
    except OSError:return deleted
    for path in paths:
        match=SESSION_FILE.fullmatch(path.name)
        if not match:continue
        # Delete only direct regular files inside the resolved session folder.
        # Never follow links, junctions or walk subdirectories.
        if path.is_symlink() or not path.is_file() or path.resolve().parent!=root:continue
        groups.setdefault(match[1],[]).append(path)
    protected={name for name,files in groups.items() if any(p in active_logs for p in files)}
    keep=protected | set(sorted(set(groups)-protected,reverse=True)[:max(0,limit-len(protected))])
    for name in sorted(set(groups)-keep):
        # Windows denies deleting an event log held by another running instance.
        # Try it first, and leave its summary alone if it is still in use.
        for path in sorted(groups[name],key=lambda p:('events.csv' not in p.name,p.name)):
            try:
                path.unlink()
                deleted.append(path)
            except OSError:
                break
    return deleted
