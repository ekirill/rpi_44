#!/usr/bin/env python3
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
    CHAN_1 = 0b1000000
    CHAN_2 = 0b1000001
    CHAN_3 = 0b1000010
    CHAN_4 = 0b1000011

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
        NIGHT: 25,
        EVENING: 50,
    }


I2C_DEV_ADDR = 0x48
I2C_BUS_ID = 1
PHOTO_SENSOR_CHAN = I2C.CHAN_1
SWITCHER_PIN = 18

TZ = pytz.timezone('Europe/Moscow')

LIGHT_ON_MIN_TIME = datetime.time(19, 0, tzinfo=TZ)
LIGHT_ON_MAX_DELAY = 60

LIGHT_OFF_MIN_TIME = datetime.time(0, 0, tzinfo=TZ)
LIGHT_OFF_MAX_DELAY = 60


class Lamp:
    ON = 1
    OFF = 0

    MIN_SWITCH_DELAY = 10

    state = OFF
    last_switch_time = 0

    def _set_light_state(self, state):
        if time.time() - self.last_switch_time < self.MIN_SWITCH_DELAY:
            logger.warning('Switched less then 10 seconds ago, ignoring switch')
            return

        if state == self.OFF:
            GPIO.output(SWITCHER_PIN, GPIO.HIGH)
        else:
            GPIO.output(SWITCHER_PIN, GPIO.LOW)

        self.state = state
        self.last_switch_time = time.time()

    def switch_off(self):
        if self.state == self.ON:
            logger.debug('Lights OFF')
            self._set_light_state(self.OFF)

    def switch_on(self):
        if self.state == self.OFF:
            logger.debug('Lights ON')
            self._set_light_state(self.ON)


class LightSensor:
    def __init__(self, i2c, sensor_channel):
        self.sensor_channel = sensor_channel
        self.i2c = i2c

    def _read_sensor_value(self):
        value = self.i2c.read_chan(self.sensor_channel)
        value = 255 - value
        return value

    def set_sensor_debug(self, value):
        self.i2c.write_out(value)

    def get_daytime(self):
        value = self._read_sensor_value()

        daytime = Daytime.DAY
        for dt, threshold in Daytime.THRESHOLDS.items():
            if value < threshold:
                daytime = dt
                break

        logger.debug("Sensor value is: %d, assuming it is daytime: %s", value, datetime)

        return daytime


class LighterState:
    WAIT_NIGHT = 0
    WAIT_ON = 1
    WAIT_OFF = 2
    WAIT_MORNING = 3


class Lighter:
    state_changed = time.time()
    state = LighterState.WAIT_NIGHT

    def __init__(self):
        i2c = I2C(I2C_DEV_ADDR, I2C_BUS_ID)
        self.light_sensor = LightSensor(i2c, PHOTO_SENSOR_CHAN)
        self.lamp = Lamp()
        self.set_state(LighterState.WAIT_MORNING)

    @property
    def seconds_from_state_changed(self):
        return time.time() - self.state_changed

    def set_state(self, state):
        self.state = state
        self.state_changed = time.time()

        if state == LighterState.WAIT_OFF:
            self.lamp.switch_on()
        else:
            self.lamp.switch_off()

    @staticmethod
    def get_today_turn_on_min_time():
        turn_on_min_time = datetime.datetime.now(tz=TZ).replace(
            hour=LIGHT_ON_MIN_TIME.hour,
            minute=LIGHT_ON_MIN_TIME.minute,
            second=0,
            microsecond=0,
        )
        return turn_on_min_time

    @staticmethod
    def get_today_turn_off_min_time():
        turn_off_min_time = datetime.datetime.now(tz=TZ).replace(
            hour=LIGHT_OFF_MIN_TIME.hour,
            minute=LIGHT_OFF_MIN_TIME.minute,
            second=0,
            microsecond=0,
        )
        return turn_off_min_time

    @staticmethod
    def get_next_turn_off_min_time():
        turn_off_min_time = Lighter.get_today_turn_off_min_time()
        if turn_off_min_time < datetime.datetime.now(tz=TZ):
            turn_off_min_time += datetime.timedelta(days=1)

        return turn_off_min_time

    def run(self):
        while True:
            now = datetime.datetime.now(tz=TZ)

            if self.state == LighterState.WAIT_NIGHT:
                daytime = self.light_sensor.get_daytime()
                if daytime == Daytime.NIGHT:
                    if now > Lighter.get_today_turn_on_min_time():
                        if now >= Lighter.get_today_turn_off_min_time():
                            self.set_state(LighterState.WAIT_MORNING)
                            logger.warning("Night detected, but it's time to sleep. Waiting for morning")
                            continue

                        self.set_state(LighterState.WAIT_ON)

                        desired_turn_on_time = now + datetime.timedelta(seconds=random.random() * LIGHT_ON_MAX_DELAY)
                        time_to_sleep = max((desired_turn_on_time - now).total_seconds(), 10)

                        turn_on_time = now + datetime.timedelta(seconds=int(time_to_sleep))

                        logger.info('Night detected. Light will be turned on at %s', turn_on_time)

                        time.sleep(time_to_sleep)
                    else:
                        logger.debug('Night detected, but its too early. Doing nothing')

                time.sleep(60)
            elif self.state == LighterState.WAIT_ON:
                self.lamp.switch_on()
                self.set_state(LighterState.WAIT_OFF)

                turn_off_min_time = Lighter.get_next_turn_off_min_time()
                desired_turn_off_time = (
                    turn_off_min_time + datetime.timedelta(seconds=random.random() * LIGHT_OFF_MAX_DELAY)
                )
                time_to_sleep = max((desired_turn_off_time - now).total_seconds(), 10)
                turn_off_time = now + datetime.timedelta(seconds=int(time_to_sleep))
                logger.info('Light turned on. Will be turned off at %s', turn_off_time)

                time.sleep(time_to_sleep)
            elif self.state == LighterState.WAIT_OFF:
                self.lamp.switch_off()
                self.set_state(LighterState.WAIT_MORNING)
                logger.info('Light turned off. Waiting for morning')
                time.sleep(60)
            elif self.state == LighterState.WAIT_MORNING:
                daytime = self.light_sensor.get_daytime()
                if daytime != Daytime.NIGHT:
                    self.set_state(LighterState.WAIT_NIGHT)
                    logger.info('Morning. Waiting for night.')

                time.sleep(60)

    def cleanup(self):
        self.lamp.switch_off()
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
