# Folder Player — Kodi add-on (`script.folderplayer`)

Play a folder of **mixed audio and video files** as one playlist.

Kodi's own players keep music and music videos apart: a playlist started with an audio file stays in
the audio player, which plays a `.mp4` as sound only. Folder Player treats a folder as one queue —
`.mp3` next to `.mp4` next to `.flac`, in the order you see — and lets Kodi pick the right player
core per file. No library, no scanning, no thumbnails: a plain folder view.

Built for TV remotes (Android/Google TV); mouse and touch work too. Tested on Kodi 21 (Linux,
Windows) and Kodi 22 beta (Android TV). Landscape only — like Kodi itself.

## Features

- Left: the current folder (subfolders, audio ♪, video ▶), right: the video of the running title
  (visualisation/empty for audio), time, seekable progress bar (green on black, couch-readable)
- The playlist is the visible list read top to bottom: subfolders are expanded at their position
  (depth first, each with its own sort mode), then the folder's files; clicking a title starts there
- Transport icons: prev · rewind · play/pause (state-aware) · forward · next · stop;
  fullscreen as a corner icon on the video; fullscreen is kept across titles, Back returns
- **Per-folder sort**: Name / Date / **Shuffle** / **Custom**. Shuffle randomizes the whole tree for
  playback (never stored, list keeps its order). Custom order: move entries by hand — created on the
  first move, auto-saved per folder, reset button next to the sort button
- Custom orders reconcile against reality on every visit: vanished names are dropped, new ones are
  appended alphabetically (a rename is drop + append). Stored data of a folder is only removed when
  its parent folder is readable and the folder is really gone — an unreachable share or unplugged
  drive never deletes anything
- Browse while playing: the header shows what folder is playing, the list highlights the running
  title (or the subfolder containing it)

## Controls

| Input | Action |
|---|---|
| OK on a folder | open it (cursor lands on the first entry) |
| OK on a title | play the list from there |
| Long-press OK on an entry | menu: **Play from here** · **Play only this folder/title** · **Move** |
| Long-press OK elsewhere | cycle sort mode |
| Back | folder up; in the start folder: exit |
| Play/pause media key | pause/resume; when idle: play the highlighted folder/title |
| Skip keys | previous / next title |
| Progress bar | focus it: Left/Right seek 10 s, OK = pause; mouse/touch: click to seek |
| Move mode | Up/Down move the entry, OK saves the custom order, Back cancels |

## Install

1. Kodi → Settings → System → Add-ons → **Unknown sources** on
2. Add-ons → **Install from zip file** → pick `script.folderplayer-<version>.zip`
   (from a local download, USB stick, or a network source you add via *Add network location…*)
3. Add-ons → Program add-ons → **Folder Player** — on first start it asks for your music folder

Settings: start folder, default sort order, optional log-file folder (for troubleshooting; Kodi's
own log is hard to reach on Android TVs — the add-on then writes `folderplayer-<device>.log` there).

Updates: install the newer zip over the old one; settings and custom orders are kept. Add-ons live
in `userdata/addons` and survive Kodi updates.

No sync across devices by design. The **Backup** add-on (robweber) can back up `addon_data`;
porting to another device means copying `userdata/addon_data/script.folderplayer/` over manually.

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

## Layout / ids

`resources/skins/Default/720p/folderplayer.xml` — list 100, videowindow 200, status 300, title 301,
buttons 401 prev, 408 rewind, 407 play/pause, 409 forward, 402 next, 405 stop, 403 sort,
411 reset custom, 404 fullscreen, 406 seek bar, 410 move-mode grab handle.

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
- Never run a CRLF-stripping `sed` over the whole tree — `white.png` starts with `\x89PNG\r\n`.

## About

Developed with AI assistance (Anthropic's Claude, driven and reviewed by a human) for a family of
Google TVs, released in the hope it is useful. MIT license, no warranty. Issues and PRs welcome —
this is a hobby project, response times vary.

## Changelog

- 1.0.1 — proper logo
- 1.0.0 — first public release: first-run folder picker, add-on icon, no private defaults
- 0.3.x — action menu on long-press, per-folder sort incl. shuffle and persistent custom order,
  play starts the highlighted entry, click/tap-to-seek, Windows paths
- 0.2.x — list = playlist incl. subfolders, icon transport buttons, seekable high-contrast bar,
  fullscreen kept across titles, English UI
- 0.1.x — first versions: folder browser, mixed playback, sort by name/date
