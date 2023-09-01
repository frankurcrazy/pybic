import atexit
import collections
import functools
import logging
import math
import queue
import struct
import threading
import time

import can

import pybic.cmd
import pybic.listener
from pybic.utils import Promise, format_can_message


def wait_for(cmd):
    def decorator(method):
        def _impl(self, *args, **kwargs):
            if cmd not in self._promises:
                self._promises[cmd] = collections.deque()
            promise = Promise()
            self._promises[cmd].append(promise)
            method(self, *args, *kwargs)

            return promise.result

        return _impl

    return decorator


class MessageSender:
    """Command sender queues the command sending request and create a task
    to process the command to be sent
    """

    def __init__(self, bus: can.Bus):
        self._stop = threading.Event()
        self._queue = queue.Queue(maxsize=16)
        self._logger = logging.getLogger(__name__)
        self._bus = bus

        self._thread = threading.Thread(
            target=self._worker,
        )
        self._thread.start()

        atexit.register(self.stop)

    def _worker(self) -> None:
        self._logger.info("starting worker")
        while not self._stop.is_set():
            try:
                msg = self._queue.get_nowait()
                self._bus.send(msg)
                self._queue.task_done()
                self._logger.debug(f"message {format_can_message(msg)} sent.")
            except queue.Empty:
                time.sleep(0.1)
                continue

        self._logger.info("worker stopped")

    def send(self, msg: can.message.Message) -> None:
        self._queue.put(msg)

    def stop(self):
        self._logger.info(f"stopping message sender")
        self._stop.set()
        self._thread.join()


