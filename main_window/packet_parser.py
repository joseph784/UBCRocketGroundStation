import collections
import struct
from .device_manager import DeviceType
from io import BytesIO
from typing import Any, Callable, Dict

from . import subpacket_ids
from util.detail import LOGGER
from util.event_stats import Event
from main_window.subpacket_ids import SubpacketEnum
from .device_manager import DeviceManager

SINGLE_SENSOR_EVENT = Event('single_sensor')
CONFIG_EVENT = Event('config')

# Essentially a mini-class, to structure the header data. Doesn't merit its own class due to limited use,
# can be expanded if necessary elsewhere.
Header = collections.namedtuple('Header', ['subpacket_id', 'timestamp'])

# CONSTANTS
# TODO Extract
DEVICE_TYPE = 'ROCKET_TYPE'
IS_SIM = 'IS_SIM'
VERSION_ID = 'VERSION_ID'
VERSION_ID_LEN = 40 # TODO Could instead use passed length parameter, if this is not necessary
MESSAGE = 'MESSAGE'

HEADER_SIZE_WITH_LEN = 6
HEADER_SIZE_NO_LEN = 5

ID_TO_DEVICE = {
        0x00: DeviceType.TANTALUS_STAGE_1,
        0x01: DeviceType.TANTALUS_STAGE_2,
        0x02: DeviceType.CO_PILOT,
}


