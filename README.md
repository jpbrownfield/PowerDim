# PowerDim

A lightweight Windows system-tray utility for dimming your screen(s) below what
Windows' own brightness slider allows — useful for OLED monitors/TVs at night,
reducing eye strain or when the windows brightness changing features aren't natively available.

PowerDim runs entirely from the tray.

## How dimming works

PowerDim can dim a display two different ways, chosen per monitor:

- **Overlay Mode** (default): a click-through, always-on-top black window is
  placed over each monitor and its transparency is adjusted to darken
  everything beneath it. Works on every display, but a handful of things (the
  Windows right-click context menu, the mouse cursor itself, and some fullscreen
  exclusive games) render on top of any window and can't be covered, so they still appear bright.

- **Gamma Mode**: dims by rewriting the display's actual output curve instead of
  drawing a window over it — either the legacy gamma ramp (`SetDeviceGammaRamp`)
  for SDR displays, or the "SDR content brightness" value for HDR-enabled
  displays. Nothing can render on top of a dimmer physical signal, so this
  covers context menus and the cursor too. Not every monitor/driver supports a
  real gamma-ramp write, though (virtual/RDP displays, some HDMI-connected TVs,
  etc.) — PowerDim automatically probes each monitor on startup and only offers
  Gamma Mode for the ones that actually work.

You can pick a mode per session from the tray. If you choose Gamma Mode and
some of your monitors don't support it, PowerDim automatically falls back to
the overlay for just those monitors instead of leaving them undimmed — the
tray menu will show this as a split state (see below).

### Per-monitor list

The top of the tray menu lists every detected monitor as `N: <name>`, where `N`
is a small re-ranked index (1, 2, 3, ...) based on the monitor's Windows display
number — gaps from a since-unplugged monitor won't show as confusing
non-consecutive numbers. Unchecking a monitor here excludes it from dimming
entirely (it's always left at normal brightness). Monitors that can't do a real
gamma-ramp write are labeled `(No Gamma Control)`.

### Dimming mode indicator

"Overlay Mode" / "Gamma Mode" behave like a normal radio choice — a checkmark
shows whichever one is actually driving every monitor. If your monitors are
split (e.g. Gamma Mode selected, but only some monitors support it), both
items show a dot instead of a checkmark and are annotated with which monitors
are in which mode, e.g. `Gamma Mode (Monitor 1)` / `Overlay Mode (Monitor 2)`.

### Automatic fallback on flicker

Some VRR/adaptive-sync displays flicker when a black overlay window is placed
over fullscreen content (a DWM mode-switch side effect). PowerDim watches for this
and can automatically switch to Gamma Mode when it detects flicker, for a
configurable duration ("Use Gamma Mode when Z-Fighting is Detected for..." in the
tray: 15 min / 30 min / 1 hour / 2 hours / indefinitely / never). This only
applies while Overlay Mode is your selected mode, and only if at least one
monitor supports Gamma Mode.

## Brightness control

- Tray menu: pick a preset (100%, 90%, 80%, ... down to 20%). 100% is labeled
  "Disabled" and fully restores normal brightness on every monitor (including
  disabled ones), so it also doubles as a reset if anything ever looks stuck.
  It leaves the OLED VRR Black Flicker Tool's shadow lift untouched, since
  that's independent of brightness and only toggled from its own menu.
- Global hotkeys (work anywhere, not just when the tray menu is open). None
  are configured by default — set up your own from Tray → **Configure
  Hotkeys...**: Brightness Up, Brightness Down, Reset to 100%, and "Set
  Brightness To..." (jumps straight to a chosen percentage, and jumps back to
  100% if you press it again while already at that value).

## OLED VRR Black Flicker Tool

