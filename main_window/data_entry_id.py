from enum import Enum, auto

# Constants. PacketParser.single_sensor depends on this range matching packet IDs in spec
MIN_SINGLE_SENSOR_ID: int = 0x10
MAX_SINGLE_SENSOR_ID: int = 0x2F


class DataEntryIds(Enum):
    # Single Sensor:
    ACCELERATION_X = auto()
    ACCELERATION_Y = auto()
    ACCELERATION_Z = auto()
    PRESSURE = auto()
    BAROMETER_TEMPERATURE = auto()
    TEMPERATURE = auto()
    LATITUDE = auto()
    LONGITUDE = auto()
    GPS_ALTITUDE = auto()
    CALCULATED_ALTITUDE = auto()
    STATE = auto()
    VOLTAGE = auto()
    GROUND_ALTITUDE = auto()
    TIME = auto()
    ORIENTATION_1 = auto() # TODO Remove once dependencies can be resolved. Relates to https://trello.com/c/uFHtaN51/ https://trello.com/c/bA3RuHUC
    ORIENTATION_2 = auto() # TODO Remove
    ORIENTATION_3 = auto() # TODO Remove
    ORIENTATION_4 = auto() # TODO Remove

    # Data types
    MESSAGE = auto()
    EVENT = auto()
    CONFIG = auto()
    ORIENTATION = auto()
    BULK_SENSOR = auto()
    IS_SIM = auto()
    DEVICE_TYPE = auto()
    VERSION_ID = auto()

    # Sensors
    GPS = auto()
    BAROMETER = auto()
    ACCELEROMETER = auto()
    IMU = auto()

    # Status
    OVERALL_STATUS = auto()
    DROGUE_IGNITER_CONTINUITY = auto()
    MAIN_IGNITER_CONTINUITY = auto()
    FILE_OPEN_SUCCESS = auto()


class DataEntryValues(Enum):
    STATE_NOMINAL = auto()
    STATE_NONCRITICAL_FAILURE = auto()
    STATE_CRITICAL_FAILURE = auto()

    STATE_STANDBY = auto()
    STATE_ARMED = auto()
    STATE_ASCENT = auto()
    STATE_MACH_LOCK = auto()
    STATE_PRESSURE_DELAY = auto()
    STATE_INITIAL_DESCENT = auto()
    STATE_FINAL_DESCENT = auto()
    STATE_LANDED = auto()
    STATE_WINTER_CONTINGENCY = auto()

    # TODO Add other info stored

    # Events
    EVENT_LAUNCH = auto()
    EVENT_STAGE_SEPARATION = auto()
    EVENT_MACH_LOCK_ENTER = auto()
    EVENT_MACH_LOCK_EXIT = auto()
    EVENT_APOGEE = auto()
    EVENT_DROGUE_DEPLOY = auto()
    EVENT_MAIN_DEPLOY = auto()
    EVENT_LANDED = auto()
