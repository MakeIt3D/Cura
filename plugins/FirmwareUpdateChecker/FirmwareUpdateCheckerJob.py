# Copyright (c) 2017 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from UM.Application import Application
from UM.Message import Message
from UM.Logger import Logger
from UM.Job import Job
from UM.Version import Version

import urllib.request
from urllib.error import URLError
from typing import Dict
import codecs

from .FirmwareUpdateCheckerLookup import FirmwareUpdateCheckerLookup, getSettingsKeyForMachine

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("cura")


##  This job checks if there is an update available on the provided URL.
class FirmwareUpdateCheckerJob(Job):
    STRING_ZERO_VERSION = "0.0.0"
    STRING_EPSILON_VERSION = "0.0.1"
    ZERO_VERSION = Version(STRING_ZERO_VERSION)
    EPSILON_VERSION = Version(STRING_EPSILON_VERSION)

    def __init__(self, container, silent, lookups: FirmwareUpdateCheckerLookup, callback) -> None:
        super().__init__()
        self._container = container
        self.silent = silent
        self._callback = callback

        self._lookups = lookups
        self._headers = {}  # type:Dict[str, str]  # Don't set headers yet.

    def getUrlResponse(self, url: str) -> str:
        result = self.STRING_ZERO_VERSION

        try:
            request = urllib.request.Request(url, headers = self._headers)
            response = urllib.request.urlopen(request)
            result = response.read().decode("utf-8")
        except URLError:
            Logger.log("w", "Could not reach '{0}', if this URL is old, consider removal.".format(url))

        return result

    def getCurrentVersionForMachine(self, machine_id: int) -> Version:
        max_version = self.ZERO_VERSION

        machine_urls = self._lookups.getCheckUrlsFor(machine_id)
        parse_function = self._lookups.getParseVersionUrlFor(machine_id)
        if machine_urls is not None and parse_function is not None:
            for url in machine_urls:
                version = parse_function(self.getUrlResponse(url))
                if version > max_version:
                    max_version = version

        if max_version < self.EPSILON_VERSION:
            Logger.log("w", "MachineID {0} not handled!".format(repr(machine_id)))

        return max_version

    def run(self):
        if self._lookups is None:
            Logger.log("e", "Can not check for a new release. URL not set!")
            return

        try:
            application_name = Application.getInstance().getApplicationName()
            application_version = Application.getInstance().getVersion()
            self._headers = {"User-Agent": "%s - %s" % (application_name, application_version)}

            # get machine name from the definition container
            machine_name = self._container.definition.getName()

            # If it is not None, then we compare between the checked_version and the current_version
            machine_id = self._lookups.getMachineByName(machine_name.lower())
            if machine_id is not None:
                Logger.log("i", "You have a(n) {0} in the printer list. Let's check the firmware!".format(machine_name))

                current_version = self.getCurrentVersionForMachine(machine_id)

                # If it is the first time the version is checked, the checked_version is ""
                setting_key_str = getSettingsKeyForMachine(machine_id)
                checked_version = Version(Application.getInstance().getPreferences().getValue(setting_key_str))

                # If the checked_version is "", it's because is the first time we check firmware and in this case
                # we will not show the notification, but we will store it for the next time
                Application.getInstance().getPreferences().setValue(setting_key_str, current_version)
                Logger.log("i", "Reading firmware version of %s: checked = %s - latest = %s", machine_name, checked_version, current_version)

                # The first time we want to store the current version, the notification will not be shown,
                # because the new version of Cura will be release before the firmware and we don't want to
                # notify the user when no new firmware version is available.
                if (checked_version != "") and (checked_version != current_version):
                    Logger.log("i", "SHOWING FIRMWARE UPDATE MESSAGE")

                    message = Message(i18n_catalog.i18nc(
                        "@info Don't translate {machine_name}, since it gets replaced by a printer name!",
                        "New features are available for your {machine_name}! It is recommended to update the firmware on your printer.").format(
                        machine_name = machine_name),
                        title = i18n_catalog.i18nc(
                                          "@info:title The %s gets replaced with the printer name.",
                                          "New %s firmware available") % machine_name)

                    message.addAction(machine_id,
                                      i18n_catalog.i18nc("@action:button", "How to update"),
                                      "[no_icon]",
                                      "[no_description]",
                                      button_style = Message.ActionButtonStyle.LINK,
                                      button_align = Message.ActionButtonStyle.BUTTON_ALIGN_LEFT)

                    message.actionTriggered.connect(self._callback)
                    message.show()
            else:
                Logger.log("i", "No machine with name {0} in list of firmware to check.".format(machine_name))

        except Exception as e:
            Logger.log("w", "Failed to check for new version: %s", e)
            if not self.silent:
                Message(i18n_catalog.i18nc("@info", "Could not access update information.")).show()
            return