A separate feature from the automatic flicker fallback above: on some OLED
displays, near-black content flickers under VRR. This tool raises the
near-black end of the gamma curve slightly ("shadow lift") to avoid it. It
requires an actual gamma-ramp-capable monitor (not the HDR SDR-white-level
path, since that's a single scalar with no per-level curve to shape) and is
only shown in the tray if at least one monitor supports it.

- **Active** — toggle it on/off.
- **Configure...** — opens a small dialog to choose intensity: Low (15%),
  Medium (30%), or High (50%).

## Schedule

Set up automatic brightness changes at specific times of day:

- Tray → **Schedule → Edit Schedule...** opens an editor window. Add entries
  with a time (12-hour, 15-minute increments), a target brightness, and an
  enabled checkbox. Changes autosave immediately — there's no separate save
  button.
- Tray → **Schedule → Enabled** toggles whether the schedule is applied at all
  without deleting your entries.
- Entries are stored in `%LOCALAPPDATA%\PowerDim\schedule.json`.

## Run on Startup

Tray → **Run on Startup** adds/removes PowerDim from your current user's
startup programs (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`) — no
administrator rights required, and it only affects your own account.

## Other tray items

- **Check for Updates...** — checks the latest GitHub release and, if it's
  newer than the running build, asks to confirm before downloading and
  installing it. Only runs when clicked (never automatically/in the
  background). Only works from the built `.exe`, not when running from
  source. See "Updating" below for how this actually applies the update.
- **Exit** — quits PowerDim, restoring every monitor to normal brightness
  first.

## Updating

"Check for Updates..." downloads the latest release's `.exe`, verifies its
SHA-256 checksum (and, once configured, its Authenticode signer certificate)
before touching anything, then hands off to a small generated `.bat` script
that waits for PowerDim to exit, swaps the new `.exe` into place, and
restarts it — a running `.exe` can't overwrite its own file directly, so this
is the standard way self-updating Windows apps handle it. This requires the
folder PowerDim is installed in to be writable by your user account (true for
most non-`Program Files` locations).

The update is checksum-verified but only *optionally* signature-pinned right
now (see `EXPECTED_SIGNER_THUMBPRINT` in `powerdim/updater.py`) — the release
workflow signs builds with a self-signed certificate if you've configured
`CODESIGN_PFX_BASE64`/`CODESIGN_PASSWORD` secrets (see
`scripts/generate_codesign_cert.ps1`), but a self-signed cert does **not**
give you a "trusted publisher" checkmark or bypass SmartScreen — its only
purpose here is letting the updater confirm a downloaded build was signed
with the exact same key as your other releases, as one more integrity check
alongside the checksum.

If you fork this repo, update checking won't work against your fork until you
change `GITHUB_REPO` in `powerdim/updater.py` to your own `user/repo`,
generate your own cert via `scripts/generate_codesign_cert.ps1`, set your
fork's own `CODESIGN_PFX_BASE64`/`CODESIGN_PASSWORD` secrets (these aren't
inherited from the upstream repo), and swap in the new thumbprint.

## Requirements

- Windows 10/11
- Python 3.14 (only needed if running from source; not needed for the built
  `.exe`)

## Running from source

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Running the test suite

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

## Building the executable

PowerDim is built as a single-file Windows executable via PyInstaller:

```powershell
pip install pyinstaller
pyinstaller --onefile --noconsole --name PowerDim --icon assets/icon.ico main.py
```

The `.github/workflows/build.yml` GitHub Actions workflow does this
automatically on every push and publishes a GitHub Release with the built
`PowerDim.exe` (plus a `PowerDim.exe.sha256` checksum file) attached. Pushing
to a branch auto-bumps the patch version (`vX.Y.Z`); to set an explicit
version instead, include `@x.y.z` anywhere in your commit message (e.g.
`Fix flicker bug @2.5.0`). The resolved version is written into
`powerdim/version.py` before building, which is what "Check for Updates"
compares against.

## Logs

PowerDim writes a rotating log file to `%LOCALAPPDATA%\PowerDim\powerdim.log`
(capped at ~1&nbsp;MB × 3 backups) — check here first if something isn't
behaving as expected.

## Notes and limitations

- Only one instance of PowerDim can run at a time (enforced via a named OS
  mutex); launching a second copy just shows a notice and exits.
- Overlay Mode cannot cover the mouse cursor or the Windows right-click context
  menu — both are rendered by the OS above any application window. Gamma Mode
  is the only way to dim these, and only on monitors that support it.
- Gamma-ramp writes are a legacy SDR mechanism, so many HDR-enabled displays
  (especially TVs) either bypass them entirely or accept the call but ignore
  it. PowerDim verifies this per monitor at startup rather than assuming
  success, and uses the HDR "SDR content brightness" control instead where
  HDR is on — but that path only dims SDR content composited into the HDR
  signal, not native HDR content.
