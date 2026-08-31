# Folder Player — Kodi add-on (`script.folderplayer`)

Play a folder of **mixed audio and video files** as one playlist on Kodi (Android/Google TVs).
Plain folder view, no library, no scanning, no thumbnails.

- Left: entries of the current folder (subfolders, audio ♪, video ▶), current title highlighted
- Right: the video of the running title (empty/visualisation for audio), time, progress
- Buttons: Previous · Next · Stop / Fullscreen · Sort (name / modification date)
- Remote keys: OK = open folder / play title, Back = folder up (in the start folder: exit),
  long-press OK (context menu) on a folder = play it **including subfolders**, elsewhere = toggle sort,
  media keys (skip next/prev) work if the remote has them
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

## Changelog

- 0.2.0 — play folder incl. subfolders (long-press OK on a folder, depth first, capped at 2000 titles),
  seekable progress bar (Left/Right ±10 s, OK = pause), list highlights the subfolder of the running title
- 0.1.1 — English UI, button layout (Prev/Next/Stop + Fullscreen/Sort), fullscreen kept across titles, optional log file
- 0.1.0 — first version (folder browser, mixed playback, sort by name/date), tested on WZ-TV (Kodi 22 beta 1)

Ideas: custom per-folder order (move titles, persisted in addon_data, sort cycle name/date/custom).

Note for developers: never run a CRLF-stripping `sed` over the whole tree — `white.png` starts with `\x89PNG\r\n`.
