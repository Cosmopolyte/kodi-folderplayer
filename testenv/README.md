# Test environment — Kodi in a Docker container (saturn)

Debian trixie + `kodi` (Debian package) + Xvfb + Mesa llvmpipe + PulseAudio null sink.
No display, no GPU, no audio hardware — enough for GUI logic, window handling, player core selection.

```
docker build -t kodi-poc .
docker run -d --name kodi-poc -p 127.0.0.1:8090:8080 \
  -v $PWD/../script.folderplayer:/home/kodi/.kodi/addons/script.folderplayer:ro \
  --entrypoint sleep kodi-poc infinity
docker exec -d kodi-poc bash -c 'bash /home/kodi/entrypoint.sh > /home/kodi/console.log 2>&1'
./rpc.sh JSONRPC.Ping
./rpc.sh Addons.SetAddonEnabled '{"addonid":"script.folderplayer","enabled":true}'
./rpc.sh Addons.ExecuteAddon '{"addonid":"script.folderplayer","params":["/home/kodi/media/"]}'
```

- Kodi dies silently as PID 1 under `xvfb-run` → container idles with `sleep infinity`, Kodi via `docker exec -d`.
- ALSA `type null` has no clock (20 s of audio "play" in 1 s) → PulseAudio `module-null-sink`.
- First `ExecuteAddon` pops an "enable add-on?" dialog → `Input.Left` + `Input.Select`.
- Screenshots: `Settings.SetSettingValue debug.screenshotpath` → `Input.ExecuteAction screenshot`.
- JSON-RPC `playerid` follows the playlist type, not the player core — use `Player.GetActivePlayers` (`type`).
- Test media are generated with ffmpeg at build time (`/home/kodi/media`, 2× audio, 2× video, 20 s each).
- `timeline.sh` / `test.sh`: example drive scripts (restart Kodi, run add-on, poll state, screenshot).

Nothing is kept on saturn (container, image and `/tmp/kodi-poc` were removed 2026-09-01) — rebuild on demand
from this directory, ~3–5 min. Note: Debian stable ships Kodi 21.2 and stays there, so this environment tests
GUI/API logic, not new Kodi releases — the canary for a new Kodi version is the TV on the beta channel.
