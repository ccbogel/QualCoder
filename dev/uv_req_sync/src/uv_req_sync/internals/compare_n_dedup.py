"""Dedups the reqs list"""
import re

_NAME_RE = re.compile(r'^\s*([A-Za-z0-9_.\-]+)')

def _mod_name(dep: str) -> str:
    m = _NAME_RE.match(dep)
    if m is None:
        raise ValueError(f"invalid dependency spec: {dep!r}")
    return m.group(1).lower()

def compare_deps(deps: list[str], versionated: list[str]) -> list[str]:
    # start from deps, then overlay any versionated entries that are newer
    by_name: dict[str, str] = {}
    for d in deps:
        by_name[_mod_name(d)] = d          # deps first
    for v in versionated:
        by_name[_mod_name(v)] = v          # newer wins
    
    return sorted(by_name.values())