#!/usr/bin/python3
"""
Bluetooth HID keyboard emulator DBUS Service
Original idea taken from:
http://yetanotherpointlesstechblog.blogspot.com/2016/04/emulating-bluetooth-keyboard-with.html
Moved to Python 3 and tested with BlueZ 5.43
"""
import os
import sys
import dbus
import dbus.service
import socket
import _thread
from kb_client import Kbrd

from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop

from bluetooth import BluetoothSocket, L2CAP
import bluetooth

ENABLE_PAIRING = True


class HumanInterfaceDeviceProfile(dbus.service.Object):
    """
    BlueZ D-Bus Profile for HID
    """
    fd = -1

    @dbus.service.method('org.bluez.Profile1',
                         in_signature='', out_signature='')
    def Release(self):
            print('Release')
            mainloop.quit()

    @dbus.service.method('org.bluez.Profile1',
                         in_signature='oha{sv}', out_signature='')
    def NewConnection(self, path, fd, properties):
            self.fd = fd.take()
            print('NewConnection({}, {})'.format(path, self.fd))
            for key in properties.keys():
                    if key == 'Version' or key == 'Features':
                            print('  {} = 0x{:04x}'.format(key,
                                                           properties[key]))
                    else:
                            print('  {} = {}'.format(key, properties[key]))

    @dbus.service.method('org.bluez.Profile1',
                         in_signature='o', out_signature='')
    def RequestDisconnection(self, path):
            print('RequestDisconnection {}'.format(path))

            if self.fd > 0:
                    os.close(self.fd)
                    self.fd = -1


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
        self.scontrol = None
        self.ccontrol = None  # Socket object for control
        self.sinterrupt = None
        self.cinterrupt = None  # Socket object for interrupt
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

        self.bus.add_signal_receiver(self.interfaces_added,
                                     dbus_interface=self.DBUS_OM_IFACE,
                                     signal_name='InterfacesAdded')

        self.bus.add_signal_receiver(self._properties_changed,
                                     dbus_interface=self.DBUS_PROP_IFACE,
                                     signal_name='PropertiesChanged',
                                     arg0=self.DEVICE_INTERFACE,
                                     path_keyword='path')

        print('Configuring for name {}'.format(BTKbDevice.MY_DEV_NAME))

        self.config_hid_profile()

        # set the Bluetooth device configuration
        self.alias = BTKbDevice.MY_DEV_NAME
        self.discoverabletimeout = 0
        self.discoverable = True
        self.paired_devices = []
        self.paired_connections = []

        self.load_paired_devices()
        #self.connect_all_devices()

        self.active_target_index = 0

    
    def has_paired_devices(self):
        return len(self.paired_devices) > 0

    def connectNonTupple(self, f, a, b):
        try:
            f((a,b))
        except:
            pass


    def connect_to_paired_device(self, target):
        print("Connecting to paired device: ", target)
        control, interrupt = self.create_sockets()

        controlListen, interruptListen = self.create_sockets()
        controlListen.bind((self.address, self.P_CTRL))
        controlListen.listen()
        interruptListen.bind((self.address, self.P_INTR))
        interruptListen.listen()
        
        try:
            print("Before connecting")
            #_thread.start_new_thread(self.connectNonTupple, (interrupt.connect, target, self.P_INTR))
        except OSError as e:
            #e = sys.exc_info()[0]
            print(e)
            # Set them in listen mode and wait for the incomming connection
            print("Before accepting")
            _, cinfo = interruptListen.accept()
            print("Wow, the target did connect")

        print("Before accepting 2")
        _, cinfo = interruptListen.accept()
        print("After accepting 2")

        interrupt.connect((target, self.P_INTR))
        control.connect((target, self.P_CTRL))
        self.paired_connections.append(interrupt)

    def load_paired_devices(self):
        try:
            with open("pairedDevices", "r") as f:
                devices = f.readlines()
                for d in devices:
                    self.paired_devices.append(d.strip())
        except:
            pass

    def connect_all_devices(self):
        for d in self.paired_devices:
            self.connect_to_paired_device(d)


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


    def interfaces_added(self, a, b, c):
        pass

    def _properties_changed(self, interface, changed, invalidated, path):
        if self.on_disconnect is not None:
            if 'Connected' in changed:
                if not changed['Connected']:
                    self.on_disconnect()

    def on_disconnect(self):
        print('The client has been disconnected. IGNORING')
        #self.listen()

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
        return self.adapter_property.Get(
            self.ADAPTER_INTERFACE, 'Discoverable')

    @discoverable.setter
    def discoverable(self, new_state):
        self.adapter_property.Set(self.ADAPTER_IFACE,
                                  'Discoverable',
                                  new_state)

    def config_hid_profile(self):
        """
        Setup and register HID Profile
        """

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

        HumanInterfaceDeviceProfile(self.bus,
                                    BTKbDevice.PROFILE_DBUS_PATH)

        manager.RegisterProfile(BTKbDevice.PROFILE_DBUS_PATH,
                                BTKbDevice.UUID,
                                opts)

        print('Profile registered ')

    @staticmethod
    def read_sdp_service_record():
        """
        Read and return SDP record from a file
        :return: (string) SDP record
        """
        print('Reading service record')
        try:
            fh = open(BTKbDevice.SDP_RECORD_PATH, 'r')
        except OSError:
            sys.exit('Could not open the sdp record. Exiting...')

        return fh.read()   


    def add_paired_device(self, address):
        # Store to a txt file if it does not exist
        for d in self.paired_devices:
            if address == d:
                return
        
        self.paired_devices.append(address)

        with open("pairedDevices", "a") as f:
            f.write(address + '\n')


    # Called on a worker thread to allow pairing
    def listen(self):
        """
        Listen for connections coming from HID client
        """

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

            self.add_paired_device(cinfo[0])
            self.paired_connections.append(cinterrupt)


        

       

    def send(self, msg):
        """
        Send HID message
        :param msg: (bytes) HID packet to send
        """
        if self.paired_connections:   
            
            # Check if we want to toggle the target device
            if msg[4] == 116:
                self.active_target_index = 0
            if msg[4] == 117:
                self.active_target_index = 1



            con = self.paired_connections[self.active_target_index]
            con.send(bytes(bytearray(msg)))
        else:
            print("No active device yet")


class BTKbService(dbus.service.Object):
    """
    Setup of a D-Bus service to recieve HID messages from
    processes.
    Send the recieved HID messages to the Bluetooth HID server to send
    """
    def __init__(self):
        print('Setting up service T')
        self.device = BTKbDevice()


    def listen(self):
        self.device.listen()

    def has_paired_devices(self):
        return self.device.has_paired_devices()
        

    def send_keys(self, cmd):
        self.device.send(cmd)


if __name__ == '__main__':
    # The sockets require root permission
    if not os.geteuid() == 0:
        sys.exit('Only root can run this script')

    DBusGMainLoop(set_as_default=True)
    myservice = BTKbService()
    #mainloop = GLib.MainLoop()

    if not myservice.has_paired_devices() or ENABLE_PAIRING:
        _thread.start_new_thread(myservice.listen, ())

    print('Setting up keyboard')
    kb = Kbrd(myservice.send_keys)

    print('starting event loop KBD')
    kb.event_loop()
    #_thread.start_new_thread( kb.event_loop, ())

    #print('starting event loop BT')
    #mainloop.run()


    # Test sending a connection request on a try catch and listen before that so the target can connect