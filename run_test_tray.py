"""Manual smoke-test entry point: run the full app with a console attached and
without the single-instance mutex, so you can iterate on tray/schedule/overlay
behavior without building the PyInstaller exe first.

Usage:
    .venv\\Scripts\\python.exe run_test_tray.py

Differences from main.py:
  * No mutex check -- lets you run this alongside a real installed instance.
  * Keeps a console window so print()s and tracebacks are visible (the built
    exe runs with --noconsole).
"""
import atexit

from powerdim.app import PowerDimApp
from powerdim.controller_window import run_message_loop
from powerdim.logging_setup import configure_logging
from powerdim.tray import run_tray_in_background
from powerdim.win32defs import PHANDLER_ROUTINE, WM_QUIT, kernel32, shell32, user32

_APP_USER_MODEL_ID = "PowerDim.App"


def main() -> None:
    configure_logging()
    shell32.SetCurrentProcessExplicitAppUserModelID(_APP_USER_MODEL_ID)
    print("PowerDim test run starting. Right-click the tray icon to exercise the menu.")
    app = PowerDimApp()
    atexit.register(app.shutdown)
    console_ctrl_handler = PHANDLER_ROUTINE(lambda _ctrl_type: (app.shutdown(), False)[1])
    kernel32.SetConsoleCtrlHandler(console_ctrl_handler, True)

    main_thread_id = kernel32.GetCurrentThreadId()

    def on_exit():
        # Runs on the tray icon's own thread -- shutdown() must be called directly
        # here, and PostThreadMessage (not PostQuitMessage) targets this thread's
        # queue specifically so run_message_loop() below actually wakes up.
        print("Exit clicked, shutting down.")
        app.shutdown()
        user32.PostThreadMessageW(main_thread_id, WM_QUIT, 0, 0)

    run_tray_in_background(app, on_exit)
    try:
        run_message_loop()
    finally:
        app.shutdown()
        print("PowerDim test run stopped.")


if __name__ == "__main__":
    main()
