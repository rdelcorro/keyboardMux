# Keyboard muxer

### Problem statement

Connect a single physical USB keyboard to multiple computers / devices at the same time using bluetooth but send the keypresses to a single device at the same time
Allow the user to switch the target device using any key combination

#### Requirements

- Raspberry pi (any will work, just needs BT support)
- Latest raspbian installed

## Configure the BT daemon

The input BT plugin needs to be disabled. To do so, modify the BT service
```
sudo vi /lib/systemd/system/bluetooth.service
```

Edit the file and change the line ExecStart to:
```
ExecStart=/usr/lib/bluetooth/bluetoothd -P input
```

## Hardware
Connect a keyboard

## Modify the target change key codes

The server has a function called ```change_active_target_device``` that has a few key shortcuts used to change the target device you send the keyboard to
In my case I use Fn + F1 to F4 to change the target, but you can use anything. If you do not want to use any dedicated key like volume up to do this and your 
keyboard is programmable, you can send for example ```!@#$%^``` or some other combination to to this

## Install the requirements

```
pip3 install -r requirements.txt
```

## Execute the server as root

Note, this can be automatically be done on a systemd or any other auto startup script

```
python3 server.py
```

## Pair any device to ```KB_Mux```

To use the tool, after running, just pair N devices to it by following the normal pairing procedure of your OS
Once its paired, you can choose the target via the key shortcuts

## Notes

Due to some time limits, there are a few things I left out:

- If you stop the process, the BT devices will disconnect but not auto reconnect once the server is executed again. Not a problem for me as the pi will always run
- To reconnect, simply disable / enable the BT on windows or click connect on OSX
- The order of connection will determine which device is which option (ie pair pc1 and then pc2, Fn + F1 will be pc1)
- The code has some callbacks it never uses, but are there for debugging purposes

### PRs are welcome 







