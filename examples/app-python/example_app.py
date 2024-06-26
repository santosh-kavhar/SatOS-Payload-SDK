# Copyright 2023 Antaris, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import logging
import pathlib
import os
import sys
import time
import serial

from satos_payload_sdk import app_framework
from satos_payload_sdk import antaris_api_gpio as api_gpio
from satos_payload_sdk import antaris_api_can as api_can

g_GPIO_ERROR = -1
g_Uart_Baudrate = 9600
g_FileDownloadDir = "/opt/antaris/outbound/"    # path for staged file download
g_StageFileName = "SampleFile.txt"              # name of staged file

logger = logging.getLogger()


class Controller:

    def is_healthy(self):
        logger.info("Health check succeeded")
        return True

    def handle_hello_world(self, ctx):
        logger.info("Handling sequence: hello, world!")

    def handle_hello_friend(self, ctx):
        name = ctx.params
        logger.info(f"Handling sequence: hello, {name}!")

    def handle_log_location(self, ctx):
        loc = ctx.client.get_current_location()
        logger.info(f"Handling sequence: lat={loc.latitude}, lng={loc.longitude}, alt={loc.altitude}")

    def handle_power_control(self, ctx):
        print("Handling payload power")
        power_state = ctx.params                    # 0 = power off, 1 = power on
        resp = ctx.client.payload_power_control(power_state)
        logger.info(f"Power control state = {power_state}. Call response is = {resp}")
        
    # The sample program assumes 2 GPIO pins are connected back-to-back. 
    # This sequence toggles level of 'Write Pin' and then reads level of 'Read Pin'
    def handle_test_gpio(self, ctx):
        gpio_info = api_gpio.api_pa_pc_get_gpio_info()

        logger.info("Total gpio pins = %d", int(gpio_info.pin_count))

        i = 0
        # Read initial value of GPIO pins.
        # As GPIO pins are back-to-back connected, their value must be same.
        while (i < int(gpio_info.pin_count)):
            if int(gpio_info.pins[i]) != -1:
                readPin = gpio_info.pins[i];
                i += 1
                writePin = gpio_info.pins[i];

                val = api_gpio.api_pa_pc_read_gpio(int(readPin))
                if val != g_GPIO_ERROR:
                    logger.info("Initial Gpio value of pin no %d is %d ", int(readPin), val)
                else:
                    logger.info("Error in pin no %d", int(readPin))
                    return 
                # Toggle the value
                val = val ^ 1                      
                logger.info("Writing %d to pin no. %d", val, int(writePin))

                # Writing value to WritePin.
                val = api_gpio.api_pa_pc_write_gpio(int(writePin), val)
                if val != g_GPIO_ERROR:
                    logger.info("Written %d successfully to pin no %d", val, int(writePin))
                else:
                    logger.info("error in pin no %d ", int(writePin))
                    return 
                # As Read and Write pins are back-to-back connected, 
                # Reading value of Read pin to confirm GPIO success/failure
                val = api_gpio.api_pa_pc_read_gpio(int(readPin))
                if val != g_GPIO_ERROR:
                    logger.info("Final Gpio value of pin no %d is %d ", int(readPin), val)
                else:
                    logger.info("Error in pin no %d", int(readPin))
                    return
            i += 1

    # Sequence to test UART loopback. The sample program assumes Tx and Rx are connected in loopback mode.
    def handle_uart_loopback(self, ctx):
        data = ctx.params
        if data == "":
            logger.info("Using default string, as input string is empty")
            data = "Default string: Uart Tested working"

        data = data + "\n"
        uartInfo = api_gpio.api_pa_pc_get_uart_dev()
        logger.info("Total uart ports = %d", int(uartInfo.uart_port_count))

        uartPort = uartInfo.uart_dev[0]
        try: 
            ser = serial.Serial(uartPort, g_Uart_Baudrate)  # Replace '9600' with your baud rate
        except Exception as e:
            print("Error in opening serial port")
            return
        
        logger.info(f"writing data")
        # Write data to the serial port
        ser.write(data.encode('utf-8'))  # Send the data as bytes

        logger.info("Reading data")
        # Read data from the serial port
        read_data = ser.readline()
        logger.info("Data =  %s", read_data)

        # Close the serial port
        ser.close()


    def handle_stage_filedownload(self, ctx):
        logger.info("Staging file for download")
        # creating a sample text file
        new_file = g_FileDownloadDir + g_StageFileName
        with open(new_file, "w") as file:
            file.write("Testing file download with payload")
        
        # Files must be present in "/opt/antaris/outbound/" before staging them for download
        resp = ctx.client.stage_file_download(g_StageFileName)

    def handle_test_can_bus(self, ctx):
        logger.info("Test CAN bus")

        # Get Arbitration ID & data
        data = ctx.params
        parts = data.split()

        if len(parts) != 2:
            logger.info("Input format is incorrect. The format is: ")
            logger.info("Arbitration ID data[0],data[1],data[2],data[3]..data[7]") 
            logger.info("Using defaullt arbitration ID and data bytes.")
            data = "0x123 0x11,0x12,0x13,0x14,0x15,0x16,0x17"
            parts = data.split()

        # Extract arbitration ID and data bytes
        arb_id = int(parts[0], 16)
        data_str = parts[1]
        data_bytes = [int(byte, 16) for byte in data_str.split(",")]

        # Get CAN bus info from config file
        canInfo = api_can.api_pa_pc_get_can_dev()
        logger.info("Total CAN bus ports = %d", int(canInfo.can_port_count))

        # Define the CAN channel to use (assuming the first device)
        channel = canInfo.can_dev[0]
        logger.info("Starting CAN receiver port", channel)

        # Starting CAN received thread
        api_can.api_pa_pc_start_can_receiver_thread(channel)
        
        # Defining limits for data send and receive
        send_msg_limit = 10

        loopCounter = 0

        # Main loop to send CAN messages
        logger.info("Sending data in CAN bus")
        while loopCounter < send_msg_limit:
            loopCounter = loopCounter + 1
            arb_id = arb_id + 1
            api_can.api_pa_pc_send_can_message(channel, arb_id, data_bytes)
            time.sleep(1)

        logger.info("Data send = ", api_can.api_pa_pc_get_can_message_received_count())

        while api_can.api_pa_pc_get_can_message_received_count() > 0: 
            received_data = api_can.api_pa_pc_read_can_data()
            if received_data != g_GPIO_ERROR:
                print("received data =", received_data)
            else:
                print("Error in receiving data")
        
        logger.info("Completed reading")

        return 
    
