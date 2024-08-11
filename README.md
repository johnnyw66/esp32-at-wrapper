
ESP32 Wrapper C3


pip3 install esptool

esptool.py --chip esp32c3 --port /dev/tty.usbmodem101 erase_flash
esptool.py --chip esp32c3 --port /dev/tty.usbmodem101 --baud 460800 write_flash -z 0x0 factory/factory_MINI-1.bin
