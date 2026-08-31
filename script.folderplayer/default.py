# -*- coding: utf-8 -*-
"""Folder Player - play a folder of mixed audio/video files as one playlist.

One window: left = entries of the current folder (subfolders + media files),
right = video of the running title (empty/visualisation for audio).
Each title is started explicitly (Player.play per file) so Kodi picks the
right core per file (PAPlayer for audio, VideoPlayer for video) - Kodi's own
playlist auto-advance would keep PAPlayer and play videos as audio only.
"""
import sys
import os
import time
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_VERSION = ADDON.getAddonInfo('version')
PATH = ADDON.getAddonInfo('path')

# control ids (see resources/skins/Default/720p/folderplayer.xml)
C_LIST, C_VIDEO, C_TITLE, C_STATUS = 100, 200, 301, 300
B_PREV, B_NEXT, B_SORT, B_FULL, B_STOP = 401, 402, 403, 404, 405

# Kodi window ids
WIN_FULLSCREEN_VIDEO, WIN_VISUALISATION = 12005, 12006

AUDIO_EXT = ('.mp3', '.flac', '.m4a', '.ogg', '.opus', '.wav', '.aac', '.wma', '.aiff', '.ape', '.wv')
VIDEO_EXT = ('.mp4', '.mkv', '.m4v', '.avi', '.webm', '.mov', '.mpg', '.mpeg', '.ts', '.wmv')
MEDIA_EXT = AUDIO_EXT + VIDEO_EXT

SORT_NAME, SORT_DATE = 'name', 'date'

_logfile = None


def log(msg, level=xbmc.LOGINFO):
    xbmc.log('[%s] %s' % (ADDON_ID, msg), level)
    if _logfile:
        try:
            _logfile.write(('%s %s\n' % (time.strftime('%H:%M:%S'), msg)).encode('utf-8'))
        except Exception:
            pass


def open_logfile(folder):
    """Optional plain-text log on a share (Kodi's own log is not reachable on Android TVs)."""
    global _logfile
    if not folder:
        return
    if not folder.endswith('/'):
        folder += '/'
    host = xbmc.getInfoLabel('System.FriendlyName') or 'kodi'
    host = ''.join(c if c.isalnum() else '-' for c in host).strip('-') or 'kodi'
    path = '%sfolderplayer-%s.log' % (folder, host)
    try:
        _logfile = xbmcvfs.File(path, 'w')
        log('logfile %s (%s %s, Kodi %s)' % (path, ADDON_ID, ADDON_VERSION, xbmc.getInfoLabel('System.BuildVersion')))
    except Exception as e:
        _logfile = None
        xbmc.log('[%s] cannot open logfile %s: %s' % (ADDON_ID, path, e), xbmc.LOGWARNING)


def close_logfile():
    global _logfile
    if _logfile:
        try:
            _logfile.close()
        except Exception:
            pass
        _logfile = None


def join(folder, name):
    if folder.endswith('/') or folder.endswith('\\'):
        return folder + name
    return folder + '/' + name


def fmt_date(ts):
    try:
        return time.strftime('%Y-%m-%d', time.localtime(ts))
    except Exception:
        return ''


class Entry(object):
    __slots__ = ('name', 'path', 'is_dir', 'mtime')

    def __init__(self, name, path, is_dir, mtime=0):
        self.name, self.path, self.is_dir, self.mtime = name, path, is_dir, mtime


def read_folder(folder, sort=SORT_NAME):
    """Return (dirs, files) of a folder as Entry lists, sorted."""
    try:
        dnames, fnames = xbmcvfs.listdir(folder)
    except Exception as e:
        log('listdir failed %s: %s' % (folder, e), xbmc.LOGERROR)
        return [], []
    dirs = [Entry(d, join(folder, d) + '/', True) for d in dnames]
    files = []
    for f in fnames:
        if not f.lower().endswith(MEDIA_EXT):
            continue
        p = join(folder, f)
        mtime = 0
        if sort == SORT_DATE:
            try:
                mtime = xbmcvfs.Stat(p).st_mtime()
            except Exception:
                mtime = 0
        files.append(Entry(f, p, False, mtime))
    dirs.sort(key=lambda e: e.name.lower())
    if sort == SORT_DATE:
        files.sort(key=lambda e: (e.mtime, e.name.lower()))
    else:
        files.sort(key=lambda e: e.name.lower())
    return dirs, files


class Player(xbmc.Player):
    def __init__(self, win):
        super().__init__()
        self.win = win

    def onAVStarted(self):
        self.win.on_started()

    def onPlayBackEnded(self):
        self.win.on_ended()

    def onPlayBackStopped(self):
        if self.win.switching:
            return          # our own play() stopped the previous title
        self.win.stopped_by_user = True
        self.win.on_stopped()

    def onPlayBackError(self):
        log('playback error, skipping', xbmc.LOGWARNING)
        self.win.on_ended()


