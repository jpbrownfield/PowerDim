"""PowerDim entry point."""
import atexit
import ctypes

from powerdim.app import PowerDimApp
from powerdim.controller_window import run_message_loop
from powerdim.logging_setup import configure_logging
from powerdim.tray import run_tray_in_background
from powerdim.win32defs import ERROR_ALREADY_EXISTS, PHANDLER_ROUTINE, WM_QUIT, kernel32, shell32, user32

_MUTEX_NAME = "Global\\PowerDim_SingleInstance_Mutex"
_MB_ICONINFORMATION = 0x40
_APP_USER_MODEL_ID = "PowerDim.App"


def _acquire_single_instance_lock():
    """Two instances both dimming/writing gamma independently would fight each
    other's recovery-file writes and dim calculations. Use a named OS mutex (scoped
    "Global" so it also blocks a second instance in a different RDP/user session on
    the same machine) so only one instance ever runs."""
    handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    already_running = bool(handle) and ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    return handle, already_running


def main() -> None:
    configure_logging()
    shell32.SetCurrentProcessExplicitAppUserModelID(_APP_USER_MODEL_ID)
    mutex_handle, already_running = _acquire_single_instance_lock()
    if already_running:
        user32.MessageBoxW(None, "PowerDim is already running.", "PowerDim", _MB_ICONINFORMATION)
        if mutex_handle:
            kernel32.CloseHandle(mutex_handle)
        return

    app = PowerDimApp()
    # Belt-and-suspenders cleanup: atexit covers normal interpreter exit/uncaught
    # exceptions; the console control handler additionally covers Ctrl+C, console
    # window close, and logoff/shutdown, none of which reliably trigger atexit.
    # shutdown() is idempotent, so multiple paths calling it is harmless.
    atexit.register(app.shutdown)
    console_ctrl_handler = PHANDLER_ROUTINE(lambda _ctrl_type: (app.shutdown(), False)[1])
    kernel32.SetConsoleCtrlHandler(console_ctrl_handler, True)

    main_thread_id = kernel32.GetCurrentThreadId()

    def on_exit():
        # Runs on the tray icon's own thread, not this one -- shutdown() must be
        # called directly here to guarantee dimming is reverted immediately, and
        # PostThreadMessage (not PostQuitMessage, which only targets the *calling*
        # thread's queue) is needed to actually stop run_message_loop() below.
        app.shutdown()
        user32.PostThreadMessageW(main_thread_id, WM_QUIT, 0, 0)

    run_tray_in_background(app, on_exit)
    try:
        run_message_loop()
    finally:
        app.shutdown()
        if mutex_handle:
            kernel32.CloseHandle(mutex_handle)


if __name__ == "__main__":
    main()