def new():
    ctl = Controller()

    app = app_framework.PayloadApplication()
    app.set_health_check(ctl.is_healthy)

    # Sample function to add stats counters and names
    set_payload_values(app)

    # Note : SatOS-Payload-SDK supports sequence upto 16 characters long
    app.mount_sequence("HelloWorld", ctl.handle_hello_world)
    app.mount_sequence("HelloFriend", ctl.handle_hello_friend)
    app.mount_sequence("LogLocation", ctl.handle_log_location)
    app.mount_sequence("TestGPIO", ctl.handle_test_gpio)
    app.mount_sequence("UARTLoopback", ctl.handle_uart_loopback)
    app.mount_sequence("StageFile",ctl.handle_stage_filedownload)
    app.mount_sequence("PowerControl", ctl.handle_power_control)
    app.mount_sequence("TestCANBus", ctl.handle_test_can_bus)
    return app

def set_payload_values(payload_app):
    payload_metrics = payload_app.payload_metrics
    # Set used_counter
    payload_metrics.used_counter = 5  # Example value

    # Set counter values
    for i in range(payload_metrics.used_counter):
        payload_metrics.metrics[i].counter = i + 1 # Example value

    # Set counter_name values
    for i in range(payload_metrics.used_counter):
        payload_metrics.metrics[i].names = f"Counter {i}"  # Example value
    
    # Change counter name
    payload_metrics.define_counter(1, "MetricName_1")
    # Increment counter
    payload_metrics.inc_counter(1)

    return 

if __name__ == '__main__':
    DEBUG = os.environ.get('DEBUG')
    logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)

    app = new()

    try:
        app.run()
    except Exception as exc:
        logger.exception("payload app failed")
        sys.exit(1)