class Bic:
    def __init__(self, bus: can.Bus, arbitration_id: int = 0xC0300):
        self._bus = bus
        self._arbitration_id = arbitration_id
        self._msg_sender = MessageSender(bus=bus)
        self._listener = pybic.listener.BicListener(bic=self)
        can.Notifier(bus, [self._listener])

        self._promises = {}

        # prefetch scaling factor
        self.scaling_factor

    def _msg_factory(self, command, data=None) -> can.message.Message:
        data_bytes = struct.pack("<H", command[0])

        if data:
            data_bytes += data

        return can.Message(
            arbitration_id=self._arbitration_id, is_extended_id=True, data=data_bytes
        )

    @property
    @wait_for("operation")
    def operation(self):
        """query the operation of bic"""

        msg = self._msg_factory(command=pybic.cmd.OPERATION)
        self._msg_sender.send(msg)

    @operation.setter
    def operation(self, value: bool) -> None:
        """set the operation of bic

        arguments:
            value: 1 for on, 0 for off
        """

        data = b"\x01" if value else b"\x00"
        msg = self._msg_factory(command=pybic.cmd.OPERATION, data=data)
        self._msg_sender.send(msg)

    @property
    @functools.lru_cache
    @wait_for("scaling_factor")
    def scaling_factor(self):
        """query the scaling factor of the bic"""
        msg = self._msg_factory(command=pybic.cmd.SCALING_FACTOR)
        self._msg_sender.send(msg)

    @property
    @wait_for("v_in")
    def v_in(self):
        """query the v_out of the bic"""
        msg = self._msg_factory(command=pybic.cmd.READ_VIN)

        self._msg_sender.send(msg)

    @property
    @wait_for("reverse_v_out")
    def reverse_v_out(self):
        """query the reverse_v_out of the bic"""
        msg = self._msg_factory(command=pybic.cmd.REVERSE_VOUT_SET)

        self._msg_sender.send(msg)

    @reverse_v_out.setter
    def reverse_v_out(self, value):
        """set the reverse_v_out of the bic"""
        if value < 38 or value > 65:
            raise ValueError("reverse_v_out should be [38, 65]")

        rev_vout_scaled = math.floor(value / self.scaling_factor["v_out"])
        rev_vout_bytes = struct.pack("<H", rev_vout_scaled)

        msg = self._msg_factory(command=pybic.cmd.REVERSE_VOUT_SET, data=rev_vout_bytes)

        self._msg_sender.send(msg)

    @property
    @wait_for("reverse_i_out")
    def reverse_i_out(self):
        """query the reverse_i_out of the bic"""
        msg = self._msg_factory(command=pybic.cmd.REVERSE_IOUT_SET)

        self._msg_sender.send(msg)

    @reverse_i_out.setter
    def reverse_i_out(self, value):
        """set the reverse_i_out of the bic"""
        if value < 0.45 or value > 38.3:
            raise ValueError("reverse_i_out should be [0.45, 38.3]")

        rev_iout_scaled = math.floor(value / self.scaling_factor["i_out"])
        rev_iout_bytes = struct.pack("<H", rev_iout_scaled)

        msg = self._msg_factory(command=pybic.cmd.REVERSE_IOUT_SET, data=rev_iout_bytes)

        self._msg_sender.send(msg)

    @property
    @wait_for("v_out")
    def v_out(self):
        """query the v_out of the bic"""
        msg = self._msg_factory(command=pybic.cmd.READ_VOUT)

        self._msg_sender.send(msg)

    @v_out.setter
    def v_out(self, value):
        """set the v_out of the bic"""
        if value < 38 or value > 65:
            raise ValueError("v_out should be [38, 65]")

        vout_scaled = math.floor(value / self.scaling_factor["v_out"])
        vout_bytes = struct.pack("<H", vout_scaled)

        msg = self._msg_factory(command=pybic.cmd.VOUT_SET, data=vout_bytes)

        self._msg_sender.send(msg)

    @property
    @wait_for("i_out")
    def i_out(self):
        """query the i_out of the bic"""
        msg = self._msg_factory(command=pybic.cmd.READ_IOUT)

        self._msg_sender.send(msg)

    @i_out.setter
    def i_out(self, value):
        """set the i_out of the bic"""
        if value < 0.45 or value > 49.5:
            raise ValueError("i_out should be [0.45, 49.5]")

        vout_scaled = math.floor(value / self.scaling_factor["i_out"])
        vout_bytes = struct.pack("<H", vout_scaled)

        msg = self._msg_factory(command=pybic.cmd.IOUT_SET, data=vout_bytes)

        self._msg_sender.send(msg)

    @property
    @wait_for("system_config")
    def system_config(self):
        msg = self._msg_factory(command=pybic.cmd.SYSTEM_CONFIG)

        self._msg_sender.send(msg)

    @system_config.setter
    def system_config(self, value: dict) -> None:
        if "can_ctrl" not in value:
            raise ValueError("can_ctrl key not found")
        if "operation_init" not in value:
            raise ValueError("operation_init key not found")

        data = bytes(
            [(value["can_ctrl"] & 0x01) + ((value["operation_init"] & 0x06) << 1), 0x00]
        )

        msg = self._msg_factory(command=pybic.cmd.SYSTEM_CONFIG, data=data)

        self._msg_sender.send(msg)

    @property
    @wait_for("bidirectional_config")
    def bidirectional_config(self):
        msg = self._msg_factory(command=pybic.cmd.BIDIRECTIONAL_CONFIG)

        self._msg_sender.send(msg)

    @bidirectional_config.setter
    def bidirectional_config(self, value: dict) -> None:
        if "mode" not in value:
            raise ValueError("mode key not found")

        msg = self._msg_factory(
            command=pybic.cmd.BIDIRECTIONAL_CONFIG, data=bytes([value["mode"], 0x00])
        )

        self._msg_sender.send(msg)

    @property
    @wait_for("direction_ctrl")
    def direction_ctrl(self):
        msg = self._msg_factory(command=pybic.cmd.DIRECTION_CTRL)

        self._msg_sender.send(msg)

    @direction_ctrl.setter
    def direction_ctrl(self, value: int) -> None:
        msg = self._msg_factory(
            command=pybic.cmd.DIRECTION_CTRL,
            data=bytes(
                [
                    value,
                ]
            ),
        )

        self._msg_sender.send(msg)

    @property
    @wait_for("temperature")
    def temperature(self):
        """query the temperature of the bic"""
        msg = self._msg_factory(command=pybic.cmd.READ_TEMPERATURE)

        self._msg_sender.send(msg)

    @property
    @wait_for("fault_status")
    def fault_status(self):
        """query the fault status of the bic"""
        msg = self._msg_factory(command=pybic.cmd.FAULT_STATUS)

        self._msg_sender.send(msg)

    @property
    @functools.lru_cache
    @wait_for("mfr_id_b0b5")
    def mfr_id_b0b5(self):
        """query the mfr_id_b0b5 of the bic"""
        msg = self._msg_factory(command=pybic.cmd.MFR_ID_B0B5)

        self._msg_sender.send(msg)

    @property
    @functools.lru_cache
    @wait_for("mfr_id_b6b11")
    def mfr_id_b6b11(self):
        """query the mfr_id_b6b11 of the bic"""
        msg = self._msg_factory(command=pybic.cmd.MFR_ID_B6B11)

        self._msg_sender.send(msg)

    @property
    def mfr_id(self):
        return self.mfr_id_b0b5 + self.mfr_id_b6b11

    @property
    @functools.lru_cache
    @wait_for("mfr_model_b0b5")
    def mfr_model_b0b5(self):
        """query the mfr_model_b0b5 of the bic"""
        msg = self._msg_factory(command=pybic.cmd.MFR_MODEL_B0B5)

        self._msg_sender.send(msg)

    @property
    @functools.lru_cache
    @wait_for("mfr_model_b6b11")
    def mfr_model_b6b11(self):
        """query the mfr_model_b6b11 of the bic"""
        msg = self._msg_factory(command=pybic.cmd.MFR_MODEL_B6B11)

        self._msg_sender.send(msg)

    @property
    def mfr_model(self):
        return (self.mfr_model_b0b5 + self.mfr_model_b6b11).strip()

    @property
    @functools.lru_cache
    @wait_for("mfr_serial_b0b5")
    def mfr_serial_b0b5(self):
        """query the mfr_serial_b0b5 of the bic"""
        msg = self._msg_factory(command=pybic.cmd.MFR_SERIAL_B0B5)

        self._msg_sender.send(msg)

    @property
    @functools.lru_cache
    @wait_for("mfr_serial_b6b11")
    def mfr_serial_b6b11(self):
        """query the mfr_serial_b6b11 of the bic"""
        msg = self._msg_factory(command=pybic.cmd.MFR_SERIAL_B6B11)

        self._msg_sender.send(msg)

    @property
    def mfr_serial(self):
        return self.mfr_serial_b0b5 + self.mfr_serial_b6b11

    @property
    @functools.lru_cache
    @wait_for("mfr_date_b0b5")
    def mfr_date(self):
        """query the mfr_date_b0b5 of the bic"""
        msg = self._msg_factory(command=pybic.cmd.MFR_DATE_B0B5)

        self._msg_sender.send(msg)

    @property
    @functools.lru_cache
    @wait_for("mfr_revision_b0b5")
    def mfr_revision(self):
        """query the mfr_revision_b0b5 of the bic"""
        msg = self._msg_factory(command=pybic.cmd.MFR_REVISION_B0B5)

        self._msg_sender.send(msg)

    @property
    @functools.lru_cache
    @wait_for("mfr_location_b0b2")
    def mfr_location(self):
        """query the mfr_location_b0b2 of the bic"""
        msg = self._msg_factory(command=pybic.cmd.MFR_LOCATION_B0B2)

        self._msg_sender.send(msg)
