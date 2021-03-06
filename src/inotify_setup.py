# -*- coding: utf-8 -*-
"""
inotify_setup.py 

setup inotify to watch directory
"""
import logging 
from threading import Thread

import pyinotify

class InotifyError(Exception):
    pass

from event_names import inotify_idle

_incoming_files_mask = pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO
_outgoing_files_mask = pyinotify.IN_DELETE | pyinotify.IN_MOVED_FROM 
_file_changes_mask = _incoming_files_mask | _outgoing_files_mask   
                
class _ProcessEvent(pyinotify.ProcessEvent):
    
    def my_init(self, **kwargs):
        self._log = logging.getLogger("_ProcessEvent")
        self._log.info("max_queued_events = {0}".format(
            pyinotify.max_queued_events))
        self._file_name_queue = kwargs["file_name_queue"]

    def process_default(self, inotify_event):
        self._file_name_queue.put((inotify_event.name, 
                                   inotify_event.maskname, ))

    def process_IN_Q_OVERFLOW(self, event):
        error_message = "Overflow: max_queued_events={0} {1}".format(
            pyinotify.max_queued_events, event,
        )
        self._log.error(error_message)
        raise InotifyError(error_message)

class _NotifierThread(Thread):
    def __init__(self, halt_event, notifier, file_name_queue):
        Thread.__init__(self, name="notifier")
        self._halt_event = halt_event
        self._notifier = notifier
        self._file_name_queue = file_name_queue 
        self._log = logging.getLogger("notifier_thread")

    def run(self):
        while not self._halt_event.is_set():
            if self._notifier.check_events(timeout=(1 * 1000)):
                self._notifier.read_events()
                try:
                    self._notifier.process_events()
                except Exception:
                    self._log.exception("process_events")
                    self._halt_event.set()
                    break
            else:
                self._file_name_queue.put((None, inotify_idle, ))

def create_notifier(watch_path, file_name_queue):
    """
    create the inotifier infrastructure for watching a directory
    """
    log = logging.getLogger("create_notifier")
    watch_manager = pyinotify.WatchManager()

    log.info("watching path {0}".format(watch_path))
    result = watch_manager.add_watch(watch_path, 
                                     mask=_file_changes_mask,
                                     rec=False, 
                                     auto_add=False, 
                                     quiet=False)
    if not watch_path in result:
        raise InotifyError("add_watch failed: invalid directory '{0}'".format(
            watch_path))

    if result[watch_path] < 0:
        raise InotifyError("add_watch failed: {0} {1}".format(
                           watch_path, 
                           result[watch_path]))

    proc_fun = _ProcessEvent(file_name_queue=file_name_queue)
    notifier = pyinotify.Notifier(watch_manager, default_proc_fun=proc_fun)

    return notifier

def create_notifier_thread(halt_event, notifier, file_name_queue):
    """
    create a Thread object that polls the notifier and puts file_names
    in the queue
    """
    return _NotifierThread(halt_event, notifier, file_name_queue)
