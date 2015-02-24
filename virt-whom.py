"""
Agent for manually reporting host-guest mappings to candlepin,
based on virt-who

Copyright (C) 2014 Carter Kozak <ckozak@redhat.com>

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

import sys
import os
import time
import atexit
import signal
import errno

from manual import Manual
from subscriptionmanager import SubscriptionManager, SubscriptionManagerError

import logging
import log

from optparse import OptionParser, OptionGroup

class OptionParserEpilog(OptionParser):
    """ Epilog is new in Python 2.5, we need to support Python 2.4. """
    def __init__(self, usage="%prog [options]", description=None, epilog=None):
        self.myepilog = epilog
        OptionParser.__init__(self, usage=usage, description=description)

    def format_help(self, formatter=None):
        if formatter is None:
            formatter = self.formatter
        help = OptionParser.format_help(self, formatter)
        return help + "\n" + self.format_myepilog(formatter) + "\n"

    def format_myepilog(self, formatter=None):
        if self.myepilog is not None:
            return formatter.format_description(self.myepilog)
        else:
            return ""

from ConfigParser import NoOptionError

class VirtWho(object):
    def __init__(self, logger, options):
        """
        VirtWho class provides bridge between virtualization supervisor and
        Subscription Manager.

        logger - logger instance
        options - options for virt-who, parsed from command line arguments
        """
        self.logger = logger
        self.options = options

        self.virt = None
        self.subscriptionManager = None

        # True if reload is queued
        self.doReload = False


    def initSM(self):
        """
        Connect to the subscription manager (candlepin).
        """
        try:
            self.subscriptionManager = SubscriptionManager(self.logger,
                self.options.username,
                self.options.password)
            self.subscriptionManager.connect()
        except NoOptionError, e:
            self.logger.exception("Error in reading configuration file (/etc/rhsm/rhsm.conf):")
            raise
        except SubscriptionManagerError, e:
            self.logger.exception("Unable to obtain status from server, UEPConnection is likely not usable:")
            raise
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception, e:
            exceptionCheck(e)
            self.logger.exception("Unknown error")
            raise

    def checkConnections(self):
        """
        Check if connection to subscription manager and virtualization supervisor
        is established and reconnect if needed.
        """
        if self.subscriptionManager is None:
            self.initSM()
        if self.virt is None:
            self.virt = Manual(self.logger, self.options.hypervisor)

    def send(self, retry=True):
        """
        Send list of uuids to subscription manager. This method will call itself
        once if sending fails.

        retry - Should be True on first run, False on second.
        return - True if sending is successful, False otherwise
        """
        logger = self.logger
        try:
            self.checkConnections()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception, e:
            exceptionCheck(e)
            if retry:
                logger.exception("Unable to create connection:")
                return self.send(False)
            else:
                return False

        try:
            virtualGuests = self.virt.getHostGuestMapping()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception, e:
            exceptionCheck(e)
            # Communication with virtualization supervisor failed
            self.virt = None
            # Retry once
            if retry:
                logger.exception("Error in communication with virt backend, trying to recover:")
                return self.send(False)
            else:
                return False

        try:
            owner = self.options.org
            result = self.subscriptionManager.hypervisorCheckIn(owner, self.options.env, virtualGuests, type='manual')

            # Show the result of hypervisorCheckIn
            for fail in result['failedUpdate']:
                logger.error("Error during update list of guests: %s", str(fail))
            for updated in result['updated']:
                guests = [x['guestId'] for x in updated['guestIds']]
                logger.info("Updated host: %s with guests: [%s]", updated['uuid'], ", ".join(guests))
            for created in result['created']:
                guests = [x['guestId'] for x in created['guestIds']]
                logger.info("Created host: %s with guests: [%s]", created['uuid'], ", ".join(guests))
            for unchanged in result['unchanged']:
                guests = [x['guestId'] for x in unchanged['guestIds']]
                logger.info("Did not modify host: %s with guests: [%s]", unchanged['uuid'], ", ".join(guests))
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception, e:
            exceptionCheck(e)
            # Communication with subscription manager failed
            self.subscriptionManager = None
            # Retry once
            if retry:
                logger.exception("Error in communication with subscription manager, trying to recover:")
                return self.send(False)
            else:
                return False

        return True

    def ping(self):
        """
        Test if connection to virtualization manager is alive.

        return - True if connection is alive, False otherwise
        """
        if self.virt is None:
            return False
        return self.virt.ping()

    def queueReload(self, *p):
        """
        Reload virt-who configuration. Called on SIGHUP signal arrival.
        """
        self.doReload = True


def exceptionCheck(e):
    try:
        # This happens when connection to server is interrupted (CTRL+C or signal)
        if e.args[0] == errno.EALREADY:
            sys.exit(0)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        pass

def main():
    parser = OptionParserEpilog(usage="virt-whom [-d]",
                                description="Agent for manually reporting hypervisor ID to virtual guest ID mappings to subscription manager")
    parser.add_option("-d", "--debug", action="store_true", dest="debug", default=False, help="Enable debugging output")
    parser.add_option("-e", "--env", dest="env", default=None, help="Subscription management environment in which to create and update hypervisor consumers")
    parser.add_option("-H", "--hypervisor", action="append", dest="hypervisor", help="hypervisorID:guestId1,guestId2,guestId3")
    parser.add_option("-u", "--username", dest="username", help="Username to authenticate with. (instead of system identity cert)")
    parser.add_option("-p", "--password", dest="password", help="Password to authenticate with. (instead of system identity cert)")
    parser.add_option("-o", "--org", dest="org", help="Destination organization to report to.")

    (options, args) = parser.parse_args()

    logger = log.getLogger(options.debug)

    virtWho = VirtWho(logger, options)
    signal.signal(signal.SIGHUP, virtWho.queueReload)
    virtWho.checkConnections()

    logger.debug("Virt-who is running in manual mode")

    # Send list of virtual guests and exit
    virtWho.send()

if __name__ == '__main__':
    try:
        if os.getuid() != 0:
            sys.stderr.write('Error: this command requires root access to execute\n')
            sys.exit(8)
        main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception, e:
        print e
        logger = log.getLogger(True)
        logger.exception("Fatal error:")
        sys.exit(1)
