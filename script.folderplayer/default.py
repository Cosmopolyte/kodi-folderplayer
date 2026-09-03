# -*- coding: utf-8 -*-
"""Folder Player - play a folder of mixed audio/video files as one playlist.

One window: left = entries of the current folder (subfolders + media files),
right = video of the running title (empty/visualisation for audio).
Each title is started explicitly (Player.play per file) so Kodi picks the
right core per file (PAPlayer for audio, VideoPlayer for video) - Kodi's own
playlist auto-advance would keep PAPlayer and play videos as audio only.

The playlist is the visible list read top to bottom: subfolders are expanded
at their position (each with its own sort mode), then the folder's files.

Sort modes are stored per folder (name / date / custom); shuffle is transient.
A custom order is created by moving a title (long-press OK on an entry) and
reconciled against reality on every visit: missing entries are dropped, new
ones are appended alphabetically. A folder's stored data is only removed when
its parent folder is readable and the folder is really gone - an unreachable
share never deletes anything.
"""
import json
import os
import random
import sys
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
B_PREV, B_NEXT, B_SORT, B_FULL, B_STOP, B_SEEK, B_PLAY, B_RW, B_FF = 401, 402, 403, 404, 405, 406, 407, 408, 409
B_MOVEGRAB, B_RESET = 410, 411

# Kodi window ids
WIN_FULLSCREEN_VIDEO, WIN_VISUALISATION = 12005, 12006

# seek bar geometry in skin coordinates (see folderplayer.xml, control 406)
SEEK_X, SEEK_Y, SEEK_W, SEEK_H = 614, 490, 648, 34   # a little taller for fat fingers

AUDIO_EXT = ('.mp3', '.flac', '.m4a', '.ogg', '.opus', '.wav', '.aac', '.wma', '.aiff', '.ape', '.wv')
VIDEO_EXT = ('.mp4', '.mkv', '.m4v', '.avi', '.webm', '.mov', '.mpg', '.mpeg', '.ts', '.wmv')
MEDIA_EXT = AUDIO_EXT + VIDEO_EXT

SORT_NAME, SORT_DATE, SORT_SHUFFLE, SORT_CUSTOM = 'name', 'date', 'shuffle', 'custom'
SORT_LABELS = {SORT_NAME: 'Name', SORT_DATE: 'Date', SORT_SHUFFLE: 'Shuffle', SORT_CUSTOM: 'Custom'}

SEEK_STEP = 10          # seconds per left/right press on the progress bar
MAX_RECURSIVE = 2000    # safety cap for recursive queues

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
    if not folder.endswith(('/', '\\')):
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


# ---------------------------------------------------------------- paths
# smb:// and other VFS paths use '/', local Windows start folders use '\'
def sep_of(path):
    return '\\' if ('\\' in path and '/' not in path) else '/'


def join(folder, name):
    if folder.endswith('/') or folder.endswith('\\'):
        return folder + name
    return folder + sep_of(folder) + name


def parent_of(folder):
    f = folder.rstrip('/\\')
    i = max(f.rfind('/'), f.rfind('\\'))
    return f[:i + 1] if i >= 0 else folder


def leaf_of(folder):
    return folder.rstrip('/\\').replace('\\', '/').split('/')[-1]


def fmt_date(ts):
    try:
        return time.strftime('%Y-%m-%d', time.localtime(ts))
    except Exception:
        return ''


class Entry(object):
    __slots__ = ('name', 'path', 'is_dir', 'mtime')

    def __init__(self, name, path, is_dir, mtime=0):
        self.name, self.path, self.is_dir, self.mtime = name, path, is_dir, mtime

    def key(self):
        # order entries are stored by name; folders carry a trailing '/'
        return self.name + '/' if self.is_dir else self.name


