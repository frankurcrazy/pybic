import atexit
import concurrent.futures
import logging
import struct

import can

import pybic.cmd
from pybic.utils import format_can_message

DIR_TO_CONTROLLER = 0xC0200
DIR_FROM_CONTROLLER = 0xC0300
CMD_LENGTH = 2


def convert_scaling_factor(sf):
    if sf == 0:
        return None

    return 10 ** (sf - 7)


class BicListener(can.Listener):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._logger = logging.getLogger(__name__)
        self._bic = kwargs.get("bic", None)

        self._handler_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)

        self._command_handlers = {
            pybic.cmd.OPERATION[0]: self._handle_cmd_operation,
            pybic.cmd.SCALING_FACTOR[0]: self._handle_cmd_scaling_factor,
            pybic.cmd.READ_VIN[0]: self._handle_cmd_read_vin,
            pybic.cmd.READ_IOUT[0]: self._handle_cmd_read_iout,
            pybic.cmd.REVERSE_VOUT_SET[0]: self._handle_cmd_reverse_vout,
            pybic.cmd.READ_VOUT[0]: self._handle_cmd_read_vout,
            pybic.cmd.REVERSE_IOUT_SET[0]: self._handle_cmd_reverse_iout,
            pybic.cmd.SYSTEM_CONFIG[0]: self._handle_cmd_system_config,
            pybic.cmd.BIDIRECTIONAL_CONFIG[0]: self._handle_cmd_bidirectional_config,
            pybic.cmd.DIRECTION_CTRL[0]: self._handle_cmd_direction_ctrl,
            pybic.cmd.READ_TEMPERATURE[0]: self._handle_cmd_read_temperature,
            pybic.cmd.FAULT_STATUS[0]: self._handle_cmd_fault_status,
            pybic.cmd.SYSTEM_STATUS[0]: self._handle_cmd_system_status,
            pybic.cmd.MFR_ID_B0B5[0]: self._handle_cmd_mfr_id_b0b5,
            pybic.cmd.MFR_ID_B6B11[0]: self._handle_cmd_mfr_id_b6b11,
            pybic.cmd.MFR_MODEL_B0B5[0]: self._handle_cmd_mfr_model_b0b5,
            pybic.cmd.MFR_MODEL_B6B11[0]: self._handle_cmd_mfr_model_b6b11,
            pybic.cmd.MFR_SERIAL_B0B5[0]: self._handle_cmd_mfr_serial_b0b5,
            pybic.cmd.MFR_SERIAL_B6B11[0]: self._handle_cmd_mfr_serial_b6b11,
            pybic.cmd.MFR_DATE_B0B5[0]: self._handle_cmd_mfr_date_b0b5,
            pybic.cmd.MFR_REVISION_B0B5[0]: self._handle_cmd_mfr_revision_b0b5,
            pybic.cmd.MFR_LOCATION_B0B2[0]: self._handle_cmd_mfr_location_b0b2,
        }

        if not self._bic:
            self._logger.warn(f"bic is none")

        atexit.register(self.stop)

    def on_error(self, exc: Exception) -> None:
        self._logger.error(f"encounter error: {exc}")

    def on_message_received(self, msg: can.message.Message) -> None:
        try:
            if (msg.arbitration_id & 0xFFF00) == DIR_TO_CONTROLLER:
                self._logger.debug(
                    f"received message to controller: {format_can_message(msg)}"
                )
                self._handle_to_controller(msg)

            if (msg.arbitration_id & 0xFFF00) == DIR_FROM_CONTROLLER:
                self._logger.debug(
                    f"received message from controller: {format_can_message(msg)}"
                )
                self._handle_from_controller(msg)

        except Exception as e:
            self._logger.error(
                f'failed handling message "{format_can_message(msg)}": {e}'
            )

    def stop(self) -> None:
        self._handler_job_queue.shutdown(cancel_futures=True)

    def _fulfill_bic_promises(self, key, value):
        if not self._bic:
            self._logger.warn(f"bic is none, skip fulfilling promises for key {key}")
            return

        if key not in self._bic._promises:
            self._logger.warn(
                f"key does not exist in promise map, skip fulfilling promises for key {key}"
            )
            return

        for promise in self._bic._promises[key]:
            promise.set_result(value)

        self._bic._promises[key].clear()

    def _handle_to_controller(self, msg: can.message.Message) -> None:
        if msg.arbitration_id & 0x000FF != self._bic._arbitration_id & 0x000FF:
            # skip message not meant for us
            return

        (cmd,) = struct.unpack("<H", msg.data[:CMD_LENGTH])

        if cmd not in self._command_handlers:
            self._logger.warn(f"handler not implemented for command: {cmd}")
            return

        self._handler_thread_pool.submit(self._command_handlers[cmd], msg=msg)

    def _handle_from_controller(self, msg: can.message.Message) -> None:
        pass

    def _handle_cmd_operation(self, msg: can.message.Message) -> None:
        self._fulfill_bic_promises("operation", True if msg.data[2] == 1 else False)

    def _handle_cmd_read_vin(self, msg: can.message.Message) -> None:
        (v_in_raw,) = struct.unpack("<H", msg.data[2 : msg.dlc])

        self._fulfill_bic_promises("v_in", v_in_raw * self._bic.scaling_factor["v_in"])

    def _handle_cmd_read_vout(self, msg: can.message.Message) -> None:
        (v_out_raw,) = struct.unpack("<H", msg.data[2 : msg.dlc])

        self._fulfill_bic_promises(
            "v_out", v_out_raw * self._bic.scaling_factor["v_out"]
        )

    def _handle_cmd_scaling_factor(self, msg: can.message.Message) -> None:
        # trim the command from the data
        data = msg.data[2:]

        v_out_factor = convert_scaling_factor(data[0] & 0x0F)
        i_out_factor = convert_scaling_factor((data[0] & 0xF0) >> 4)
        v_in_factor = convert_scaling_factor(data[1] & 0x0F)
        fan_speed_factor = convert_scaling_factor((data[1] & 0xF0) >> 4)
        temperature_factor = convert_scaling_factor(data[2] & 0x0F)
        i_in_factor = convert_scaling_factor(data[3] & 0x0F)

        self._fulfill_bic_promises(
            "scaling_factor",
            {
                "v_out": v_out_factor,
                "i_out": i_out_factor,
                "v_in": v_in_factor,
                "i_in": i_in_factor,
                "fan_speed": fan_speed_factor,
                "temperature": temperature_factor,
            },
        )

    def _handle_cmd_system_config(self, msg: can.message.Message) -> None:
        # trim the command from the data
        data = msg.data[2:]

        operation_init = (data[0] & 0x06) >> 1
        can_ctrl = data[0] & 0x01

        self._fulfill_bic_promises(
            "system_config",
            {
                "operation_init": operation_init,
                "can_ctrl": can_ctrl,
            },
        )

    def _handle_cmd_bidirectional_config(self, msg: can.message.Message) -> None:
        # trim the command from the data
        data = msg.data[2:]

        self._fulfill_bic_promises(
            "bidirectional_config",
            {
                "mode": data[0] & 0x01,
            },
        )

    def _handle_cmd_direction_ctrl(self, msg: can.message.Message) -> None:
        # trim the command from the data
        data = msg.data[2]

        self._fulfill_bic_promises("direction_ctrl", data)

    def _handle_cmd_reverse_vout(self, msg: can.message.Message) -> None:
        (rev_v_out_raw,) = struct.unpack("<H", msg.data[2 : msg.dlc])

        self._fulfill_bic_promises(
            "reverse_v_out", rev_v_out_raw * self._bic.scaling_factor["v_out"]
        )

    def _handle_cmd_reverse_iout(self, msg: can.message.Message) -> None:
        (rev_i_out_raw,) = struct.unpack("<H", msg.data[2 : msg.dlc])

        self._fulfill_bic_promises(
            "reverse_i_out", rev_i_out_raw * self._bic.scaling_factor["i_out"]
        )

    def _handle_cmd_read_iout(self, msg: can.message.Message) -> None:
        (i_out_raw,) = struct.unpack("<h", msg.data[2 : msg.dlc])

        self._fulfill_bic_promises(
            "i_out", i_out_raw * self._bic.scaling_factor["i_out"]
        )

    def _handle_cmd_read_temperature(self, msg: can.message.Message) -> None:
        (temp_raw,) = struct.unpack("<h", msg.data[2 : msg.dlc])

        self._fulfill_bic_promises(
            "temperature", temp_raw * self._bic.scaling_factor["temperature"]
        )

    def _handle_cmd_fault_status(self, msg: can.message.Message) -> None:
        data = msg.data[2 : msg.dlc]

        fault_status = {
            "fan_fail": (data[0] & 0x01) > 0,
            "otp": (data[0] & 0x02) > 0,
            "ovp": (data[0] & 0x04) > 0,
            "olp": (data[0] & 0x08) > 0,
            "short": (data[0] & 0x10) > 0,
            "ac_fail": (data[0] & 0x20) > 0,
            "op_off": (data[0] & 0x40) > 0,
            "hi_temp": (data[0] & 0x80) > 0,
            "hv_ovp": (data[1] & 0x01) > 0,
        }

        self._fulfill_bic_promises("fault_status", fault_status)

    def _handle_cmd_system_status(self, msg: can.message.Message) -> None:
        data = msg.data[2 : msg.dlc]

        system_status = {
            "m/s": (data[0] & 0x01) > 0,
            "dc_ok": (data[0] & 0x02) > 0,
            "pfc_ok": (data[0] & 0x04) > 0,
            "adl_on": (data[0] & 0x10) > 0,
            "initial_state": (data[0] & 0x20) > 0,
            "eeper": (data[0] & 0x40) > 0,
        }

        self._fulfill_bic_promises("system_status", system_status)

    def _handle_cmd_mfr_id_b0b5(self, msg: can.message.Message) -> None:
        self._fulfill_bic_promises("mfr_id_b0b5", msg.data[2 : msg.dlc].decode())

    def _handle_cmd_mfr_id_b6b11(self, msg: can.message.Message) -> None:
        self._fulfill_bic_promises("mfr_id_b6b11", msg.data[2 : msg.dlc].decode())

    def _handle_cmd_mfr_model_b0b5(self, msg: can.message.Message) -> None:
        self._fulfill_bic_promises("mfr_model_b0b5", msg.data[2 : msg.dlc].decode())

    def _handle_cmd_mfr_model_b6b11(self, msg: can.message.Message) -> None:
        self._fulfill_bic_promises("mfr_model_b6b11", msg.data[2 : msg.dlc].decode())

    def _handle_cmd_mfr_serial_b0b5(self, msg: can.message.Message) -> None:
        self._fulfill_bic_promises("mfr_serial_b0b5", msg.data[2 : msg.dlc].decode())

    def _handle_cmd_mfr_serial_b6b11(self, msg: can.message.Message) -> None:
        self._fulfill_bic_promises("mfr_serial_b6b11", msg.data[2 : msg.dlc].decode())

    def _handle_cmd_mfr_date_b0b5(self, msg: can.message.Message) -> None:
        self._fulfill_bic_promises("mfr_date_b0b5", msg.data[2 : msg.dlc].decode())

    def _handle_cmd_mfr_revision_b0b5(self, msg: can.message.Message) -> None:
        revision_list = []
        for rev in msg.data[2 : msg.dlc]:
            if rev != 0xFF:
                revision_list.append(f"r{rev/10:2.1f}")

        self._fulfill_bic_promises("mfr_revision_b0b5", tuple(revision_list))

    def _handle_cmd_mfr_location_b0b2(self, msg: can.message.Message) -> None:
        self._fulfill_bic_promises("mfr_location_b0b2", msg.data[2 : msg.dlc].decode())
