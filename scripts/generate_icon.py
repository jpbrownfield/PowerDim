"""One-off script to regenerate assets/icon.ico from the shared icon artwork
(powerdim/app_icon.py). Run manually whenever the icon design changes:

    .venv\\Scripts\\python.exe scripts/generate_icon.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from powerdim.app_icon import make_icon_image

_SIZES = [16, 24, 32, 48, 64, 128, 256]


def main() -> None:
    out_path = pathlib.Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base = make_icon_image(256)
    base.save(out_path, sizes=[(size, size) for size in _SIZES])
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
