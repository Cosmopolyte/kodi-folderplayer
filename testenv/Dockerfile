FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    kodi kodi-repository-kodi xvfb xauth xdotool procps pulseaudio libgl1-mesa-dri mesa-utils ffmpeg ca-certificates curl python3 \
    fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1500 kodi
USER kodi
WORKDIR /home/kodi
RUN mkdir -p /home/kodi/media /home/kodi/.kodi/userdata /home/kodi/.kodi/addons && \
    ffmpeg -loglevel error -f lavfi -i "sine=frequency=440:duration=20" -c:a libmp3lame /home/kodi/media/01_audio_a.mp3 && \
    ffmpeg -loglevel error -f lavfi -i "testsrc=size=640x360:rate=25:duration=20" -f lavfi -i "sine=frequency=660:duration=20" -c:v libx264 -pix_fmt yuv420p -c:a aac /home/kodi/media/02_video_b.mp4 && \
    ffmpeg -loglevel error -f lavfi -i "sine=frequency=880:duration=20" -c:a flac /home/kodi/media/03_audio_c.flac && \
    ffmpeg -loglevel error -f lavfi -i "smptebars=size=640x360:rate=25:duration=20" -f lavfi -i "sine=frequency=330:duration=20" -c:v libx264 -pix_fmt yuv420p -c:a aac /home/kodi/media/04_video_d.mp4
COPY --chown=kodi:kodi guisettings.xml /home/kodi/.kodi/userdata/guisettings.xml
COPY --chown=kodi:kodi asoundrc /home/kodi/.asoundrc
COPY --chown=kodi:kodi entrypoint.sh /home/kodi/entrypoint.sh
EXPOSE 8080
CMD ["/bin/bash","/home/kodi/entrypoint.sh"]
