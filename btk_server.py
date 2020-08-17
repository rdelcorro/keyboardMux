#!/usr/bin/python3
import os
import sys
import dbus
import dbus.service
import socket
import _thread
from kb_client import Kbrd

from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop

ENABLE_PAIRING = True


class BTKbDevice:
    """
    create a bluetooth device to emulate a HID keyboard
    """
    MY_DEV_NAME = 'KB_Mux'
    # Service port - must match port configured in SDP record
    P_CTRL = 17
    # Service port - must match port configured in SDP record#Interrrupt port
    P_INTR = 19
    # BlueZ dbus
    PROFILE_DBUS_PATH = '/bluez/yaptb/btkb_profile'
    ADAPTER_IFACE = 'org.bluez.Adapter1'
    DEVICE_INTERFACE = 'org.bluez.Device1'
    DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
    DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'

    # file path of the sdp record to laod
    install_dir  = os.path.dirname(os.path.realpath(__file__))
    SDP_RECORD_PATH = os.path.join(install_dir,
                                   'sdp_record.xml')
    # UUID for HID service (1124)
    # https://www.bluetooth.com/specifications/assigned-numbers/service-discovery
    UUID = '00001124-0000-1000-8000-00805f9b34fb'

    def __init__(self, hci=0):
        self.dev_path = '/org/bluez/hci{}'.format(hci)
        print('Setting up BT device')
        self.bus = dbus.SystemBus()
        self.adapter_methods = dbus.Interface(
            self.bus.get_object('org.bluez',
                                self.dev_path),
            self.ADAPTER_IFACE)
        self.adapter_property = dbus.Interface(
            self.bus.get_object('org.bluez',
                                self.dev_path),
            self.DBUS_PROP_IFACE)

        print('Configuring for name {}'.format(BTKbDevice.MY_DEV_NAME))
        self.config_hid_profile()

        # set the Bluetooth device configuration
        self.alias = BTKbDevice.MY_DEV_NAME
        self.active_target_index = 0
        self.paired_connections = []

    def create_sockets(self):
        scontrol = socket.socket(socket.AF_BLUETOOTH,
                                      socket.SOCK_SEQPACKET,
                                      socket.BTPROTO_L2CAP)
        scontrol.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sinterrupt = socket.socket(socket.AF_BLUETOOTH,
                                        socket.SOCK_SEQPACKET,
                                        socket.BTPROTO_L2CAP)
        sinterrupt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return scontrol, sinterrupt

    @property
    def address(self):
        """Return the adapter MAC address."""
        return self.adapter_property.Get(self.ADAPTER_IFACE,
                                         'Address')

    @property
    def powered(self):
        """
        power state of the Adapter.
        """
        return self.adapter_property.Get(self.ADAPTER_IFACE, 'Powered')

    @powered.setter
    def powered(self, new_state):
        self.adapter_property.Set(self.ADAPTER_IFACE, 'Powered', new_state)

    @property
    def alias(self):
        return self.adapter_property.Get(self.ADAPTER_IFACE,
                                         'Alias')

    @alias.setter
    def alias(self, new_alias):
        self.adapter_property.Set(self.ADAPTER_IFACE,
                                  'Alias',
                                  new_alias)

    @property
    def discoverabletimeout(self):
        """Discoverable timeout of the Adapter."""
        return self.adapter_property.Get(self.ADAPTER_IFACE,
                                      'DiscoverableTimeout')

    @discoverabletimeout.setter
    def discoverabletimeout(self, new_timeout):
        self.adapter_property.Set(self.ADAPTER_IFACE,
                                  'DiscoverableTimeout',
                                  dbus.UInt32(new_timeout))

    @property
    def discoverable(self):
        """Discoverable state of the Adapter."""
        return self.adapter_property.Get(self.ADAPTER_IFACE, 'Discoverable')

    @discoverable.setter
    def discoverable(self, new_state):
        self.adapter_property.Set(self.ADAPTER_IFACE,
                                  'Discoverable',
                                  new_state)

    def config_hid_profile(self):
        print('Configuring Bluez Profile')
        service_record = self.read_sdp_service_record()

        opts = {
            'Role': 'server',
            'RequireAuthentication': False,
            'RequireAuthorization': False,
            'AutoConnect': True,
            'ServiceRecord': service_record,
        }

        manager = dbus.Interface(self.bus.get_object('org.bluez',
                                                     '/org/bluez'),
                                 'org.bluez.ProfileManager1')

        manager.RegisterProfile(BTKbDevice.PROFILE_DBUS_PATH,
                                BTKbDevice.UUID,
                                opts)

        print('Profile registered ')

    @staticmethod
    def read_sdp_service_record():
        print('Reading service record')
        try:
            fh = open(BTKbDevice.SDP_RECORD_PATH, 'r')
        except OSError:
            sys.exit('Could not open the sdp record. Exiting...')

        return fh.read()   

    # Called on a worker thread to allow continuous pairing
    def listen(self):
        print('Waiting for connections')
        scontrol, sinterrupt = self.create_sockets()
        
        scontrol.bind((self.address, self.P_CTRL))
        sinterrupt.bind((self.address, self.P_INTR))

        # Start listening on the server sockets
        scontrol.listen() 
        sinterrupt.listen()

        while(True):
            print("Waiting for inbound connections")
            _, cinfo = scontrol.accept()
            print('{} connected on the control socket'.format(cinfo[0]))

            cinterrupt, cinfo = sinterrupt.accept()
            print('{} connected on the interrupt channel'.format(cinfo[0]))

            self.paired_connections.append(cinterrupt)

    def change_active_target_device(self, msg):
        if len(msg) > 4:
            if msg[4] == 58:
                print("Switched to device 0")
                self.active_target_index = 0
                return True
            if msg[4] == 59:
                print("Switched to device 1")
                self.active_target_index = 1
                return True
            if msg[4] == 60:
                print("Switched to device 2")
                self.active_target_index = 2
                return True
            if msg[4] == 61:
                print("Switched to device 3")
                self.active_target_index = 3
                return True

        return False

    def send(self, msg):
        if self.change_active_target_device(msg):
            # Eat the key if its used for a switch. Not needed but cleaner
            return

        if self.paired_connections:   
            if len(self.paired_connections) > self.active_target_index:
                con = self.paired_connections[self.active_target_index]
                con.send(bytes(bytearray(msg)))
            else:
                print("Sending a key to a non existant keyboard")
        else:
            print("No active device yet")


class BTKbService():
    def __init__(self):
        print('Setting up service')
        self.device = BTKbDevice()

    def listen(self):
        self.device.listen()

    def send_keys(self, cmd):
        self.device.send(cmd)


if __name__ == '__main__':
    if not os.geteuid() == 0:
        sys.exit('Only root can run this')

    DBusGMainLoop(set_as_default=True)
    myservice = BTKbService()
    mainloop = GLib.MainLoop()

    _thread.start_new_thread(myservice.listen, ())
    kb = Kbrd(myservice.send_keys)

    print('starting event loop KBD')
    _thread.start_new_thread( kb.event_loop, ())

    print('starting event loop BT')
    mainloop.run()