# ---------------------------------------------------------------- store
class Store(object):
    """Per-folder sort mode + custom order, JSON in the addon profile."""

    def __init__(self):
        profile = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
        if not xbmcvfs.exists(profile):
            xbmcvfs.mkdirs(profile)
        self.path = os.path.join(profile, 'folders.json')
        self.data = {}
        try:
            if xbmcvfs.exists(self.path):
                f = xbmcvfs.File(self.path)
                raw = f.read()
                f.close()
                loaded = json.loads(raw)
                if isinstance(loaded, dict) and loaded.get('version') == 1:
                    self.data = loaded.get('folders', {})
        except Exception as e:
            log('store load failed: %s' % e, xbmc.LOGWARNING)

    def save(self):
        try:
            f = xbmcvfs.File(self.path, 'w')
            f.write(json.dumps({'version': 1, 'folders': self.data}, ensure_ascii=False, indent=1))
            f.close()
        except Exception as e:
            log('store save failed: %s' % e, xbmc.LOGWARNING)

    @staticmethod
    def key(folder):
        return folder.rstrip('/\\')

    def entry(self, folder):
        return self.data.get(self.key(folder))

    def get_mode(self, folder):
        e = self.entry(folder)
        return e.get('mode') if e else None

    def get_order(self, folder):
        e = self.entry(folder)
        return list(e.get('order', [])) or None if e else None

    def set(self, folder, mode=None, order=None):
        k = self.key(folder)
        e = self.data.setdefault(k, {})
        if mode is not None:
            e['mode'] = mode
        if order is not None:
            e['order'] = order
        self.save()

    def delete_order(self, folder):
        k = self.key(folder)
        e = self.data.get(k)
        if not e:
            return
        e.pop('order', None)
        if e.get('mode') == SORT_CUSTOM:
            e.pop('mode', None)
        if not e:
            self.data.pop(k, None)
        self.save()

    def gc_children(self, folder, existing_dirnames):
        """The parent was just listed successfully -> stored entries for direct
        child folders that no longer exist are really gone (rule: an unreachable
        share deletes nothing, because then the listing itself fails)."""
        base = self.key(folder)
        sep = sep_of(folder)
        removed = False
        for k in list(self.data.keys()):
            if not k.startswith(base + sep):
                continue
            rest = k[len(base) + 1:]
            child = rest.replace('\\', '/').split('/')[0]
            if child not in existing_dirnames:
                log('gc: stored folder gone, dropping %s' % k)
                self.data.pop(k, None)
                removed = True
        if removed:
            self.save()


# ---------------------------------------------------------------- player
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


