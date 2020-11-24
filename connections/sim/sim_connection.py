import os
import sys
import subprocess as sp
import threading
import struct
from enum import Enum
from pathlib import Path

from .hw_sim import SensorType
from ..connection import Connection, ConnectionMessage
from .stream_filter import StreamFilter
from .xbee_module_sim import XBeeModuleSim
from util.detail import LOGGER, LOCAL, EXECUTABLE_FILE_EXTENSION


class SimRxId(Enum):
    CONFIG = 0x01
    BUZZER = 0x07
    DIGITAL_PIN_WRITE = 0x50
    RADIO = 0x52
    ANALOG_READ = 0x61
    SENSOR_READ = 0x73


class SimTxId(Enum):
    RADIO = 0x52
    ANALOG_READ = 0x61
    SENSOR_READ = 0x73


LOG_HISTORY_SIZE = 500

ID_TO_SENSOR = {
    0x00: SensorType.GPS,
    0x01: SensorType.IMU,
    0x02: SensorType.ACCELEROMETER,
    0x03: SensorType.BAROMETER,
    0x04: SensorType.TEMPERATURE,
    0x05: SensorType.THERMOCOUPLE
}


class SimConnection(Connection):
    def __init__(self, executable_name, hw_sim):
        self._find_executable(executable_name)

        self.hwid = executable_name + 'SIM_CONN_HWID'
        self.callback = None

        self.bigEndianInts = None
        self.bigEndianFloats = None

        # Firmware subprocess - Closes automatically when parent (ground station) closes
        self.rocket = sp.Popen(
            self.executablePath, cwd=self.firmwareDir, stdin=sp.PIPE, stdout=sp.PIPE
        )
        self.stdout = StreamFilter(self.rocket.stdout, LOG_HISTORY_SIZE)
        self._rocket_handshake()

        # Gets endianess of ints and floats
        self._getEndianness()

        self._xbee = XBeeModuleSim()
        self._xbee.rocket_callback = self._send_radio_sim

        self._hw_sim = hw_sim

        self._shutdown_lock = threading.RLock()
        self._is_shutting_down = False

        # Thread to make communication non-blocking
        self.thread = threading.Thread(target=self._run, name="SIM", daemon=True)
        self.thread.start()

    def _rocket_handshake(self):
        assert self.stdout.read(3) == b"SYN"
        # Uncomment for FW debuggers, for a chance to attach debugger
        # input(f"Received rocket SYN; press enter to respond with ACK and continue. PID={self.rocket.pid}\n")
        self.rocket.stdin.write(b"ACK")
        self.rocket.stdin.flush()

    def send(self, hwid, data):
        if hwid != self.hwid:
            raise Exception(f"Connection does not support HWID={hwid}")
        self.broadcast(data)

    def broadcast(self, data):
        self._xbee.send_to_rocket(data)

    def _send_sim_packet(self, id_, data):
        id_ = id_.to_bytes(length=1, byteorder="big")
        length = len(data).to_bytes(length=2, byteorder="big")
        packet = id_ + length + data
        for b in packet:  # Work around for windows turning LF to CRLF
            self.rocket.stdin.write(bytes([b]))
        self.rocket.stdin.flush()

    def _send_radio_sim(self, data):
        self._send_sim_packet(SimTxId.RADIO.value, data)

    def registerCallback(self, fn):
        self.callback = fn
        self._xbee.ground_callback = self._receive

    def _receive(self, data):
        if not self.callback:
            raise Exception("Can't receive data. Callback not set.")

        message = ConnectionMessage(hwid=self.hwid, connection=self, data=data)

        self.callback(message)

    # Returns whether ints should be decoded as big endian
    def isIntBigEndian(self):  # must be thead safe
        assert self.bigEndianInts is not None
        return self.bigEndianInts

    # Returns whether floats should be decoded as big endian
    def isFloatBigEndian(self):
        assert self.bigEndianFloats is not None
        return self.bigEndianFloats

    def shutdown(self):
        with self._shutdown_lock:
            self._is_shutting_down = True

        self._xbee.shutdown()
        self._hw_sim.shutdown()

        self.rocket.kill()

        self.thread.join()  # join thread

    # AKA handle "Config" packet
    def _getEndianness(self):
        id = self.stdout.read(1)[0]
        assert id == SimRxId.CONFIG.value

        length = self._getLength()
        assert length == 8
        data = self.stdout.read(length)

        self.bigEndianInts = data[0] == 0x04
        self.bigEndianFloats = data[4] == 0xC0

        LOGGER.info(
            f"SIM: Big Endian Ints - {self.bigEndianInts}, Big Endian Floats - {self.bigEndianFloats} (HWID={self.hwid})"
        )

    def _handleBuzzer(self):
        length = self._getLength()
        assert length == 1
        data = self.stdout.read(length)

        songType = int(data[0])
        LOGGER.info(f"SIM: Bell rang with song type {songType} (HWID={self.hwid})")

    def _handleDigitalPinWrite(self):
        length = self._getLength()
        assert length == 2
        pin, value = self.stdout.read(2)

        self._hw_sim.digital_write(pin, value)
        LOGGER.info(f"SIM: Pin {pin} set to {value} (HWID={self.hwid})")

    def _handleRadio(self):
        length = self._getLength()

        if length == 0:
            LOGGER.warning(f"Empty SIM radio packet received (HWID={self.hwid})")

        data = self.stdout.read(length)
        self._xbee.recieved_from_rocket(data)

    def _handleAnalogRead(self):
        length = self._getLength()
        assert length == 1
        pin = self.stdout.read(length)[0]
        result = self._hw_sim.analog_read(pin).to_bytes(2, "big")
        self._send_sim_packet(SimTxId.ANALOG_READ.value, result)

    def _handleSensorRead(self):
        length = self._getLength()
        assert length == 1
        sensor_id = self.stdout.read(length)[0]
        sensor_data = self._hw_sim.sensor_read(ID_TO_SENSOR[sensor_id])
        endianness = ">" if self.bigEndianFloats else "<"
        result = struct.pack(f"{endianness}{len(sensor_data)}f", *sensor_data)
        self._send_sim_packet(SimTxId.SENSOR_READ.value, result)

    packetHandlers = {
        # DO NOT HANDLE "CONFIG" - it should be received only once at the start
        SimRxId.BUZZER.value: _handleBuzzer,
        SimRxId.DIGITAL_PIN_WRITE.value: _handleDigitalPinWrite,
        SimRxId.RADIO.value: _handleRadio,
        SimRxId.ANALOG_READ.value: _handleAnalogRead,
        SimRxId.SENSOR_READ.value: _handleSensorRead,
    }

    def _run(self):
        try:
            while True:

                id = self.stdout.read(1)[0]  # Returns 0 if process was killed

                if id not in SimConnection.packetHandlers.keys():
                    LOGGER.error(f"SIM protocol violation!!! Shutting down. (HWID={self.hwid})")
                    for b in self.stdout.getHistory():
                        LOGGER.error(hex(b[0]))
                    LOGGER.error("^^^^ violation.")
                    return

                # Call packet handler
                SimConnection.packetHandlers[id](self)

        except Exception as ex:
            with self._shutdown_lock:
                if not self._is_shutting_down:
                    LOGGER.exception(f"Error in SIM connection. (HWID={self.hwid})")

        LOGGER.warning(f"SIM connection thread shut down (HWID={self.hwid})")

    def _getLength(self):
        [msb, lsb] = self.stdout.read(2)
        return (msb << 8) | lsb

    def _find_executable(self, executable_name):
        flare_path = os.path.join(Path(LOCAL).parent, 'FLARE', 'avionics', 'build')

        local_path = os.path.join(LOCAL, 'FW')

        local_name = 'program' + EXECUTABLE_FILE_EXTENSION

        # Check FW (child) dir and FLARE (neighbour) dir for rocket build files
        # If multiple build files found throw exception
        neighbour_build_file = executable_name + EXECUTABLE_FILE_EXTENSION
        neighbour_build_file_exists = os.path.exists(os.path.join(flare_path, neighbour_build_file))

        child_build_file_exists = os.path.exists(os.path.join(local_path, local_name))

        if child_build_file_exists and neighbour_build_file_exists:
            raise FirmwareNotFound(
                f"Multiple build files found: {neighbour_build_file} and {local_name}")
        elif neighbour_build_file_exists:
            executable_name = neighbour_build_file
            path = flare_path
        elif child_build_file_exists:
            executable_name = local_name
            path = local_path
        else:
            raise FirmwareNotFound(f"No build files found with name {executable_name}")

        self.executablePath = os.path.join(path, executable_name)
        self.firmwareDir = path


class FirmwareNotFound(Exception):
    pass
