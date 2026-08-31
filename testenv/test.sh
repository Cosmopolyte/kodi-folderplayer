#!/bin/bash
# PoC test sequence: run addon, step through mixed playlist, screenshot each state
R=/tmp/kodi-poc/rpc.sh
FOLDER=${1:-/home/kodi/media/}
st() { echo "## $1"; $R GUI.GetProperties '{"properties":["currentwindow","fullscreen"]}'; $R Player.GetItem '{"playerid":1,"properties":["file"]}'; $R Player.GetProperties '{"playerid":1,"properties":["position","time","speed"]}'; }
shot() { $R Input.ExecuteAction '{"action":"screenshot"}' >/dev/null; sleep 2; }
sudo docker exec kodi-poc sh -c 'mkdir -p /home/kodi/shots; rm -f /home/kodi/shots/*.png'
# dismiss "enable add-on?" dialog if present
$R Addons.ExecuteAddon "{\"addonid\":\"script.folderplayer\",\"params\":[\"$FOLDER\"]}" >/dev/null; sleep 4
if $R GUI.GetProperties '{"properties":["currentwindow"]}' | grep -q 'Yes / No'; then
  echo "dismissing enable dialog"; $R Input.Left >/dev/null; sleep 1; $R Input.Select >/dev/null; sleep 4
fi
sleep 4
st "item1 audio"; shot
$R Player.GoTo '{"playerid":1,"to":"next"}' >/dev/null; sleep 8
st "after next -> item2 video"; shot
$R Player.GoTo '{"playerid":1,"to":"next"}' >/dev/null; sleep 6
st "after next -> item3 audio"; shot
echo "## waiting for auto-advance to item4 video"; sleep 17
st "auto-advance -> item4 video"; shot
$R Player.GoTo '{"playerid":1,"to":"previous"}' >/dev/null; sleep 6
st "after previous -> item3 audio"; shot
echo '## LOG'; sudo docker exec kodi-poc grep -E 'folderplayer|EXCEPTION|Non-Existent|Traceback' /home/kodi/.kodi/temp/kodi.log | cut -c1-200 | tail -20
cd /tmp/kodi-poc && rm -f r*.png && for i in 0 1 2 3 4; do sudo docker cp kodi-poc:/home/kodi/shots/screenshot0000$i.png ./r$i.png 2>/dev/null; done; sudo chmod 644 r*.png; ls r*.png
