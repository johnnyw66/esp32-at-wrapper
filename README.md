
ESP32 Wrapper C3

Download binary

https://docs.espressif.com/projects/esp-at/en/latest/esp32c3/AT_Binary_Lists/esp_at_binaries.html

Flash ESP32

pip3 install esptool

esptool.py --chip esp32c3 --port /dev/tty.usbmodem101 erase_flash

esptool.py --chip esp32c3 --port /dev/tty.usbmodem101 --baud 460800 write_flash -z 0x0 factory/factory_MINI-1.bin

Upload Micropython Code to Pico 2

Create folder 

espatcontrol

Upload files
espatcontrol.py to the folder espatcontrol
simpletest.py to root folder




Wire ESP32 to Pico 2


