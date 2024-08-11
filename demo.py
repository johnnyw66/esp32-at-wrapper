
#import time
import asyncio
from queue import Queue

import serial


# Get wifi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    secrets = {
            "ssid":"MYAPSSID",
            "password":"MYAPPASSWORD",
            "phone":"+4477500000",
            "mqtt_host":"mqtt.ip.linodeusercontent.com",
            "mqtt_username":"MQTTUSER",
            "mqtt_password":"MQTTPASSWORD",
            "mqtt_port":1883
            
        }
    

DELAY_BETWEEN_AT_COMMANDS = 1


def build_mqtt_subscribe_message(data_string):
        
    # Example string
    #data_string = '+MQTTSUBRECV:0,"torratorratorra",46,{"to":"+447753432247","message":"Hello World"}'

    # Splitting the string based on commas
    parts = data_string.split(',')

    prefix = parts[0]  # +MQTTSUBRECV:0
    topic = parts[1].strip('"')  # torratorratorra
    msg_size_bytes = int(parts[2])  # 46

    # Extracting JSON object
    json_str = ','.join(parts[3:])  # Reconstruct the JSON string

    # Calculate the size of the JSON string in bytes
    json_size_calculated = len(json_str.encode('utf-8'))


    # Print comparison
    print(f"Provided Size: {msg_size_bytes} bytes")
    print(f"Calculated Size: {json_size_calculated} bytes")
    
    # Checking if they match
    if msg_size_bytes != json_size_calculated:
        print("WARNING ... Sizes do not match.")
    
    return topic, json_str
            
# Demonstrate scheduler is operational.
async def heartbeat(led):
    print("Start Heartbeat")
    while True:
        await asyncio.sleep(1)
        if (led):
            led.value = not led.value

def uart_write(uart, message):
    #uart.write(message.encode('utf-8'))  # Write message to UART
    uart.write(bytes(message, 'utf-8'))

async def uart_write_loop(uart, message_queue):
    print("uart_write_loop", message_queue)
    while True:
        message = await message_queue.get()  # Wait for a message from the queue
        uart_write(uart,message)  # Write message to UART
        await asyncio.sleep(1)  # Wait for 2 seconds between messages
     

async def uart_read_loop(uart, response_queue):
    print(f"uart_read_loop queue = {response_queue}")
    while True:
        if uart.in_waiting > 0:
            data = uart.readline()
            response = data.decode('utf-8')
            await response_queue.put(response)
            #print(f"uart_read_loop: response = {response} added to response queue - size = {response_queue.qsize()}")
            
        await asyncio.sleep(0.1)  # Wait for 1 mseconds between messages


async def response_handler(response_queue, message_queue):
    print(f"response_handler queue = {response_queue}")
    while True:
        response = await response_queue.get()
        #await parse_responses(response, message_queue)
        params=response.split(',')
        print(f"debugESPAT - parse_responses:-------> {params}")

        if '+MQTTSUBRECV:' in params[0]:
            topic, sub_message = build_mqtt_subscribe_message(response)
            print(f"Received topic {topic}", sub_message)

        if '+MQTTCONNECTED:' in params[0]:
            pass
            
        if '+CWJAP:' in params[0]:
            pass

        await asyncio.sleep(1)  # Wait for 1 seconds between messages
       
     
# WiFi Management AT commands
def form_join_wifi():
    ssid, password = secrets['ssid'], secrets['password']
    command = f'AT+CWJAP="{ssid}","{password}"\r\n'
    return command

def form_disconnect_wifi():
    command = 'AT+CWQAP\r\n'
    return command

def form_get_wifi_status():
    command = 'AT+CWJAP?\r\n'
    return command

def form_scan_wifi_networks():
    command = 'AT+CWLAP\r\n'
    return command


def form_at_esp_mqtt_credentials():
    username = secrets["mqtt_username"]
    password = secrets["mqtt_password"]
    client_id = "client_id_12"
    return f'AT+MQTTUSERCFG=0,1,"{client_id}","{username}","{password}",0,0,""\r\n'

def form_at_esp_mqtt_connect():
    host = secrets["mqtt_host"]
    port = secrets["mqtt_port"]
    reconnect = 1 # 1 or 0
    return f'AT+MQTTCONN=0,"{host}",{port},{reconnect}\r\n'

