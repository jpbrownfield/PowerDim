"""PowerDim entry point."""
from powerdim.app import PowerDimApp
from powerdim.controller_window import run_message_loop
from powerdim.tray import run_tray_in_background
from powerdim.win32defs import user32


def main() -> None:
    app = PowerDimApp()

    def on_exit():
        user32.PostQuitMessage(0)

    run_tray_in_background(app, on_exit)
    try:
        run_message_loop()
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