class Window(xbmcgui.WindowXML):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.start_folder = k.get('folder')
        self.sort = k.get('sort') or SORT_NAME
        self.folder = self.start_folder          # folder shown in the list
        self.dirs, self.files = [], []
        # playback state
        self.player = Player(self)
        self.queue = []                            # Entry list of the playing folder
        self.queue_folder = None
        self.index = -1
        self.my_id = 0
        self.started = False
        self.switching = False
        self.stopped_by_user = False
        self.keep_fullscreen = False               # user chose fullscreen -> keep it across titles

    # ------------------------------------------------------------ lifecycle
    def onInit(self):
        if self.started:
            # window re-shown: Kodi returns here from fullscreen/visualisation,
            # either at the end of a title (keep fullscreen) or because the user pressed Back
            if self.player.isPlaying() and not self.switching and self.keep_fullscreen:
                log('back from fullscreen by user')
                self.keep_fullscreen = False
            self.sync_highlight()
            return
        self.started = True
        self.my_id = xbmcgui.getCurrentWindowId()
        log('window id=%d start=%s sort=%s' % (self.my_id, self.start_folder, self.sort))
        self.load_folder(self.folder)
        self.setFocusId(C_LIST)

    # ------------------------------------------------------------ browsing
    def load_folder(self, folder, select_name=None):
        self.folder = folder
        self.dirs, self.files = read_folder(folder, self.sort)
        log('folder %s: %d dirs, %d files' % (folder, len(self.dirs), len(self.files)))
        lst = self.getControl(C_LIST)
        lst.reset()
        if folder != self.start_folder:
            li = xbmcgui.ListItem('..')
            li.setProperty('kind', 'up')
            lst.addItem(li)
        for e in self.dirs:
            li = xbmcgui.ListItem(e.name)
            li.setProperty('kind', 'dir')
            lst.addItem(li)
        for e in self.files:
            li = xbmcgui.ListItem(e.name)
            li.setProperty('kind', 'video' if e.name.lower().endswith(VIDEO_EXT) else 'audio')
            if self.sort == SORT_DATE and e.mtime:
                li.setLabel2(fmt_date(e.mtime))
            lst.addItem(li)
        self.getControl(C_TITLE).setLabel(self.display_folder(folder))
        self.getControl(B_SORT).setLabel('Sort: %s' % ('Date' if self.sort == SORT_DATE else 'Name'))
        self.sync_highlight()
        sel = 0
        if select_name:
            for i in range(lst.size()):
                if lst.getListItem(i).getLabel() == select_name:
                    sel = i
                    break
        if lst.size():
            # after reset() the container has no valid cursor until it is moved once
            # (reloads triggered from onAction swallowed the next Select) -> set it via builtin
            lst.selectItem(sel)
            xbmc.executebuiltin('SetFocus(%d,%d)' % (C_LIST, sel))
        else:
            self.set_status('Folder is empty or not readable')

    def display_folder(self, folder):
        rel = folder[len(self.start_folder):] if folder.startswith(self.start_folder) else folder
        rel = rel.strip('/')
        root = self.start_folder.rstrip('/').split('/')[-1] or self.start_folder
        return '%s / %s' % (root, rel) if rel else root

    def parent(self, folder):
        f = folder.rstrip('/')
        i = f.rfind('/')
        return f[:i + 1] if i >= 0 else folder

    def go_up(self):
        if self.folder == self.start_folder:
            return False
        child = self.folder.rstrip('/').split('/')[-1]
        self.load_folder(self.parent(self.folder), select_name=child)
        return True

    def toggle_sort(self):
        self.sort = SORT_DATE if self.sort == SORT_NAME else SORT_NAME
        ADDON.setSetting('sort', self.sort)
        self.load_folder(self.folder)

    def entry_at(self, pos):
        """Map list position -> ('up', None) | ('dir', Entry) | ('file', Entry)."""
        off = 0
        if self.folder != self.start_folder:
            if pos == 0:
                return 'up', None
            off = 1
        pos -= off
        if pos < len(self.dirs):
            return 'dir', self.dirs[pos]
        pos -= len(self.dirs)
        if 0 <= pos < len(self.files):
            return 'file', self.files[pos]
        return None, None

    # ------------------------------------------------------------ playback
    def play_folder(self, folder, files, start_index):
        self.queue = list(files)
        self.queue_folder = folder
        self.play_index(start_index)

    def play_index(self, i, natural=False):
        if not self.queue:
            return
        if i < 0:
            i = 0
        if i >= len(self.queue):
            if natural:
                # last title finished on its own
                log('end of folder')
                self.queue, self.index = [], -1
                self.keep_fullscreen = False
                self.sync_highlight()
                self.set_status('End of folder')
            return
        self.index = i
        e = self.queue[i]
        li = xbmcgui.ListItem(e.name)
        log('play %d/%d %s' % (i + 1, len(self.queue), e.name))
        self.stopped_by_user = False
        self.switching = True
        self.player.play(e.path, li, windowed=True)

    def next(self):
        if self.queue:
            self.play_index(self.index + 1)

    def prev(self):
        if self.queue:
            # restart current title if more than 3 s in, else previous title
            try:
                if self.player.isPlaying() and self.player.getTime() > 3:
                    self.player.seekTime(0)
                    return
            except Exception:
                pass
            self.play_index(self.index - 1)

    def go_fullscreen(self):
        if self.player.isPlayingVideo():
            xbmc.executebuiltin('ActivateWindow(%d)' % WIN_FULLSCREEN_VIDEO)
        elif self.player.isPlayingAudio():
            xbmc.executebuiltin('ActivateWindow(%d)' % WIN_VISUALISATION)

    def on_started(self):
        self.switching = False
        kind = 'video' if self.player.isPlayingVideo() else 'audio'
        cur = xbmcgui.getCurrentWindowId()
        log('started %s, window=%d, keep_fullscreen=%s' % (kind, cur, self.keep_fullscreen))
        if self.keep_fullscreen:
            self.go_fullscreen()
        elif self.my_id and cur != self.my_id:
            log('reclaim window: current=%d mine=%d' % (cur, self.my_id))
            xbmc.executebuiltin('ActivateWindow(%d)' % self.my_id)
        self.sync_highlight()

    def on_ended(self):
        if self.stopped_by_user:
            return
        self.play_index(self.index + 1, natural=True)

    def on_stopped(self):
        log('stopped by user')
        self.keep_fullscreen = False
        self.sync_highlight()
        self.set_status('')

    # ------------------------------------------------------------ ui helpers
    def set_status(self, txt):
        try:
            self.getControl(C_STATUS).setLabel(txt)
        except RuntimeError:
            pass

    def sync_highlight(self):
        """Mark the playing title in the list (only if the list shows the playing folder)."""
        try:
            lst = self.getControl(C_LIST)
        except RuntimeError:
            return
        playing = self.queue[self.index] if (self.queue and 0 <= self.index < len(self.queue)) else None
        same = playing is not None and self.folder == self.queue_folder
        for i in range(lst.size()):
            kind, e = self.entry_at(i)
            lst.getListItem(i).select(same and kind == 'file' and e is playing)
        if playing:
            kind = 'Video' if self.player.isPlayingVideo() else 'Audio'
            self.set_status('%d/%d  %s  [%s]' % (self.index + 1, len(self.queue), playing.name, kind))
            self.setProperty('playing_folder', self.display_folder(self.queue_folder))
        else:
            self.setProperty('playing_folder', '')

    # ------------------------------------------------------------ input
    def onClick(self, cid):
        if cid == C_LIST:
            pos = self.getControl(C_LIST).getSelectedPosition()
            kind, e = self.entry_at(pos)
            if kind == 'up':
                self.go_up()
            elif kind == 'dir':
                self.load_folder(e.path)
            elif kind == 'file':
                self.play_folder(self.folder, self.files, self.files.index(e))
        elif cid == B_PREV:
            self.prev()
        elif cid == B_NEXT:
            self.next()
        elif cid == B_SORT:
            self.toggle_sort()
        elif cid == B_FULL:
            if self.player.isPlaying():
                self.keep_fullscreen = True
                self.go_fullscreen()
        elif cid == B_STOP:
            self.stopped_by_user = True
            self.keep_fullscreen = False
            self.player.stop()
            self.queue, self.index = [], -1
            self.sync_highlight()
            self.set_status('')

    def onAction(self, action):
        aid = action.getId()
        if aid in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            if self.go_up():
                return
            # at start folder: close (playback ends with the window)
            log('close')
            self.stopped_by_user = True
            if self.player.isPlaying():
                self.player.stop()
            self.close()
        elif aid == xbmcgui.ACTION_NEXT_ITEM:
            self.next()
        elif aid == xbmcgui.ACTION_PREV_ITEM:
            self.prev()
        elif aid == xbmcgui.ACTION_STOP:
            self.onClick(B_STOP)
        elif aid == xbmcgui.ACTION_CONTEXT_MENU:
            self.toggle_sort()


def main():
    folder = ADDON.getSetting('start_folder') or 'smb://jupiter.vialactea.at/content/pub/Music/'
    sort = ADDON.getSetting('sort') or SORT_NAME
    if len(sys.argv) > 1 and sys.argv[1]:
        folder = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] in (SORT_NAME, SORT_DATE):
        sort = sys.argv[2]
    if not folder.endswith('/'):
        folder += '/'
    open_logfile(ADDON.getSetting('logfolder'))
    log('start folder=%s sort=%s' % (folder, sort))
    win = Window('folderplayer.xml', PATH, 'Default', '720p', folder=folder, sort=sort)
    try:
        win.doModal()
    finally:
        del win
        log('exit')
        close_logfile()


if __name__ == '__main__':
    main()