def form_at_esp_subscribe(topic):
    return f'AT+MQTTSUB=0,"{topic}",1\r\n'
    
def form_at_esp_publish(topic,data,qos=1,retain=0):
    return f'AT+MQTTPUB=0,"{topic}","{data}",{qos},{retain}\r\n'




def update_status_factory(uart, dongle_stats, delay = 30):
    print("update_dongle_status... ")
    count = 1    
         
    async def update_status():
        nonlocal count
        while True:
            print(f"Update STATUS time: {dongle_stats.time}  publish:{dongle_stats}")
            resp = esp.at_response(form_at_esp_publish(f"status/{dongle_stats.name}",f"{dongle_stats}"))
            count = count + 1
            dongle_stats.update_time(delay)
            await asyncio.sleep(delay)
            
    return  update_status


async def http_get(uart, gsm_command_queue, url, port=80):
    # Extract host and path from the URL

    protocol, rest = url.split("://")
    host, path = rest.split("/", 1)
    path = "/" + path

    # Start TCP connection
    await gsm_command_queue.put(f'AT+CIPSTART="TCP","{host}",{port}\r\n')
        
    # Formulate the HTTP GET request
    http_request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        
    # Send the HTTP request
    await gsm_command_queue.put(f'AT+CIPSEND={len(http_request)}\r\n')
    await gsm_command_queue.put(http_request)
        
    # Read the HTTP response
    response = []
    while True:
        if uart.in_waiting > 0:
            line = uart.readline().decode('utf-8')
            if any(["0, CLOSE OK" in line , "CLOSED" in line]):  # Connection closed
                break
            response.append(line)
        await asyncio.sleep(1)
        
    # Close TCP connection
    await gsm_command_queue.put('AT+CIPCLOSE\r\n')
        
    return "\n".join(response)


async def fetch_page(uart, gsm_command_queue):
    url = "http://example.com/index.html"
    print(f"Fetching: {url}")
    webpage = await http_get(uart, gsm_command_queue, url)
    print(f"Web Page Response from {url}:")
    print(webpage)

async def mqtt_init(gsm_command_queue):
    await gsm_command_queue.put(form_at_esp_mqtt_credentials())
    await gsm_command_queue.put(form_at_esp_mqtt_connect())

async def subscribe(gsm_command_queue, topic):
    await gsm_command_queue.put(form_at_esp_subscribe(topic))


async def wifi_init(gsm_command_queue):
    await gsm_command_queue.put(form_join_wifi())

#  await publish(gsm_command_queue, "opportunities/111283278/status/#")



async def wifi_loop(uart, gsm_response_queue, gsm_command_queue):
    
    first_pass = True
    while True:
        try:

            if first_pass:
                print("FIRST PASS ON WIFI LOOP")
                await wifi_init(gsm_command_queue)
                await mqtt_init(gsm_command_queue)
                await subscribe(gsm_command_queue, "opportunities/111283278/status/#")
                first_pass = False
                
            if (True):
                print("wifi Loop")
                await gsm_command_queue.put('AT+CWJAP?\r\n')
                #await fetch_page(uart,gsm_command_queue)
                await asyncio.sleep(10)
                

        except (ValueError, RuntimeError) as e:
            print("Failed to get data, retrying\n", e)
            print("Resetting ESP module")
            await wifi_init(gsm_command_queue)
            continue
        

        

async def main():

    start_up_commands = [
        "AT\r\n",
        "AT+RST\r\n",
    ]   

    uart = serial.Serial("/dev/tty.usbserial-110", 115200, timeout=1)

    gsm_response_queue = Queue()
    gsm_command_queue = Queue()

    led = None

    try:
        asyncio.create_task(heartbeat(led))
        asyncio.create_task(uart_read_loop(uart, gsm_response_queue))
        asyncio.create_task(uart_write_loop(uart, gsm_command_queue))
        asyncio.create_task(response_handler(gsm_response_queue, gsm_command_queue))
        asyncio.create_task(wifi_loop(uart, gsm_response_queue, gsm_command_queue))

        for command in start_up_commands:
            await gsm_command_queue.put(command)
    except OSError:
        print('Connection failed.')
        return

    while True:
        await asyncio.sleep(5)   




try:
    asyncio.run(main())

finally:
    asyncio.new_event_loop()




