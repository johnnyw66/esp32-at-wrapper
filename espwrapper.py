import asyncio
import serial_asyncio
try:
    from secrets import secrets
except Exception as e:
    pass
    print("No Secrets")

class AsyncESP32ATWrapper:
    def __init__(self, port, baudrate=115200, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.reader = None
        self.writer = None
        self.keep_listening = True
        self.listen_task = asyncio.create_task(self.listen_for_at_messages())

        


    async def connect(self):
        self.reader, self.writer = await serial_asyncio.open_serial_connection(
            url=self.port, baudrate=self.baudrate)
        print(f"Connected to {self.port} at {self.baudrate} bps.")

    async def send_command(self, command):
        if not command.endswith('\r\n'):
            command += '\r\n'
        self.writer.write(command.encode())
        await self.writer.drain()
        print(f"Sent: {command.strip()}")

    async def read_response(self):
        response = await self.reader.readline()
        response = response.decode('utf-8').strip()
        print(f"Received: {response}")
        return response

    async def execute_command(self, command):
        await self.send_command(command)
        response = []
        while True:
            line = await self.read_response()
            if line in ["OK", "ERROR"]:  # Typical response terminators
                response.append(line)
                break
            response.append(line)
        return "\n".join(response)

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()
        print("Connection closed.")

    # WiFi Management Methods
    async def join_wifi(self, ssid, password):
        command = f'AT+CWJAP="{ssid}","{password}"'
        return await self.execute_command(command)

    async def disconnect_wifi(self):
        command = 'AT+CWQAP'
        return await self.execute_command(command)

    async def get_wifi_status(self):
        command = 'AT+CWJAP?'
        return await self.execute_command(command)

    async def scan_wifi_networks(self):
        command = 'AT+CWLAP'
        return await self.execute_command(command)


    async def http_get(self, url, port=80):
        # Extract host and path from the URL
        protocol, rest = url.split("://")
        host, path = rest.split("/", 1)
        path = "/" + path

        # Start TCP connection
        await self.execute_command(f'AT+CIPSTART="TCP","{host}",{port}')
        
        # Formulate the HTTP GET request
        http_request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        
        # Send the HTTP request
        await self.execute_command(f'AT+CIPSEND={len(http_request)}')
        await self.send_command(http_request)
        
        # Read the HTTP response
        response = []
        while True:
            line = await self.read_response()
            if line == "0, CLOSE OK" or line == "CLOSED":  # Connection closed
                break
            response.append(line)

        # Close TCP connection
        await self.execute_command('AT+CIPCLOSE')
        
        return "\n".join(response)

    async def listen_for_at_messages(self):
        print("LISTENING FOR MESSAGES................................")
        while self.keep_listening:
            response = await self.read_response()
            if response.startswith("+MQTTRECV"):  # MQTT message received
                print(f"MQTT Message: {response}")
            # Additional handling for other types of responses can go here
            else:
                print("DUNNO----------> ", response)
            print("><><><><><")
        print(" listen_for_at_messages TASK has STOPPED!!!!!!!!!!!!!*********************")

    def stop_listening(self):
        self.keep_listening = False

    # MQTT Methods


    async def mqtt_connect(self, broker, port, client_id, username=None, password=None):
        if username and password:
            print("Setting up MQTT credentials")
            command = f'AT+MQTTUSERCFG=0,1,"{client_id}","{username}","{password}",0,0,""'
            response = await self.execute_command(command)
            print(f"USER AND PASSWORD RESPONSE {response}")
                            
        command = f'AT+MQTTCONN=0,"{broker}",{port},1'

        return await self.execute_command(command)

    async def mqtt_subscribe(self, topic, qos=0):
        command = f'AT+MQTTSUB=0,"{topic}",{qos}'
        return await self.execute_command(command)

    async def mqtt_publish(self, topic, message, qos=0, retain=False):
        retain_flag = 1 if retain else 0
        command = f'AT+MQTTPUB=0,"{topic}","{message}",{qos},{retain_flag}'
        return await self.execute_command(command)

    async def mqtt_disconnect(self):
        command = 'AT+MQTTCLEAN=0'
        return await self.execute_command(command)




async def main():

    esp32 = AsyncESP32ATWrapper(port='/dev/tty.usbserial-110', baudrate=115200)  # Adjust the port according to your setup

    try:
        await esp32.connect()

        # Test basic communication
        response = await esp32.execute_command("AT")
        print(response)

        response = await esp32.execute_command("AT+RST")
        print(response)
        await asyncio.sleep(10)

        #response = await esp32.mqtt_disconnect()
        #print(response)
        #await asyncio.sleep(10)
              

        # Add more commands to test
        response = await esp32.execute_command("AT+GMR")  # Get version info
        print(response)

        response = await esp32.scan_wifi_networks()
        print(response)
        print("Finished - Initiating Scan")
        print(f"Secrets {secrets}")

        response = await esp32.join_wifi(secrets['ssid'], secrets['password'])

        status = None
        while not status:
            status = await esp32.get_wifi_status()
            print('STATUS = ', status)
        print("Connected!!!")

        url = "http://example.com/index.html"
        print(f"Fetching: {url}")
        webpage = await esp32.http_get(url)
        print("Web Page Response from {url}:")
        print(webpage)

        # Example using MQTT.
        #resp = await esp32.mqtt_disconnect()
        #print(resp)

        # Connect to HiveMQ public MQTT broker
        response = await esp32.mqtt_connect(secrets['mqtt_host'], 1883, "ESP32Client", username=secrets['mqtt_username'], password=secrets['mqtt_password'])
        print(f"CONNECT RESPONSE {response}")

        # Subscribe to a topic
        topic = "opportunities/111283278/status/#"
        await esp32.mqtt_subscribe(topic, qos=1)

        # Publish a message
        #message = "Hello, MQTT!"
        #await esp32.mqtt_publish("greet", message, qos=1)

        # Disconnect from the broker
        #await esp32.mqtt_disconnect()
        await asyncio.sleep(600)

    except Exception as e:
        print(f"Error: {e}")

    finally:
        await esp32.close()

if __name__ == "__main__":
    asyncio.run(main())