# ---------------------------------------------------------------- window
class Window(xbmcgui.WindowXML):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.start_folder = k.get('folder')
        self.default_sort = k.get('sort') or SORT_NAME
        self.store = Store()
        self.shuffled = set()                     # folders whose ACTIVE mode is shuffle (transient)
        self.folder = self.start_folder           # folder shown in the list
        self.entries = []                         # display order (dirs + files mixed for custom)
        # playback state
        self.player = Player(self)
        self.queue = []
        self.queue_folder = None
        self.index = -1
        self.my_id = 0
        self.started = False
        self.switching = False
        self.stopped_by_user = False
        self.keep_fullscreen = False
        # move mode state
        self.moving_pos = -1                      # position in self.entries, -1 = off
        self.entries_backup = None

    # ------------------------------------------------------------ modes
    def mode_of(self, folder):
        """Active sort mode of a folder (shuffle is transient, never stored)."""
        if self.store.key(folder) in self.shuffled:
            return SORT_SHUFFLE
        stored = self.store.get_mode(folder)
        if stored == SORT_CUSTOM and not self.store.get_order(folder):
            stored = None
        return stored or self.default_sort

    def display_mode_of(self, folder):
        """Mode used for the visible list: shuffle shows the underlying order."""
        m = self.mode_of(folder)
        if m == SORT_SHUFFLE:
            stored = self.store.get_mode(folder)
            if stored == SORT_CUSTOM and not self.store.get_order(folder):
                stored = None
            return stored or self.default_sort
        return m

    def cycle_mode(self):
        folder = self.folder
        modes = [SORT_NAME, SORT_DATE, SORT_SHUFFLE]
        if self.store.get_order(folder):
            modes.append(SORT_CUSTOM)
        cur = self.mode_of(folder)
        nxt = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else SORT_NAME
        self.shuffled.discard(self.store.key(folder))
        if nxt == SORT_SHUFFLE:
            self.shuffled.add(self.store.key(folder))
        else:
            self.store.set(folder, mode=nxt)
        log('sort %s -> %s (%s)' % (cur, nxt, folder))
        self.load_folder(folder, keep_selection=True)

    # ------------------------------------------------------------ reading
    def read_entries(self, folder, for_display=True):
        """Entries of one folder in its display order. Applies the stored custom
        order (dropping vanished names, appending new ones) and lazily GCs
        stored data of child folders that are really gone."""
        mode = self.display_mode_of(folder)
        try:
            dnames, fnames = xbmcvfs.listdir(folder)
        except Exception as e:
            log('listdir failed %s: %s' % (folder, e), xbmc.LOGERROR)
            return None
        if dnames or fnames:
            # only GC when the listing really returned content: xbmcvfs.listdir can
            # return empty lists instead of raising on some errors, and an error
            # must never delete stored orders (rule: unreachable deletes nothing)
            self.store.gc_children(folder, set(dnames))
        need_date = mode == SORT_DATE
        dirs = [Entry(d, join(folder, d) + sep_of(folder), True) for d in dnames]
        files = []
        for f in fnames:
            if not f.lower().endswith(MEDIA_EXT):
                continue
            p = join(folder, f)
            mtime = 0
            if need_date:
                try:
                    mtime = xbmcvfs.Stat(p).st_mtime()
                except Exception:
                    mtime = 0
            files.append(Entry(f, p, False, mtime))
        dirs.sort(key=lambda e: e.name.lower())
        if mode == SORT_DATE:
            files.sort(key=lambda e: (e.mtime, e.name.lower()))
        else:
            files.sort(key=lambda e: e.name.lower())
        entries = dirs + files
        if mode == SORT_CUSTOM:
            order = self.store.get_order(folder) or []
            by_key = {e.key(): e for e in entries}
            ordered = [by_key.pop(k) for k in order if k in by_key]
            fresh_dirs = [e for e in by_key.values() if e.is_dir]
            fresh_files = [e for e in by_key.values() if not e.is_dir]
            fresh_dirs.sort(key=lambda e: e.name.lower())
            fresh_files.sort(key=lambda e: e.name.lower())
            entries = ordered + fresh_dirs + fresh_files
            cleaned = [e.key() for e in entries]
            if cleaned != order:
                log('custom order reconciled for %s (%d -> %d entries)' % (folder, len(order), len(cleaned)))
                self.store.set(folder, order=cleaned)
        return entries

    def collect(self, folder, limit=MAX_RECURSIVE):
        """Flat queue of a folder tree in list order; every folder uses its own mode."""
        out = []
        entries = self.read_entries(folder)
        if entries is None:
            return out
        for e in entries:
            if len(out) >= limit:
                break
            if e.is_dir:
                out.extend(self.collect(e.path, limit - len(out)))
            else:
                out.append(e)
        return out[:limit]

    # ------------------------------------------------------------ lifecycle
    def onInit(self):
        if self.started:
            if self.player.isPlaying() and not self.switching and self.keep_fullscreen:
                log('back from fullscreen by user')
                self.keep_fullscreen = False
            self.sync_highlight()
            return
        self.started = True
        self.my_id = xbmcgui.getCurrentWindowId()
        log('window id=%d start=%s default sort=%s' % (self.my_id, self.start_folder, self.default_sort))
        self.load_folder(self.folder)
        self.setFocusId(C_LIST)

    # ------------------------------------------------------------ browsing
    def has_up(self):
        return self.folder != self.start_folder

    def load_folder(self, folder, select_name=None, keep_selection=False):
        old_pos = self.list_pos() if keep_selection else -1
        entries = self.read_entries(folder)
        if entries is None:
            entries = []
            self.set_status('Folder is empty or not readable')
        self.folder = folder
        self.entries = entries
        self.refill_list()
        lst = self.getControl(C_LIST)
        self.getControl(C_TITLE).setLabel(self.display_folder(folder))
        self.getControl(B_SORT).setLabel('Sort: %s' % SORT_LABELS[self.mode_of(folder)])
        self.setProperty('has_custom', '1' if self.store.get_order(folder) else '')
        self.sync_highlight()
        # entering a folder: land on the first real entry, not on '..'
        sel = 1 if (self.has_up() and lst.size() > 1) else 0
        if select_name:
            for i in range(lst.size()):
                if lst.getListItem(i).getLabel() == select_name:
                    sel = i
                    break
        elif keep_selection and 0 <= old_pos < lst.size():
            sel = old_pos
        if lst.size():
            # after reset() the container has no valid cursor until it is moved once;
            # only pull focus when the list already had it (keep it on sort/reset buttons)
            lst.selectItem(sel)
            if self.getFocusId() in (C_LIST, 0):
                xbmc.executebuiltin('SetFocus(%d,%d)' % (C_LIST, sel))

    def refill_list(self):
        lst = self.getControl(C_LIST)
        lst.reset()
        if self.has_up():
            li = xbmcgui.ListItem('..')
            li.setProperty('kind', 'up')
            lst.addItem(li)
        mode = self.display_mode_of(self.folder)
        for i, e in enumerate(self.entries):
            li = xbmcgui.ListItem(e.name)
            if e.is_dir:
                li.setProperty('kind', 'dir')
            else:
                li.setProperty('kind', 'video' if e.name.lower().endswith(VIDEO_EXT) else 'audio')
                if mode == SORT_DATE and e.mtime:
                    li.setLabel2(fmt_date(e.mtime))
            if i == self.moving_pos:
                li.setProperty('moving', '1')
            lst.addItem(li)

    def list_pos(self):
        try:
            return self.getControl(C_LIST).getSelectedPosition()
        except RuntimeError:
            return -1

    def display_folder(self, folder):
        norm, start = folder.replace('\\', '/'), self.start_folder.replace('\\', '/')
        rel = norm[len(start):] if norm.startswith(start) else norm
        rel = rel.strip('/')
        root = leaf_of(self.start_folder) or self.start_folder
        return '%s / %s' % (root, rel) if rel else root

    def go_up(self):
        if not self.has_up():
            return False
        child = leaf_of(self.folder)
        self.load_folder(parent_of(self.folder), select_name=child)
        return True

    def entry_at(self, pos):
        off = 1 if self.has_up() else 0
        if self.has_up() and pos == 0:
            return 'up', None
        pos -= off
        if 0 <= pos < len(self.entries):
            e = self.entries[pos]
            return ('dir' if e.is_dir else 'file'), e
        return None, None

    # ------------------------------------------------------------ move mode
    def start_move(self, pos):
        kind, e = self.entry_at(pos)
        if kind not in ('dir', 'file'):
            return
        if self.mode_of(self.folder) == SORT_SHUFFLE:
            xbmcgui.Dialog().notification('Folder Player', 'Reordering is not possible in shuffle mode',
                                          xbmcgui.NOTIFICATION_INFO, 2500)
            return
        self.moving_pos = pos - (1 if self.has_up() else 0)
        self.entries_backup = list(self.entries)
        self.setProperty('moving', '1')
        self.refill_list()
        self.getControl(C_LIST).selectItem(pos)
        self.setFocusId(B_MOVEGRAB)
        log('move mode: %s' % e.name)

    def move_step(self, delta):
        i = self.moving_pos
        j = i + delta
        if i < 0 or not (0 <= j < len(self.entries)):
            return
        self.entries[i], self.entries[j] = self.entries[j], self.entries[i]
        self.moving_pos = j
        self.refill_list()
        self.getControl(C_LIST).selectItem(j + (1 if self.has_up() else 0))

    def end_move(self, save):
        moved_to = self.moving_pos
        if save and self.entries != self.entries_backup:
            order = [e.key() for e in self.entries]
            self.store.set(self.folder, mode=SORT_CUSTOM, order=order)
            self.shuffled.discard(self.store.key(self.folder))
            self.getControl(B_SORT).setLabel('Sort: %s' % SORT_LABELS[SORT_CUSTOM])
            self.setProperty('has_custom', '1')
            log('custom order saved for %s' % self.folder)
            self.resync_queue()
        elif not save:
            self.entries = self.entries_backup or self.entries
        self.entries_backup = None
        self.moving_pos = -1
        self.setProperty('moving', '')
        self.refill_list()
        pos = moved_to + (1 if self.has_up() else 0)
        lst = self.getControl(C_LIST)
        if lst.size():
            lst.selectItem(min(max(pos, 0), lst.size() - 1))
        self.setFocusId(C_LIST)
        self.sync_highlight()

    def reset_custom(self):
        if not self.store.get_order(self.folder):
            return
        self.store.delete_order(self.folder)
        xbmcgui.Dialog().notification('Folder Player', 'Custom order removed', xbmcgui.NOTIFICATION_INFO, 2000)
        self.load_folder(self.folder, keep_selection=True)

    def resync_queue(self):
        """The playing folder was reordered -> rebuild the queue around the running title."""
        if not self.queue or self.queue_folder is None:
            return
        playing = self.queue[self.index] if 0 <= self.index < len(self.queue) else None
        if playing is None:
            return
        # only if the reordered folder is part of the playing tree
        if not self.folder.replace('\\', '/').startswith(self.queue_folder.replace('\\', '/')):
            return
        new_queue = self.collect(self.queue_folder)
        idx = next((i for i, q in enumerate(new_queue) if q.path == playing.path), -1)
        if idx >= 0:
            self.queue, self.index = new_queue, idx
            log('queue resynced: %d titles, now %d/%d' % (len(new_queue), idx + 1, len(new_queue)))
            self.sync_highlight()

    # ------------------------------------------------------------ playback
    def busy_collect(self, folder):
        xbmc.executebuiltin('ActivateWindow(busydialognocancel)')
        try:
            files = self.collect(folder)
        finally:
            xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
        log('queue %s: %d files' % (folder, len(files)))
        if len(files) >= MAX_RECURSIVE:
            xbmcgui.Dialog().notification('Folder Player', 'Limited to %d titles' % MAX_RECURSIVE)
        return files

    def play_from(self, folder, clicked=None):
        files = self.busy_collect(folder)
        if not files:
            self.set_status('No media files in %s' % leaf_of(folder))
            return
        start = 0
        if self.mode_of(folder) == SORT_SHUFFLE:
            random.shuffle(files)
            if clicked is not None:
                files = [f for f in files if f.path != clicked.path]
                files.insert(0, clicked)
            log('shuffled %d titles' % len(files))
        elif clicked is not None:
            start = next((i for i, q in enumerate(files) if q.path == clicked.path), 0)
        self.queue = files
        self.queue_folder = folder
        self.play_index(start)

    def entry_menu(self, pos):
        """Long press OK on an entry: small menu with the possible actions."""
        kind, e = self.entry_at(pos)
        if kind not in ('dir', 'file'):
            return False
        shuffle = self.mode_of(self.folder) == SORT_SHUFFLE
        opts = ['Play from here',
                'Play only this folder' if kind == 'dir' else 'Play only this title']
        if not shuffle:
            opts.append('Move (change order)')
        choice = xbmcgui.Dialog().contextmenu(opts)
        log('entry menu %s on %s -> %s' % (kind, e.name, choice))
        if choice == 0:
            if kind == 'file' or shuffle:
                self.play_from(self.folder, clicked=e if kind == 'file' else None)
            else:
                # folder: start the current list's queue at this folder's first title
                files = self.busy_collect(self.folder)
                if not files:
                    self.set_status('No media files in %s' % leaf_of(self.folder))
                    return True
                norm = e.path.replace('\\', '/')
                start = next((i for i, q in enumerate(files) if q.path.replace('\\', '/').startswith(norm)), 0)
                self.queue = files
                self.queue_folder = self.folder
                self.play_index(start)
        elif choice == 1:
            if kind == 'dir':
                self.play_from(e.path)
            else:
                self.queue = [e]
                self.queue_folder = self.folder
                self.play_index(0)
        elif choice == 2:
            self.start_move(pos)
        return True

    def play_selected(self):
        """Play button / media key while nothing is playing: start the highlighted entry."""
        kind, e = self.entry_at(self.list_pos())
        if kind == 'file':
            self.play_from(self.folder, clicked=e)
        elif kind == 'dir':
            self.play_from(e.path)
        else:
            self.play_from(self.folder)

    def play_pause(self):
        if self.player.isPlaying():
            xbmc.executebuiltin('PlayerControl(Play)')
        else:
            self.play_selected()

    def play_index(self, i, natural=False):
        if not self.queue:
            return
        if i < 0:
            i = 0
        if i >= len(self.queue):
            if natural:
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

    def seek_to_fraction(self, x):
        """Mouse click / touch tap on the progress bar: jump to that position."""
        try:
            if not self.player.isPlaying():
                return
            total = self.player.getTotalTime()
            if not total:
                return
            frac = min(1.0, max(0.0, (x - 620.0) / 636.0))
            t = min(frac * total, total - 1)
            log('click-seek to %.0f%% (%.0fs)' % (frac * 100, t))
            self.player.seekTime(t)
        except Exception as e:
            log('click-seek failed: %s' % e, xbmc.LOGWARNING)

    def seek(self, delta):
        try:
            if not self.player.isPlaying():
                return
            t = max(0.0, self.player.getTime() + delta)
            total = self.player.getTotalTime()
            if total and t > total - 1:
                t = total - 1
            self.player.seekTime(t)
        except Exception as e:
            log('seek failed: %s' % e, xbmc.LOGWARNING)

    def on_started(self):
        self.switching = False
        kind = 'video' if self.player.isPlayingVideo() else 'audio'
        cur = xbmcgui.getCurrentWindowId()
        log('started %s, window=%d, keep_fullscreen=%s' % (kind, cur, self.keep_fullscreen))
        if self.keep_fullscreen:
            self.go_fullscreen()
        elif self.my_id and cur != self.my_id:
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
        try:
            lst = self.getControl(C_LIST)
        except RuntimeError:
            return
        playing = self.queue[self.index] if (self.queue and 0 <= self.index < len(self.queue)) else None
        pnorm = playing.path.replace('\\', '/') if playing else None
        for i in range(lst.size()):
            kind, e = self.entry_at(i)
            sel = False
            if playing is not None and e is not None:
                if kind == 'file':
                    sel = e.path == playing.path
                elif kind == 'dir':
                    sel = pnorm.startswith(e.path.replace('\\', '/'))
            lst.getListItem(i).select(sel)
        if playing:
            kind = 'Video' if self.player.isPlayingVideo() else 'Audio'
            qnorm = self.queue_folder.replace('\\', '/')
            rel = pnorm[len(qnorm):] if pnorm.startswith(qnorm) else playing.name
            self.set_status('%d/%d  %s  [%s]' % (self.index + 1, len(self.queue), rel, kind))
            self.setProperty('playing_folder', self.display_folder(self.queue_folder))
        else:
            self.setProperty('playing_folder', '')

    # ------------------------------------------------------------ input
    def onClick(self, cid):
        if cid == C_LIST:
            pos = self.list_pos()
            kind, e = self.entry_at(pos)
            if kind == 'up':
                self.go_up()
            elif kind == 'dir':
                self.load_folder(e.path)
            elif kind == 'file':
                self.play_from(self.folder, clicked=e)
        elif cid == B_PREV:
            self.prev()
        elif cid == B_NEXT:
            self.next()
        elif cid == B_PLAY:
            self.play_pause()
        elif cid == B_RW:
            if self.player.isPlaying():
                xbmc.executebuiltin('PlayerControl(Rewind)')
        elif cid == B_FF:
            if self.player.isPlaying():
                xbmc.executebuiltin('PlayerControl(Forward)')
        elif cid == B_SORT:
            self.cycle_mode()
        elif cid == B_RESET:
            self.reset_custom()
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
        # move mode captures the navigation while active
        if self.moving_pos >= 0:
            if aid in (xbmcgui.ACTION_MOVE_UP,):
                self.move_step(-1)
            elif aid in (xbmcgui.ACTION_MOVE_DOWN,):
                self.move_step(1)
            elif aid == xbmcgui.ACTION_SELECT_ITEM:
                self.end_move(save=True)
            elif aid in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_CONTEXT_MENU):
                self.end_move(save=False)
            return
        if aid in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            if self.go_up():
                return
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
        elif aid in (xbmcgui.ACTION_PAUSE, getattr(xbmcgui, 'ACTION_PLAYER_PLAY', 68),
                     getattr(xbmcgui, 'ACTION_PLAYER_PLAYPAUSE', 229)):
            # play/pause media key: pause while playing, start the highlighted entry while idle
            self.play_pause()
        elif aid == xbmcgui.ACTION_CONTEXT_MENU:
            # long press OK on an entry = action menu; elsewhere = cycle sort
            if self.getFocusId() == C_LIST and self.entry_menu(self.list_pos()):
                return
            self.cycle_mode()
        elif aid in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT) and self.getFocusId() == B_SEEK:
            self.seek(-SEEK_STEP if aid == xbmcgui.ACTION_MOVE_LEFT else SEEK_STEP)
        elif aid == xbmcgui.ACTION_SELECT_ITEM and self.getFocusId() == B_SEEK:
            xbmc.executebuiltin('PlayerControl(Play)')
        elif aid in (getattr(xbmcgui, 'ACTION_MOUSE_LEFT_CLICK', 100), getattr(xbmcgui, 'ACTION_TOUCH_TAP', 401)):
            # click-to-seek: the action carries the position in GUI pixels of the
            # current resolution -> scale to the skin's 1280x720 coordinates
            x, y = action.getAmount1(), action.getAmount2()
            try:
                sw, sh = xbmcgui.getScreenWidth(), xbmcgui.getScreenHeight()
                if sw and sh:
                    x, y = x * 1280.0 / sw, y * 720.0 / sh
            except Exception:
                pass
            log('mouse/touch %d at raw=(%.0f,%.0f) skin=(%.0f,%.0f)' % (aid, action.getAmount1(), action.getAmount2(), x, y), xbmc.LOGDEBUG)
            if SEEK_X <= x <= SEEK_X + SEEK_W and SEEK_Y <= y <= SEEK_Y + SEEK_H:
                self.seek_to_fraction(x)


def choose_folder(heading):
    return xbmcgui.Dialog().browse(0, heading, 'music')


def main():
    folder = ADDON.getSetting('start_folder')
    sort = ADDON.getSetting('sort') or SORT_NAME
    if len(sys.argv) > 1 and sys.argv[1]:
        folder = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] in (SORT_NAME, SORT_DATE):
        sort = sys.argv[2]
    if not folder:
        # first run: pick the music folder (also configurable in the add-on settings)
        folder = choose_folder('Folder Player: choose your music folder')
        if not folder:
            return
        ADDON.setSetting('start_folder', folder)
    if not folder.endswith(('/', '\\')):
        folder += sep_of(folder)
    if not xbmcvfs.exists(folder):
        if not xbmcgui.Dialog().yesno('Folder Player',
                                      'The start folder is not reachable:\n%s\nChoose another folder?' % folder):
            return
        folder = choose_folder('Folder Player: choose your music folder')
        if not folder:
            return
        ADDON.setSetting('start_folder', folder)
        if not folder.endswith(('/', '\\')):
            folder += sep_of(folder)
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
