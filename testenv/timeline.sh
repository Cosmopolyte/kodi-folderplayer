#!/bin/bash
# restart kodi cleanly, run addon, poll state every 3s, screenshot on each item change
R=/tmp/kodi-poc/rpc.sh
FOLDER=${1:-/home/kodi/media/}
DUR=${2:-90}
$R Application.Quit >/dev/null; sleep 6
sudo docker exec kodi-poc pkill -9 -f kodi.bin; sudo docker exec kodi-poc pkill -9 Xvfb; sleep 2
sudo docker exec kodi-poc sh -c 'rm -f /tmp/.X*-lock; mkdir -p /home/kodi/shots; rm -f /home/kodi/shots/*.png'
sudo docker exec -d kodi-poc bash -c 'bash /home/kodi/entrypoint.sh > /home/kodi/console.log 2>&1'
for i in $(seq 1 20); do sleep 3; $R JSONRPC.Ping 2>/dev/null | grep -q pong && break; done; sleep 5
$R Settings.SetSettingValue '{"setting":"debug.screenshotpath","value":"/home/kodi/shots/"}' >/dev/null
$R Addons.ExecuteAddon "{\"addonid\":\"script.folderplayer\",\"params\":[\"$FOLDER\"]}" >/dev/null; sleep 3
if $R GUI.GetProperties '{"properties":["currentwindow"]}' | grep -q 'Yes / No'; then
  echo "dismissing enable dialog"; $R Input.Left >/dev/null; sleep 1; $R Input.Select >/dev/null; sleep 3
fi
LAST=""; N=0
for t in $(seq 3 3 $DUR); do
  sleep 3
  AP=$($R Player.GetActivePlayers)
  PT=$(echo "$AP" | grep -oE '"type":"[a-z]+"' | head -1 | cut -d'"' -f4)
  PID=$(echo "$AP" | grep -oE '"playerid":[0-9]' | head -1 | cut -d: -f2)
  W=$($R GUI.GetProperties '{"properties":["currentwindow"]}' | grep -oE '"id":[0-9]+' | cut -d: -f2)
  IT=""; T=""
  if [ -n "$PID" ]; then
    IT=$($R Player.GetItem "{\"playerid\":$PID,\"properties\":[\"file\"]}" | grep -oE 'media/[^"]*')
    T=$($R Player.GetProperties "{\"playerid\":$PID,\"properties\":[\"time\"]}" | grep -oE '"seconds":[0-9]+' | cut -d: -f2)
  fi
  echo "t=$t core=$PT win=$W item=$IT sec=$T"
  if [ -n "$IT" ] && [ "$IT" != "$LAST" ]; then LAST=$IT; sleep 2; $R Input.ExecuteAction '{"action":"screenshot"}' >/dev/null; echo "   -> screenshot $N ($IT)"; N=$((N+1)); fi
  # exercise next/prev once: at t=12 press next (skip rest of item 1), at t=45 press previous
  if [ $t -eq 12 ]; then echo "   >> Input.ExecuteAction skipnext"; $R Input.ExecuteAction '{"action":"skipnext"}' >/dev/null; fi
  if [ $t -eq 45 ]; then echo "   >> Input.ExecuteAction skipprevious"; $R Input.ExecuteAction '{"action":"skipprevious"}' >/dev/null; fi
done
echo '## LOG'; sudo docker exec kodi-poc grep -E 'folderplayer\]|EXCEPTION|Traceback|VideoPlayer::OpenFile|PAPlayer::PrepareStream' /home/kodi/.kodi/temp/kodi.log | cut -c1-170 | tail -30
cd /tmp/kodi-poc && rm -f r*.png && for f in /home/kodi/shots/screenshot0000?.png; do :; done
i=0; for f in $(sudo docker exec kodi-poc ls /home/kodi/shots/); do sudo docker cp kodi-poc:/home/kodi/shots/$f ./r$i.png; i=$((i+1)); done; sudo chmod 644 r*.png 2>/dev/null; ls r*.png
