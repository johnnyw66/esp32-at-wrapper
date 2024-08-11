# SPDX-FileCopyrightText: 2018 ladyada for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
Originally - adafruit_espatcontrol.adafruit_espatcontrol`
====================================================

Use the ESP AT command sent to communicate with the Interwebs.
Its slow, but works to get data into CircuitPython

Command set:
https://www.espressif.com/sites/default/files/documentation/4a-esp8266_at_instruction_set_en.pdf

Examples:
https://www.espressif.com/sites/default/files/documentation/4b-esp8266_at_command_examples_en.pdf

* Author(s): ladyada

Modified for MicroPython to work with ESP32C3 SuperMini-
"""


import gc
import time
#from digitalio import Direction, DigitalInOut

try:
    from typing import Optional, Dict, Union, List
    #import busio
except ImportError:
    pass

class OKError(Exception):
    """The exception thrown when we didn't get acknowledgement to an AT command"""

class ESP_ATcontrol:
    """A wrapper for AT commands to a connected ESP8266 or ESP32 module to do
    some very basic internetting. The ESP module must be pre-programmed with
    AT command firmware, you can use esptool or our CircuitPython miniesptool
    to upload firmware"""

    # pylint: disable=too-many-public-methods, too-many-instance-attributes
    MODE_STATION = 1
    MODE_SOFTAP = 2
    MODE_SOFTAPSTATION = 3
    TYPE_TCP = "TCP"
    TCP_MODE = "TCP"
    TYPE_UDP = "UDP"
    TYPE_SSL = "SSL"
    TLS_MODE = "SSL"
    STATUS_APCONNECTED = 2  # CIPSTATUS method
    STATUS_WIFI_APCONNECTED = 2  # CWSTATE method
    STATUS_SOCKETOPEN = 3  # CIPSTATUS method
    STATUS_SOCKET_OPEN = 3  # CIPSTATE method
    STATUS_SOCKETCLOSED = 4  # CIPSTATUS method
    STATUS_SOCKET_CLOSED = 4  # CIPSTATE method
    STATUS_NOTCONNECTED = 5  # CIPSTATUS method
    STATUS_WIFI_NOTCONNECTED = 1  # CWSTATE method
    STATUS_WIFI_DISCONNECTED = 4  # CWSTATE method

    USER_AGENT = "esp-idf/1.0 esp32"

    def __init__(
        self,
        uart,
        default_baudrate: int,
        *,
        run_baudrate: Optional[int] = None,
        rts_pin: Optional[int] = None,
        reset_pin: Optional[int] = None,
        debug: bool = False,
        use_cipstatus: bool = False,
    ):

        """This function doesn't try to do any sync'ing, just sets up
        # the hardware, that way nothing can unexpectedly fail!"""
        self._uart = uart
        if not run_baudrate:
            run_baudrate = default_baudrate
        self._default_baudrate = default_baudrate
        self._run_baudrate = run_baudrate
        self._uart.baudrate = default_baudrate

        self._reset_pin = reset_pin
        self._rts_pin = rts_pin
        if self._reset_pin:
            self._reset_pin.direction = Direction.OUTPUT
            self._reset_pin.value = True
        if self._rts_pin:
            self._rts_pin.direction = Direction.OUTPUT
        #self.hw_flow(True)

        self._debug = debug
        self._versionstrings = []
        self._version = None
        self._ipdpacket = bytearray(1500)
        self._ifconfig = []
        self._initialized = False
        self._conntype = None
        self._use_cipstatus = use_cipstatus
        print("DONE INIT")

    def begin(self) -> None:
        """Initialize the module by syncing, resetting if necessary, setting up
        the desired baudrate, turning on single-socket mode, and configuring
        SSL support. Required before using the module but we dont do in __init__
        because this can throw an exception."""
        # Connect and sync
        print("begin!!!!")
        for _ in range(3):
            print("TRY", _)
            try:
                self.echo(False)
                # set flow control if required
                print("BAUD RATE ",self._run_baudrate)
                self.baudrate = self._run_baudrate
                # get and cache versionstring
                print("GET VERSION")
                self.get_version()
                try:
                    self.at_response("AT+CWSTATE?", retries=1, timeout=3)
                except OKError:
                    # ESP8285's use CIPSTATUS and have no CWSTATE or CWIPSTATUS functions
                    self._use_cipstatus = True
                    if self._debug:
                        print("No CWSTATE support, using CIPSTATUS, it's ok!")

                self._initialized = True
                print("INITIALIZED DONE")
                return
            except OKError:
                pass  # retry

    def connect(
        self, secrets: Dict[str, Union[str, int]], timeout: int = 15, retries: int = 3
    ) -> None:
        """Repeatedly try to connect to an access point with the details in
        the passed in 'secrets' dictionary. Be sure 'ssid' and 'password' are
        defined in the secrets dict! If 'timezone' is set, we'll also configure
        SNTP"""
        # Connect to WiFi if not already
        try:
            if not self._initialized:
                self.begin()
            AP = self.remote_AP  # pylint: disable=invalid-name
            if AP[0] != secrets["ssid"]:
                self.join_AP(
                    secrets["ssid"],
                    secrets["password"],
                    timeout=timeout,
                    retries=retries,
                )
                print("Connected to", secrets["ssid"])
                if "timezone" in secrets:
                    tzone = secrets["timezone"]
                    ntp = None
                    if "ntp_server" in secrets:
                        ntp = secrets["ntp_server"]
                    self.sntp_config(True, tzone, ntp)
                print("My IP Address:", self.local_ip)
            else:
                print("Already connected to", AP[0])
            return  # yay!
        except (RuntimeError, OKError) as exp:
            print("Failed to connect\n", exp)
            raise

    def hard_reset(self):
        pass

    def echo(self, echo: bool) -> None:
        """Set AT command echo on or off"""
        if echo:
            self.at_response("ATE1", timeout=1)
        else:
            self.at_response("ATE0", timeout=1)

    @property
    def is_connected(self) -> bool:
        """Initialize module if not done yet, and check if we're connected to
        an access point, returns True or False"""
        if not self._initialized:
            self.begin()
        try:
            self.echo(False)
            self.baudrate = self.baudrate
            stat = self.status
            if stat in (
                self.STATUS_APCONNECTED,
                self.STATUS_SOCKETOPEN,
                self.STATUS_SOCKETCLOSED,
            ):
                if self._debug:
                    print("is_connected(): status says connected")
                return True
        except (OKError, RuntimeError):
            pass
        if self._debug:
            print("is_connected(): status says not connected")
        return False


    @property
    def status_wifi(self) -> Union[int, None]:
        """The WIFI connection status number (see AT+CWSTATE datasheet for meaning)"""
        replies = self.at_response("AT+CWSTATE?", timeout=5).split(b"\r\n")
        for reply in replies:
            if reply.startswith(b"+CWSTATE:"):
                state_info = reply.split(b",")
                if self._debug:
                    print(
                        f"State reply is {reply}, state_info[1] is {int(state_info[0][9:10])}"
                    )
                return int(state_info[0][9:10])
        return None



    @property
    def version(self) -> Union[str, None]:
        """The cached version string retrieved via the AT+GMR command"""
        return self._version

    def get_version(self) -> Union[str, None]:
        """Request the AT firmware version string and parse out the
        version number"""
        print("get_version---->")
        reply = self.at_response("AT+GMR", timeout=3).strip(b"\r\n")
        print("REPLY", reply)
        self._version = None
        for line in reply.split(b"\r\n"):
            if line:
                self._versionstrings.append(str(line, "utf-8"))
                # get the actual version out
                if b"AT version:" in line:
                    self._version = str(line, "utf-8")
        print("VERSION ",self._version)
        return self._version

    @property
    def mode(self) -> Union[int, None]:
        """What mode we're in, can be MODE_STATION, MODE_SOFTAP or MODE_SOFTAPSTATION"""
        if not self._initialized:
            self.begin()
        replies = self.at_response("AT+CWMODE?", timeout=5).split(b"\r\n")
        for reply in replies:
            if reply.startswith(b"+CWMODE:"):
                return int(reply[8:])
        raise RuntimeError("Bad response to CWMODE?")

    @mode.setter
    def mode(self, mode: int) -> None:
        """Station or AP mode selection, can be MODE_STATION, MODE_SOFTAP or MODE_SOFTAPSTATION"""
        if not self._initialized:
            self.begin()
        if not mode in (1, 2, 3):
            raise RuntimeError("Invalid Mode")
        self.at_response("AT+CWMODE=%d" % mode, timeout=3)

    @property
    def conntype(self) -> Union[str, None]:
        """The configured connection-type"""
        return self._conntype

    @conntype.setter
    def conntype(self, conntype: str) -> None:
        """set connection-type for subsequent socket_connect()"""
        self._conntype = conntype

    @property
    def local_ip(self) -> Union[str, None]:
        """Our local IP address as a dotted-quad string"""
        reply = self.at_response("AT+CIFSR").strip(b"\r\n")
        for line in reply.split(b"\r\n"):
            if line and line.startswith(b'+CIFSR:STAIP,"'):
                return str(line[14:-1], "utf-8")
        raise RuntimeError("Couldn't find IP address")

    def ping(self, host: str) -> Union[int, None]:
        """Ping the IP or hostname given, returns ms time or None on failure"""
        reply = self.at_response('AT+PING="%s"' % host.strip('"'), timeout=5)
        for line in reply.split(b"\r\n"):
            if line and line.startswith(b"+"):
                try:
                    if line[1:5] == b"PING":
                        return int(line[6:])
                    return int(line[1:])
                except ValueError:
                    return None
        raise RuntimeError("Couldn't ping")

    def nslookup(self, host: str) -> Union[str, None]:
        """Return a dotted-quad IP address strings that matches the hostname"""
        reply = self.at_response('AT+CIPDOMAIN="%s"' % host.strip('"'), timeout=3)
        for line in reply.split(b"\r\n"):
            if line and line.startswith(b"+CIPDOMAIN:"):
                return str(line[11:], "utf-8").strip('"')
        raise RuntimeError("Couldn't find IP address")

    def at_response(self, at_cmd: str, timeout: int = 5, retries: int = 3) -> bytes:
        for _ in range(retries):
            self._uart.write(bytes(at_cmd, "utf-8"))
            self._uart.write(b"\x0d\x0a")
            stamp = time.monotonic()
            response = b""
            while (time.monotonic() - stamp) < timeout:
                if self._uart.in_waiting > 0:
                    response += self._uart.readline()
                    if response[-4:] == b"OK\r\n":
                        break
                    if response[-7:] == b"ERROR\r\n":
                        break
            return response

    # *************************** SNTP SETUP ****************************

    def sntp_config(
        self, enable: bool, timezone: Optional[int] = None, server: Optional[str] = None
    ) -> None:
        """Configure the built in ESP SNTP client with a UTC-offset number (timezone)
        and server as IP or hostname."""
        cmd = "AT+CIPSNTPCFG="
        if enable:
            cmd += "1"
        else:
            cmd += "0"
        if timezone is not None:
            cmd += ",%d" % timezone
        if server is not None:
            cmd += ',"%s"' % server
        self.at_response(cmd, timeout=3)

    @property
    def sntp_time(self) -> Union[bytes, None]:
        """Return a string with time/date information using SNTP, may return
        1970 'bad data' on the first few minutes, without warning!"""
        replies = self.at_response("AT+CIPSNTPTIME?", timeout=5).split(b"\r\n")
        for reply in replies:
            if reply.startswith(b"+CIPSNTPTIME:"):
                return reply[13:]
        return None


    def scan_APs(  # pylint: disable=invalid-name
        self, retries: int = 3
    ) -> Union[List[List[bytes]], None]:
        """Ask the module to scan for access points and return a list of lists
        with name, RSSI, MAC addresses, etc"""
        for _ in range(retries):
            try:
                if self.mode != self.MODE_STATION:
                    self.mode = self.MODE_STATION
                scan = self.at_response("AT+CWLAP", timeout=5).split(b"\r\n")
            except RuntimeError:
                continue
            routers = []
            for line in scan:
                if line.startswith(b"+CWLAP:("):
                    router = line[8:-1].split(b",")
                    for i, val in enumerate(router):
                        router[i] = str(val, "utf-8")
                        try:
                            router[i] = int(router[i])
                        except ValueError:
                            router[i] = router[i].strip('"')  # its a string!
                    routers.append(router)
            return routers


    @property
    def remote_AP(self) -> List[Union[int, str, None]]:  # pylint: disable=invalid-name
        """The name of the access point we're connected to, as a string"""
        stat = self.status
        if stat != self.STATUS_APCONNECTED:
            return [None] * 4
        replies = self.at_response("AT+CWJAP?", timeout=10).split(b"\r\n")
        for reply in replies:
            print("REPLY ", type(reply))
            if not str(reply).startswith("+CWJAP:"):
                continue
            reply = reply[7:].split(b",")
            for i, val in enumerate(reply):
                reply[i] = str(val, "utf-8")
                try:
                    reply[i] = int(reply[i])
                except ValueError:
                    reply[i] = reply[i].strip('"')  # its a string!
            return reply
        return [None] * 4

    def join_AP(  # pylint: disable=invalid-name
        self, ssid: str, password: str, timeout: int = 15, retries: int = 3
    ) -> None:
        """Try to join an access point by name and password, will return
        immediately if we're already connected and won't try to reconnect"""
        # First make sure we're in 'station' mode so we can connect to AP's
        if self._debug:
            print("In join_AP()")
        if self.mode != self.MODE_STATION:
            self.mode = self.MODE_STATION

        router = self.remote_AP
        if router and router[0] == ssid:
            return  # we're already connected!
        reply = self.at_response(
            'AT+CWJAP="' + ssid + '","' + password + '"',
            timeout=timeout,
            retries=retries,
        )
        if b"WIFI CONNECTED" not in reply:
            print("no CONNECTED")
            raise RuntimeError("Couldn't connect to WiFi")
        if b"WIFI GOT IP" not in reply:
            print("no IP")
            raise RuntimeError("Didn't get IP address")
        return

    # *************************** WIFI SETUP ****************************

    @property
    def is_connected(self) -> bool:
        """Initialize module if not done yet, and check if we're connected to
        an access point, returns True or False"""
        if not self._initialized:
            self.begin()
        try:
            self.echo(False)
            self.baudrate = self.baudrate
            stat = self.status
            if stat in (
                self.STATUS_APCONNECTED,
                self.STATUS_SOCKETOPEN,
                self.STATUS_SOCKETCLOSED,
            ):
                if self._debug:
                    print("is_connected(): status says connected")
                return True
        except (OKError, RuntimeError):
            pass
        if self._debug:
            print("is_connected(): status says not connected")
        return False

    # pylint: disable=too-many-branches
    # pylint: disable=too-many-return-statements
    @property
    def status(self) -> Union[int, None]:
        """The IP connection status number (see AT+CIPSTATUS datasheet for meaning)"""
        if self._use_cipstatus:
            replies = self.at_response("AT+CIPSTATUS", timeout=5).split(b"\r\n")
            for reply in replies:
                if reply.startswith(b"STATUS:"):
                    if self._debug:
                        print(f"CIPSTATUS state is {int(reply[7:8])}")
                    return int(reply[7:8])
        else:
            status_w = self.status_wifi
            status_s = self.status_socket

            # debug only, Check CIPSTATUS messages against CWSTATE/CIPSTATE
            if self._debug:
                replies = self.at_response("AT+CIPSTATUS", timeout=5).split(b"\r\n")
                for reply in replies:
                    if reply.startswith(b"STATUS:"):
                        cipstatus = int(reply[7:8])
                print(
                    f"STATUS: CWSTATE: {status_w}, CIPSTATUS: {cipstatus}, CIPSTATE: {status_s}"
                )

            # Produce a cipstatus-compatible status code
            # Codes are not the same between CWSTATE/CIPSTATUS so in some combinations
            # we just pick what we hope is best.
            if status_w in (
                self.STATUS_WIFI_NOTCONNECTED,
                self.STATUS_WIFI_DISCONNECTED,
            ):
                if self._debug:
                    print(f"STATUS returning {self.STATUS_NOTCONNECTED}")
                return self.STATUS_NOTCONNECTED

            if status_s == self.STATUS_SOCKET_OPEN:
                if self._debug:
                    print(f"STATUS returning {self.STATUS_SOCKETOPEN}")
                return self.STATUS_SOCKETOPEN

            if status_w == self.STATUS_WIFI_APCONNECTED:
                if self._debug:
                    print(f"STATUS returning {self.STATUS_APCONNECTED}")
                return self.STATUS_APCONNECTED

            # handle extra codes from CWSTATE
            if status_w == 0:  # station has not started any Wi-Fi connection.
                if self._debug:
                    print("STATUS returning 1")
                return 1  # this cipstatus had no previous handler variable

            # pylint: disable=line-too-long
            if (
                status_w == 1
            ):  # station has connected to an AP, but does not get an IPv4 address yet.
                if self._debug:
                    print("STATUS returning 1")
                return 1  # this cipstatus had no previous handler variable

            if status_w == 3:  # station is in Wi-Fi connecting or reconnecting state.
                if self._debug:
                    print(f"STATUS returning {self.STATUS_NOTCONNECTED}")
                return self.STATUS_NOTCONNECTED

            if status_s == self.STATUS_SOCKET_CLOSED:
                if self._debug:
                    print(f"STATUS returning {self.STATUS_SOCKET_CLOSED}")
                return self.STATUS_SOCKET_CLOSED

        return None

    @property
    def status_wifi(self) -> Union[int, None]:
        """The WIFI connection status number (see AT+CWSTATE datasheet for meaning)"""
        replies = self.at_response("AT+CWSTATE?", timeout=5).split(b"\r\n")
        for reply in replies:
            if reply.startswith(b"+CWSTATE:"):
                state_info = reply.split(b",")
                if self._debug:
                    print(
                        f"State reply is {reply}, state_info[1] is {int(state_info[0][9:10])}"
                    )
                return int(state_info[0][9:10])
        return None

    @property
    def status_socket(self) -> Union[int, None]:
        """The Socket connection status number (see AT+CIPSTATE for meaning)"""
        replies = self.at_response("AT+CIPSTATE?", timeout=5).split(b"\r\n")
        for reply in replies:
            # If there are any +CIPSTATE lines that means it's an open socket
            if reply.startswith(b"+CIPSTATE:"):
                return self.STATUS_SOCKET_OPEN
        return self.STATUS_SOCKET_CLOSED
