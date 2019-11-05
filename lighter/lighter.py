#!/usr/bin/env python3.5
import datetime
import random
import time
import logging

import pytz as pytz
from RPi import GPIO
from smbus import SMBus


logging.basicConfig(
    level=logging.DEBUG,
    format="lighter: %(asctime)s;%(levelname)s;%(message)s", datefmt="%Y-%m-%d %H:%M:%S",
    filename="/var/log/lighter.log",
)
logger = logging.getLogger("lighter")


class I2C:
    CHAN_1 = 0b1000000  # 0x40 (foto-resistor)
    CHAN_2 = 0b1000001  # 0x41 (thermistor)
    CHAN_3 = 0b1000010  # 0x42 (not connected)
    CHAN_4 = 0b1000011  # 0x43 (variable resistor)

    CHAN_OUT = 0b1000000

    def __init__(self, dev_addr, bus_id):
        self.dev_addr = dev_addr
        self.bus = SMBus(bus_id)
        self.write_out(0)

    def read_chan(self, chan_name):
        self.bus.write_byte(self.dev_addr, chan_name)

        # skipping 2 history values from chan
        self.bus.read_byte(self.dev_addr)
        self.bus.read_byte(self.dev_addr)

        value = self.bus.read_byte(self.dev_addr)
        return value

    def write_out(self, value):
        self.bus.write_byte_data(self.dev_addr, I2C.CHAN_OUT, value)


class Daytime:
    NIGHT = 'night'
    EVENING = 'evening'
    DAY = 'day'

    THRESHOLDS = {
        NIGHT: 4,
        EVENING: 20,
    }


I2C_DEV_ADDR = 0x48
I2C_BUS_ID = 1
PHOTO_SENSOR_CHAN = I2C.CHAN_1
TEMP_SENSOR_CHAN = I2C.CHAN_2
SWITCHER_PIN = 26

TZ = pytz.timezone('Europe/Moscow')

LIGHT_ON_MIN_TIME = datetime.time(19, 0, tzinfo=TZ)
LIGHT_ON_MAX_DELAY = 60 * 60

LIGHT_OFF_MIN_TIME = datetime.time(0, 30, tzinfo=TZ)
LIGHT_OFF_MAX_DELAY = 2 * 60 * 60


class Lamp:
    ON = 'ON'
    OFF = 'OFF'

    MIN_SWITCH_DELAY = 10

    state = OFF
    last_switch_time = 0

    def set_state(self, state):
        if self.state == state:
            return

        if time.time() - self.last_switch_time < self.MIN_SWITCH_DELAY:
            logger.warning('Switched less then 10 seconds ago, ignoring switch')
            return

        if state == self.OFF:
            GPIO.output(SWITCHER_PIN, GPIO.HIGH)
        else:
            GPIO.output(SWITCHER_PIN, GPIO.LOW)

        self.state = state
        self.last_switch_time = time.time()

    @property
    def is_on(self):
        return self.state == self.ON

    @property
    def is_off(self):
        return self.state == self.OFF


class Sensor:
    def __init__(self, i2c, photo_sensor_channel, temp_sensor_channel):
        self.photo_sensor_channel = photo_sensor_channel
        self.temp_sensor_channel = temp_sensor_channel
        self.i2c = i2c
        self.latest_values = []

    def _read_sensor_value(self, chan):
        value = self.i2c.read_chan(chan)
        value = 255 - value
        return value

    def set_sensor_debug(self, value):
        self.i2c.write_out(value)

    def get_daytime(self):
        value = self._read_sensor_value(self.photo_sensor_channel)

        daytime = Daytime.DAY
        for dt, threshold in sorted(Daytime.THRESHOLDS.items(), key=lambda x: x[1]):
            if value < threshold:
                daytime = dt
                break

        # need 3 equal values to assume that night has come
        self.latest_values.append(daytime)
        if len(set(self.latest_values)) > 1:
            daytime = self.latest_values[-2]

        logger.debug(
            "Photo sensor value is: %d, latest values are `%s`, assuming it is daytime: %s",
            value, self.latest_values, daytime
        )

        if len(self.latest_values) > 3:
            self.latest_values = self.latest_values[1:]

        return daytime