# This class takes care of converting subpacket data coming in, according to the specifications.
class PacketParser:

    def __init__(self):
        """

        :param bigEndianInts:
        :type bigEndianInts:
        :param bigEndianFloats:
        :type bigEndianFloats:
        """
        self.big_endian_ints = None
        self.big_endian_floats = None

        # Dictionary of subpacket id mapped to function to parse that data
        self.packetTypeToParser: Dict[int, Callable[[BytesIO, Header], Dict[Any, Any]]] = {
            SubpacketEnum.MESSAGE.value: self.message,
            SubpacketEnum.EVENT.value: self.event,
            SubpacketEnum.CONFIG.value: self.config,
            # SubpacketEnum.SINGLE_SENSOR.value: single_sensor,  # See loop that maps function for range of ids below
        }
        for i in subpacket_ids.get_list_of_sensor_IDs():
            self.packetTypeToParser[i] = self.single_sensor

    def set_endianness(self, big_endian_ints: bool, big_endian_floats: bool):
        self.big_endian_ints = big_endian_ints
        self.big_endian_floats = big_endian_floats

    def extract(self, byte_stream: BytesIO):
        """
        Return dict of parsed subpacket data and length of subpacket

        :param byte_stream:
        :type byte_stream:
        :return: parsed_data
        :rtype: Dict[Any, Any]
        """
        if self.big_endian_ints is None or self.big_endian_floats is None:
            raise Exception("Endianness not set before parsing")

        # header extraction
        header: Header = self.header(byte_stream)

        # data extraction
        parsed_data: Dict[Any, Any] = {}
        try:
            parsed_data = self.parse_data(byte_stream, header)
        except Exception as e:
            LOGGER.exception("Error parsing data")  # Automatically grabs and prints exception info

        parsed_data[SubpacketEnum.TIME.value] = header.timestamp

        self.big_endian_ints = None
        self.big_endian_floats = None
        return parsed_data

    def parse_data(self, byte_stream: BytesIO, header: Header) -> Dict[Any, Any]:
        """
         General data parser interface. Routes to the right parser, based on subpacket_id.

        :param byte_stream:
        :type byte_stream:
        :param header:
        :type header:
        :return:
        :rtype:
        """
        return self.packetTypeToParser[header.subpacket_id](byte_stream, header)

    def header(self, byte_stream: BytesIO) -> Header:
        """
        Header extractor helper.

        :param byte_stream:
        :type byte_stream:
        :return:
        :rtype:
        """
        # Get ID
        subpacket_id: int = byte_stream.read(1)[0]

        # check that id is valid:
        if not subpacket_ids.isSubpacketID(subpacket_id):
            LOGGER.error("Subpacket id %d not valid.", subpacket_id)
            raise ValueError("Subpacket id " + str(subpacket_id) + " not valid.")

        # Get timestamp
        timestamp: int = self.fourtoint(byte_stream.read(4))

        return Header(subpacket_id, timestamp)

    def message(self, byte_stream: BytesIO, header: Header):
        """
        Save and log an extracted message.

        :param byte_stream:
        :type byte_stream:
        :param header:
        :type header:
        :return:
        :rtype:
        """
        data: Dict = {}
        length: int = byte_stream.read(1)[0]

        # Two step: immutable int[] -> string
        byte_data = byte_stream.read(length)
        data[SubpacketEnum.MESSAGE.value] = byte_data.decode('ascii')

        # Do something with data
        LOGGER.info("Incoming message: " + str(data[SubpacketEnum.MESSAGE.value]))
        return data

    def event(self, byte_stream: BytesIO, header: Header):
        """

        :param byte_stream:
        :type byte_stream:
        :param header:
        :type header:
        :return:
        :rtype:
        """
        data: Dict = {}
        # TODO Enumerate the list of events mapped to strings somewhere? Then convert to human readable string here. https://trello.com/c/uFHtaN51/ https://trello.com/c/bA3RuHUC
        data[SubpacketEnum.EVENT.value] = byte_stream.read(1)[0]
        return data

    def config(self, byte_stream: BytesIO, header: Header):
        """

        :param byte_stream:
        :type byte_stream:
        :param header:
        :type header:
        :return:
        :rtype:
        """

        data = {}
        data[IS_SIM] = bool(byte_stream.read(1)[0])
        data[DEVICE_TYPE] = ID_TO_DEVICE[byte_stream.read(1)[0]]
        version_id = byte_stream.read(VERSION_ID_LEN)
        data[VERSION_ID] = version_id.decode('ascii')

        LOGGER.info("Config: SIM? %s, Rocket type = %s, Version ID = %s",
                    str(data[IS_SIM]),
                    str(data[DEVICE_TYPE]),
                    str(data[VERSION_ID]))

        CONFIG_EVENT.increment()
        return data

    def single_sensor(self, byte_stream: BytesIO, header: Header):
        """

        :param byte_stream:
        :type byte_stream:
        :param header:
        :type header:
        :return:
        :rtype:
        """
        subpacket_id = header.subpacket_id # TODO Review w/ https://trello.com/c/uFHtaN51 https://trello.com/c/bA3RuHUC
        data = {}
        # TODO Commented out, since apparently we pass along state, and other non-floats items, as float too??
        # if subpacket_id == SubpacketEnum.STATE.value:
        #     data[subpacket_id] = byte_list[0]
        # else:
        #     data[subpacket_id] = self.fourtofloat(byte_list[0])
        data[subpacket_id] = self.fourtofloat(byte_stream.read(4))

        SINGLE_SENSOR_EVENT.increment()
        return data
        
    def register_packet(self, packetType: int, parsing_fn: Callable[[BytesIO, Header], Dict[Any, Any]]):
        self.packetTypeToParser[packetType] = parsing_fn

    # TODO Put these in utils folder/file?
    def fourtofloat(self, byte_list):
        """

        :param bytes:
        :type bytes:
        :return:
        :rtype:
        """
        assert len(byte_list) == 4
        data = byte_list
        b = struct.pack('4B', *data)
        c = struct.unpack('>f' if self.big_endian_floats else '<f', b)
        return c[0]

    def fourtoint(self, byte_list):
        """

        :param bytes:
        :type bytes:
        :return:
        :rtype:
        """
        assert len(byte_list) == 4
        data = byte_list
        b = struct.pack('4B', *data)
        c = struct.unpack('>I' if self.big_endian_ints else '<I', b)
        return c[0]

    def bitfrombyte(self, val: int, targetIndex: int):
        """
        Helper function. Extract bit at position targetIndex. 0 based index.

        :param val:
        :type int:
        :param targetIndex:
        :type int:
        :return: extracted bit
        :rtype: int
        """
        mask = 0b1 << targetIndex
        bit = val & mask
        bit = bit >> targetIndex
        return bit
