"""Manipulate a jails fstab"""
import os
import shutil
import tempfile
from datetime import datetime
from subprocess import PIPE, Popen, call

from iocage.lib.ioc_common import logit, open_atomic
from iocage.lib.ioc_json import IOCJson
from iocage.lib.ioc_list import IOCList


class IOCFstab(object):
    """Will add or remove an entry, and mount or umount the filesystem."""

    def __init__(self, uuid, tag, action, source, destination, fstype,
                 fsoptions, fsdump, fspass, index=None, silent=False,
                 callback=None):
        self.pool = IOCJson().json_get_value("pool")
        self.iocroot = IOCJson(self.pool).json_get_value("iocroot")
        self.uuid = uuid
        self.tag = tag
        self.action = action
        self.src = source
        self.dest = destination
        self.fstype = fstype
        self.fsoptions = fsoptions
        self.fsdump = fsdump
        self.fspass = fspass
        self.index = index
        self.mount = f"{self.src}\t{self.dest}\t{self.fstype}\t" \
                     f"{self.fsoptions}\t{self.fsdump}\t{self.fspass}"
        self.silent = silent
        self.callback = callback

        self.__fstab_parse__()

    def __fstab_parse__(self):
        """
        Checks which action the user is asking for and calls the
        appropriate methods.
        """
        if self.action == "add":
            self.__fstab_add__()
            self.__fstab_mount__()
        elif self.action == "remove":
            dest = self.__fstab_remove__()
            self.__fstab_umount__(dest)
        elif self.action == "edit":
            self.__fstab_edit__()
        else:
            raise RuntimeError("Type of operation not specified!")

    def __fstab_add__(self):
        """Adds a users mount to the jails fstab"""
        with open(f"{self.iocroot}/jails/{self.uuid}/fstab", "r") as fstab:
            with open_atomic(f"{self.iocroot}/jails/{self.uuid}/fstab",
                             "w") as _fstab:
                # open_atomic will empty the file, we need these still.
                for line in fstab.readlines():
                    _fstab.write(line)

                date = datetime.utcnow().strftime("%F %T")
                _fstab.write(f"{self.mount} # Added by iocage on {date}\n")

        logit({
            "level"  : "INFO",
            "message": f"Successfully added mount to {self.uuid}"
                       f" ({self.tag})'s fstab"
        },
            _callback=self.callback,
            silent=self.silent)

    def __fstab_remove__(self):
        """
        Removes the users mount by index or matching string.

        :return: The destination of the specified mount
        """
        removed = False
        index = 0

        with open(f"{self.iocroot}/jails/{self.uuid}/fstab", "r") as fstab:
            with open_atomic(f"{self.iocroot}/jails/{self.uuid}/fstab",
                             "w") as _fstab:
                for line in fstab.readlines():
                    if line.rsplit("#")[0].rstrip() == self.mount or index \
                            == self.index and not removed:
                        removed = True
                        dest = line.split()[1]
                        continue
                    else:
                        _fstab.write(line)

                    index += 1
        if removed:
            logit({
                "level"  : "INFO",
                "message": f"Successfully removed mount from {self.uuid}"
                           f" ({self.tag})'s fstab"
            },
                _callback=self.callback,
                silent=self.silent)
            return dest  # Needed for umounting, otherwise we lack context.
        else:
            logit({
                "level"  : "INFO",
                "message": "No matching fstab entry."
            },
                _callback=self.callback,
                silent=self.silent)
            exit()

    def __fstab_mount__(self):
        """Mounts the users mount if the jail is running."""
        status, _ = IOCList().list_get_jid(self.uuid)

        os.makedirs(self.dest, exist_ok=True)
        if status:
            proc = Popen(["mount", "-t", self.fstype, "-o", self.fsoptions,
                          self.src, self.dest], stdout=PIPE, stderr=PIPE)
            stdout_data, stderr_data = proc.communicate()

            if stderr_data:
                raise RuntimeError(f"{stderr_data.decode('utf-8')}")

    def __fstab_umount__(self, dest):
        """
        Umounts the users mount if the jail is running.

        :param dest: The destination to umount.
        """
        status, _ = IOCList().list_get_jid(self.uuid)

        if status:
            proc = Popen(["umount", "-f", dest], stdout=PIPE, stderr=PIPE)
            stdout_data, stderr_data = proc.communicate()

            if stderr_data:
                raise RuntimeError(f"{stderr_data.decode('utf-8')}")

    def __fstab_edit__(self):
        """
        Opens up the users EDITOR, or vi and replaces the jail's fstab
        with the new content.
        """
        editor = os.environ.get("EDITOR", "/usr/bin/vi")
        err_editor = editor.split("/")[-1]
        jail_fstab = f"{self.iocroot}/jails/{self.uuid}/fstab"
        tmp_fstab = tempfile.NamedTemporaryFile(suffix=".iocage")

        shutil.copy2(jail_fstab, tmp_fstab.name)
        proc = call([editor, tmp_fstab.name])

        if proc == 0:
            with open(jail_fstab, "w") as fstab:
                for line in tmp_fstab.readlines():
                    fstab.write(line.decode("utf-8"))
        else:
            raise RuntimeError(f"An error occurred within {err_editor}!")
