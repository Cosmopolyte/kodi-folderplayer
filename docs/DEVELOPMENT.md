# Development notes — Folder Player (`script.folderplayer`)

## Add-on layout

- `script.folderplayer/default.py` — the whole logic (folder reading, playlist, player, custom orders)
- `resources/skins/Default/720p/folderplayer.xml` — the window: list 100, videowindow 200,
  status 300, title 301, buttons 401 prev, 408 rewind, 407 play/pause, 409 forward, 402 next,
  405 stop, 403 sort, 411 reset custom, 404 fullscreen, 406 seek bar, 410 move-mode grab handle
- `resources/skins/Default/media/` — PNG icons (TV fonts render media glyphs unreliably)
- Settings: start folder, default sort order, optional log-file folder (Kodi's own log is hard to
  reach on Android TVs — the add-on then writes `folderplayer-<device>.log` there)

## Behaviour details

- The playlist is the visible list read top to bottom: subfolders are expanded at their position
  (depth first, each with its own sort mode), then the folder's files.
- Shuffle is never stored — the list keeps its order, only playback is randomized.
- Custom orders are created on the first move, auto-saved per folder, and reconcile against reality
  on every visit: vanished names are dropped, new ones are appended alphabetically (a rename is
  drop + append). Stored data of a folder is only removed when its parent folder is readable and
  the folder is really gone — an unreachable share or unplugged drive never deletes anything.
- No sync across devices by design. The **Backup** add-on (robweber) can back up `addon_data`;
  porting to another device means copying `userdata/addon_data/script.folderplayer/` manually.

## Build the zip

```
python3 -c "
import zipfile, os
z = zipfile.ZipFile('script.folderplayer-VERSION.zip', 'w', zipfile.ZIP_DEFLATED)
for r, d, fs in os.walk('script.folderplayer'):
    for f in fs:
        if not f.endswith('.pyc'): z.write(os.path.join(r, f))
z.close()"
```
The zip must contain the top-level folder `script.folderplayer/`.

## Test environment (`testenv/`)

Throw-away Docker container: Debian + Kodi + Xvfb (software GL) + PulseAudio null sink, driven via
JSON-RPC on `127.0.0.1:8090`; screenshots via `Input.ExecuteAction screenshot`, real mouse clicks
via `xdotool` against the Xvfb display. See `testenv/README.md`.

## Known Kodi pitfalls (found while building this)

- Kodi's playlist auto-advance keeps the player core of the first title (audio start = `.mp4` plays
  as sound only) → start every title yourself with `Player.play(path, listitem, windowed=True)`.
- A list reload (`reset()` + `addItems`) triggered from `onAction` leaves the container cursor
  invalid — the next Select is swallowed. Fix: `xbmc.executebuiltin('SetFocus(<id>,<pos>)')`.
- A list reload must not steal the focus back to the list when a button had it.
- `onPlayBackStopped` also fires for your own title switch → guard with a flag.
- Returning from fullscreen fires `onInit` again → keep state behind a guard.
- Controls with `enable` conditions are skipped by remote navigation — never gate navigable controls.
- Add-on skins have no default textures → ship your own `white.png`; `colordiffuse="00000000"` does
  NOT hide a texture (renders opaque) — use an empty texture tag instead.
- TV fonts render media glyphs (◀◀ ▶▶) unreliably → ship PNG icons. ⏮/⏭ (with bar) = prev/next,
  ⏪/⏩ (without) = rewind/ff.
- To capture Up/Down for a move mode, park the focus on an invisible button whose onup/ondown point
  to itself — the list container would otherwise consume the navigation.
- Pointer actions (`ACTION_MOUSE_LEFT_CLICK`, `ACTION_TOUCH_TAP`) carry **window pixels**, not skin
  coordinates — scale by `xbmcgui.getScreenWidth()/Height()` before hit-testing.
- `xbmcvfs.listdir` can return empty lists instead of raising on errors — never treat an empty
  listing as proof that things were deleted.
- Never run a CRLF-stripping `sed` over the whole tree — PNGs start with the bytes `89 50 4E 47 0D 0A`
  (`\x89PNG\r\n`) and get corrupted.
- Kodi caches add-on icons by file URL (Textures db) — replacing the logo under the same filename
  keeps showing the old one in most views; rename the icon file when the artwork changes.
- GitHub guesses a text file's encoding; a single invalid UTF-8 byte (or heavy symbol use) can tip
  the whole page to windows-1252 mojibake — a UTF-8 BOM makes the detection unambiguous.

## Changelog

- 1.0.4 — README split: short user page, developer notes moved here
- 1.0.3 — public home on GitHub (source URL in addon.xml)
- 1.0.2 — icon file renamed (texture cache, see pitfalls)
- 1.0.1 — proper logo
- 1.0.0 — first public release: first-run folder picker, add-on icon, no private defaults
- 0.3.x — action menu on long-press, per-folder sort incl. shuffle and persistent custom order,
  play starts the highlighted entry, click/tap-to-seek, Windows paths
- 0.2.x — list = playlist incl. subfolders, icon transport buttons, seekable high-contrast bar,
  fullscreen kept across titles, English UI
- 0.1.x — first versions: folder browser, mixed playback, sort by name/date
