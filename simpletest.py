# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

import time
import serial

from espatcontrol import espatcontrol


# Get wifi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    raise


def get_url(esp, url, port=80):
    url = "http://example.com/index.html"
    protocol, rest = url.split("://")
    host, path = rest.split("/", 1)
    path = "/" + path
    socket = esp.socket_connect("TCP",host, port, retries=3)
    if (socket):
        http_request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode('utf-8')
        res = esp.socket_send(http_request)
        response= esp.socket_receive()
        return response.decode('utf-8')
    return None

# Debug Level
# Change the Debug Flag if you have issues with AT commands
debugflag = True

uart = serial.Serial("/dev/tty.usbserial-110", 115200, timeout=1)

#uart = busio.UART(TX, RX, baudrate=11520, receiver_buffer_size=2048)


print("ESP AT commands")
# For Boards that do not have an rtspin like challenger_rp2040_wifi set rtspin to False.
esp = espatcontrol.ESP_ATcontrol(
    uart, 115200, reset_pin=0, rts_pin=False, debug=debugflag
)
print("Resetting ESP module")
esp.hard_reset()

first_pass = True
while True:
    try:
        if first_pass:
            # Some ESP do not return OK on AP Scan.
            # See https://github.com/adafruit/Adafruit_CircuitPython_ESP_ATcontrol/issues/48
            # Comment out the next 3 lines if you get a No OK response to AT+CWLAP
            print("Scanning for AP's")
            for ap in esp.scan_APs():
                print(ap)
            print("Checking connection...")
            # secrets dictionary must contain 'ssid' and 'password' at a minimum
            print("Connecting...")
            esp.connect(secrets)
            print("Connected to AT software version ", esp.version)
            print("IP address ", esp.local_ip)
            first_pass = False
        print("Pinging 8.8.8.8...", end="")
        print(esp.ping("8.8.8.8"))
        res = get_url(esp, "http://example.com/index.htm")
        print(res)
        time.sleep(10)

    except (ValueError, RuntimeError, espatcontrol.OKError) as e:
        print("Failed to get data, retrying\n", e)
        print("Resetting ESP module")
        esp.hard_reset()
        continue

