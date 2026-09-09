"""Single source of truth for the app's own version.

Patched by CI (build.yml) to the resolved release tag just before building the
exe, so a packaged build knows its own version for update checks. Stays
"0.0.0" when running from source (always considered up to date against any
real release, since update-checking only matters for packaged builds).
"""
__version__ = "0.0.0"