class Lighter:
    state_change_plan = None

    def __init__(self):
        i2c = I2C(I2C_DEV_ADDR, I2C_BUS_ID)
        self.light_sensor = Sensor(i2c, PHOTO_SENSOR_CHAN, TEMP_SENSOR_CHAN)
        self.lamp = Lamp()

        now = Lighter.get_now()
        desired_state = self.get_desired_state(now)

        logger.info('Initializing Lighter. Desired state for now is `%s`', desired_state)
        self.lamp.set_state(desired_state)

    @staticmethod
    def get_now():
        return datetime.datetime.now(tz=TZ)

    @staticmethod
    def get_today_turn_on_min_time(now):
        turn_on_min_time = now.replace(
            hour=LIGHT_ON_MIN_TIME.hour,
            minute=LIGHT_ON_MIN_TIME.minute,
            second=0,
            microsecond=0,
        )
        return turn_on_min_time

    @staticmethod
    def get_next_turn_on_min_time(now):
        turn_on_min_time = Lighter.get_today_turn_on_min_time(now)
        if now > turn_on_min_time:
            turn_on_min_time += datetime.timedelta(days=1)

        return turn_on_min_time

    @staticmethod
    def get_tommorow_turn_on_min_time(now):
        turn_on_min_time = Lighter.get_today_turn_on_min_time(now)
        turn_on_min_time += datetime.timedelta(days=1)

        return turn_on_min_time

    @staticmethod
    def get_today_turn_off_min_time(now):
        turn_off_min_time = now.replace(
            hour=LIGHT_OFF_MIN_TIME.hour,
            minute=LIGHT_OFF_MIN_TIME.minute,
            second=0,
            microsecond=0,
        )

        return turn_off_min_time

    @staticmethod
    def get_next_turn_off_min_time(now):
        turn_off_min_time = Lighter.get_today_turn_off_min_time(now)
        if now > turn_off_min_time:
            turn_off_min_time += datetime.timedelta(days=1)

        return turn_off_min_time

    @staticmethod
    def get_desired_state_by_time(now):
        sorted_times = sorted([
            (now.time(), 'now'),
            (LIGHT_ON_MIN_TIME, Lamp.ON),
            (LIGHT_OFF_MIN_TIME, Lamp.OFF),
        ])

        # we need to know what state is desired before now
        desired_state = None
        for _, state in sorted_times:
            if state == 'now':
                break
            desired_state = state

        if not desired_state:
            desired_state = sorted_times[-1][1]

        return desired_state

    def get_desired_state_by_sensor(self):
        daytime = self.light_sensor.get_daytime()
        if daytime == Daytime.NIGHT:
            return Lamp.ON
        else:
            return Lamp.OFF

    def get_desired_state(self, now):
        desired_state_by_time = Lighter.get_desired_state_by_time(now)
        desired_state_by_sensor = self.get_desired_state_by_sensor()

        if desired_state_by_sensor == desired_state_by_time:
            final_desired = desired_state_by_sensor
        else:
            final_desired = desired_state_by_time

        logger.debug(
            'Desired by time: `%s`, desired by sensor: `%s`, final desired = `%s`',
            desired_state_by_time, desired_state_by_sensor, final_desired
        )
        return final_desired

    def execute_planned_changes(self, now):
        if not self.state_change_plan:
            return False

        desired_time, desired_state = self.state_change_plan
        if now > desired_time:
            logger.info('Change planned for now, switching lamp to `%s`', desired_state)
            self.lamp.set_state(desired_state)
        else:
            logger.debug('Change planned at %s, waiting', desired_time)
            return True

        self.state_change_plan = None
        return True

    def plan_state_change(self, now, desired_state):
        if desired_state == Lamp.ON:
            time_to_off = Lighter.get_next_turn_off_min_time(now)
            latest_time_to_on = now + datetime.timedelta(seconds=LIGHT_ON_MAX_DELAY)
            latest_time_change_state = min(time_to_off, latest_time_to_on)
        else:
            time_to_on = Lighter.get_next_turn_on_min_time(now)
            latest_time_to_off = now + datetime.timedelta(seconds=LIGHT_OFF_MAX_DELAY)
            latest_time_change_state = min(time_to_on, latest_time_to_off)

        if latest_time_change_state < now:
            logger.error(
                'Latest time for switching `%s` is %s, but its %s already',
                desired_state, latest_time_change_state, now
            )
            return

        desired_delay = int((latest_time_change_state - now).total_seconds() * random.random())
        desired_time = now + datetime.timedelta(seconds=desired_delay)

        self.state_change_plan = (desired_time, desired_state)
        logger.info('Planned switching lamp to `%s` at %s', desired_state, desired_time)

    def run(self):
        while True:
            time.sleep(60)

            now = Lighter.get_now()

            if self.execute_planned_changes(now):
                continue

            desired_state = self.get_desired_state(now)
            if self.lamp.state != desired_state:
                self.plan_state_change(now, desired_state)

    def cleanup(self):
        self.lamp.set_state(Lamp.OFF)
        logger.info('STOPPED AUTO LIGHTER')


if __name__ == '__main__':
    logger.info('STARTED AUTO LIGHTER')
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SWITCHER_PIN, GPIO.OUT, initial=GPIO.HIGH)
    lighter = Lighter()
    try:
        lighter.run()
    finally:
        lighter.cleanup()
        GPIO.cleanup()
