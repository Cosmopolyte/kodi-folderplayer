# Folder Player — Kodi add-on (`script.folderplayer`)

Play a folder of **mixed audio and video files** as one playlist on Kodi (Android/Google TVs).
Plain folder view, no library, no scanning, no thumbnails.

- Left: entries of the current folder (subfolders, audio ♪, video ▶), current title highlighted
- Right: the video of the running title (empty/visualisation for audio), time, progress
- Transport icons: prev · rewind · play/pause (state-aware) · forward · next · stop; sort button above the list;
  fullscreen as a corner icon on the video
- Remote keys: OK = open folder / play title, Back = folder up (in the start folder: exit),
  long-press OK (context menu) on a folder = play it **including subfolders**, elsewhere = toggle sort,
  media keys (skip next/prev) work if the remote has them
- The playlist is the visible list read top to bottom: subfolders are expanded at their position
  (depth first, each with its own sort mode), then the folder's files; clicking a title starts there
- Sort mode is per folder: Name / Date / Shuffle / Custom (cycle via the sort button or long-press
  OK outside the list). Shuffle randomizes the whole tree for playback, is never stored, and blocks
  reordering; the visible list keeps its underlying order.
- Custom order: long-press OK on an entry -> move mode (Up/Down move, OK saves, Back cancels).
  The order is created on the first move, stored per folder (addon_data/folders.json) and shown as
  "Sort: Custom" with a reset button next to it. On every visit it is reconciled with reality:
  vanished names are dropped, new ones are appended alphabetically (a rename is a drop + append).
  Stored data of a folder is only removed when its PARENT folder is readable and the folder is
  really gone - an unreachable share or unplugged drive never deletes anything.
- No sync across devices by design. The "Backup" add-on (robweber) can back up addon_data; porting
  to another device means copying `userdata/addon_data/script.folderplayer/` over manually.
- Progress bar is focusable (Up from the buttons): Left/Right = seek ±10 s (hold to repeat), OK = pause/resume
- Fullscreen is kept across titles (Kodi's own fullscreen video / music window), Back returns to the add-on
- While playing a folder tree, the list highlights the subfolder that contains the running title

## Why an add-on

Kodi's own playlist auto-advance keeps the player core of the first title: a playlist started with an
audio file stays in PAPlayer, which plays `.mp4` as audio only. Folder Player therefore starts every
title itself (`Player.play(path, listitem, windowed=True)`), so Kodi picks the right core per file,
and draws the video into a `videowindow` control of its own `WindowXML`.

Add-ons live in `userdata/addons` and survive Kodi (Play Store) updates — no patching, no skin fork.
Tested on Kodi 21.2 (Linux) and Kodi 22 beta 1 (Android TV).

## Install / update on a TV

1. Kodi → Settings → System → Add-ons → **Unknown sources** on (once)
2. File manager → Add source → Browse → **Add network location…** (SMB, `jupiter.vialactea.at`, `kodi$`) → name `kodi$` (once)
3. Add-ons → **Install from zip file** → `kodi$` → `addons` → `script.folderplayer-<version>.zip`
4. Add-ons → Program add-ons → Folder Player

Settings (add-on → Configure): start folder (default `smb://jupiter.vialactea.at/content/pub/Music/`),
sort order, optional log-file folder (e.g. `smb://jupiter.vialactea.at/kodi$/` — Kodi's own log is not
reachable on Android TVs; the add-on then writes `folderplayer-<device>.log` there).

## Build the zip

```
cd script.folderplayer/.. && python3 -c "
import zipfile, os
z = zipfile.ZipFile('script.folderplayer-VERSION.zip', 'w', zipfile.ZIP_DEFLATED)
for r, d, fs in os.walk('script.folderplayer'):
    for f in fs: z.write(os.path.join(r, f))
z.close()"
```
The zip must contain the top-level folder `script.folderplayer/`.

## Test environment (`testenv/`)

Throw-away Docker container with Debian + Kodi + Xvfb (software GL) + PulseAudio null sink, driven via
JSON-RPC on `127.0.0.1:8090`; screenshots via `Input.ExecuteAction screenshot`. See `testenv/README.md`.

## Remote control of a TV for testing

Kodi → Settings → Services → Control → *Allow remote control via HTTP*. Then e.g.

```
curl -u user:pw http://<tv>:<port>/jsonrpc -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"Addons.ExecuteAddon","params":{"addonid":"script.folderplayer"}}'
```
`GUI.GetProperties currentwindow` → `13000` = add-on window open. Screenshots are black on Android.

## Layout / ids

`resources/skins/Default/720p/folderplayer.xml` — list 100, videowindow 200, status 300, title 301,
buttons 401 prev, 402 next, 405 stop, 404 fullscreen, 403 sort.

## Known Kodi pitfalls (found while building this)

- List reload (`reset()` + `addItems`) triggered from `onAction` leaves the container cursor invalid —
  the next Select is swallowed. Fix: `xbmc.executebuiltin('SetFocus(100,<pos>)')` after filling.
- `onPlayBackStopped` also fires for our own title switch → `switching` flag, otherwise auto-advance dies.
- Returning from fullscreen fires `onInit` again → `started` guard keeps the state.
- Addon skins have no default textures → ship `white.png`.
- `colordiffuse="00000000"` does NOT hide a texture (renders opaque) — use an empty texture tag instead.
- Controls with `enable` conditions are skipped by remote navigation (see 0.2.6).
- A list reload must not steal the focus back to the list when a button (e.g. sort) had it.
- To capture Up/Down for a move mode, park the focus on an invisible button whose onup/ondown point
  to itself — the list container would otherwise consume the navigation.

## Changelog

- 0.3.0 — per-folder sort modes incl. Shuffle and a persistent Custom order (move mode via long-press,
  auto-reconciled, reset button), local Windows path support (C:\ start folders)
- 0.2.6 — transport buttons no longer use enable-conditions: Kodi skips disabled controls in navigation,
  so rewind/play/forward were unreachable while nothing was playing

- 0.2.5 — rewind/forward buttons (Kodi speed steps 2x/4x/…, play returns to 1x), sort moved above the list,
  fullscreen as corner icon on the video (second button row removed)

- 0.2.4 — icon-only transport buttons (own PNGs — TV fonts render media glyphs unreliably; ⏮/⏭ with bar =
  prev/next, ⏪/⏩ without = rewind/ff), play/pause icon follows the player state, progress bar bright green
  on black in a light frame (readable from the couch)
- 0.2.3 — Play/Pause button (order Prev / Play-Pause / Next / Stop), plain-text labels (glyphs like ◀◀
  render as pause bars on some TV fonts), focused seek bar keeps the progress visible
- 0.2.2 — play order now matches the visible list: subfolders play at their position, before the files
- 0.2.1 — normal playback (OK on a title) now continues into the subfolders after the folder's files
- 0.2.0 — play folder incl. subfolders (long-press OK on a folder, depth first, capped at 2000 titles),
  seekable progress bar (Left/Right ±10 s, OK = pause), list highlights the subfolder of the running title
- 0.1.1 — English UI, button layout (Prev/Next/Stop + Fullscreen/Sort), fullscreen kept across titles, optional log file
- 0.1.0 — first version (folder browser, mixed playback, sort by name/date), tested on WZ-TV (Kodi 22 beta 1)

Ideas: none open right now — generalisation pass for a public release is next.

Note for developers: never run a CRLF-stripping `sed` over the whole tree — `white.png` starts with `\x89PNG\r\n`.
