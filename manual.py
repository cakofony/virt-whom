"""
Module for communcating with subscription-manager,
part of virt-whom, based on virt-who

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

class Manual(object):

    def __init__(self, logger, hypervisors=None):
        self.logger = logger
        self.hypervisorList = hypervisors or []
        self._parse_hypervisor_list()

    def getHostGuestMapping(self):
        return self.hypervisors

    def ping(self):
        return True

    def _parse_hypervisor_list(self):
        self.hypervisors = dict([self._parse_hypervisor(line) for line in self.hypervisorList])

    def _parse_hypervisor(self, hypervisor_raw):
        '''
        takes a raw string such as "aaa-aaaa-aaa:bbb-ccc,ddd-eee" and parses it into
        a key, value tuple ("aaa-aaaa-aaa", ["bbb-ccc", "ddd-eee"])
        '''
        data_parts = hypervisor_raw.split(':')
        if len(data_parts) > 2 or not data_parts[0].strip():
            raise ValueError("Hypervisor info must take the form 'hypervisorId:guestid1,guestid2,etc'")

        hypervisor = data_parts[0].strip()
        guestIds = []
        if len(data_parts) == 2:
            guestIds = filter(None, [guest.strip() for guest in data_parts[1].split(',')])

        # Create full representation of the guest
        guests = [self._create_guest(guestId) for guestId in guestIds]
        return (hypervisor, guests)

    def _create_guest(self, guest_id):
        return {'guestId': guest_id,
                'attributes': {'virtWhoType': 'manual'}}
