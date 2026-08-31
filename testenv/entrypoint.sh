#!/bin/bash
export LIBGL_ALWAYS_SOFTWARE=1
export HOME=/home/kodi
pulseaudio --start --exit-idle-time=-1 --load="module-null-sink sink_name=null" --daemonize=yes 2>/dev/null
sleep 2
echo starting
exec xvfb-run -a -s "-screen 0 1280x720x24 +extension GLX" kodi --standalone --windowing=x11 --logging=console
