import can
import logging
import struct

import pybic.cmd

from pybic.utils import format_can_message

DIR_TO_CONTROLLER = 0xc0200
DIR_FROM_CONTROLLER = 0xc0300
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
        }

        if not self._bic:
            self._logger.warn(f"bic is none")

    def on_error(self, exc: Exception) -> None:
        self._logger.error(f"encounter error: {exc}")

    def on_message_received(self, msg: can.message.Message) -> None:
        try:
            if ((msg.arbitration_id & 0xfff00) == DIR_TO_CONTROLLER):
                self._logger.debug(f"received message to controller: {format_can_message(msg)}")
                self._handle_to_controller(msg)

            if ((msg.arbitration_id & 0xfff00) == DIR_FROM_CONTROLLER):
                self._logger.debug(f"received message from controller: {format_can_message(msg)}")
                self._handle_from_controller(msg)

        except Exception as e:
            self._logger.error(f"failed handling message \"{format_can_message(msg)}\": {e}")

    def stop(self) -> None:
        pass

    def _set_bic_property(self, key, value):
        if not self._bic:
            self._logger.warn(f"bic is none, skip setting property {key} -> {value}")
            return

        self._bic.properties[key] = value

    def _handle_to_controller(self, msg: can.message.Message) -> None:
        cmd, = struct.unpack("<H", msg.data[:CMD_LENGTH])

        if cmd not in self._command_handlers:
            self._logger.warn(f"handler not implemented for command: {cmd}")
            return

        self._command_handlers[cmd](msg=msg)

    def _handle_from_controller(self, msg: can.message.Message) -> None:
        pass

    def _handle_cmd_operation(self, msg: can.message.Message) -> None:
        self._set_bic_property("operation", True if msg.data[2] == 1 else False)

    def _handle_cmd_read_vin(self, msg: can.message.Message) -> None:
        v_in_raw, = struct.unpack("<H", msg.data[2: msg.dlc])

        self._set_bic_property("v_in", v_in_raw * self._bic.scaling_factor["v_in"])

    def _handle_cmd_read_vout(self, msg: can.message.Message) -> None:
        v_out_raw, = struct.unpack("<H", msg.data[2: msg.dlc])

        self._set_bic_property("v_out", v_out_raw * self._bic.scaling_factor["v_out"])

    def _handle_cmd_scaling_factor(self, msg: can.message.Message) -> None:
        # trim the command from the data
        data = msg.data[2:]

        v_out_factor = convert_scaling_factor(data[0] & 0x0f)
        i_out_factor = convert_scaling_factor((data[0] & 0xf0) >> 4)
        v_in_factor = convert_scaling_factor(data[1] & 0x0f)
        fan_speed_factor = convert_scaling_factor((data[1] & 0xf0) >> 4)
        temperature_factor = convert_scaling_factor(data[2] & 0x0f)
        i_in_factor = convert_scaling_factor(data[3] & 0x0f)

        self._set_bic_property("scaling_factor", {
            "v_out": v_out_factor,
            "i_out": i_out_factor,
            "v_in": v_in_factor,
            "i_in": i_in_factor,
            "fan_speed": fan_speed_factor,
            "temperature": temperature_factor,
        })

    def _handle_cmd_system_config(self, msg: can.message.Message) -> None:
        # trim the command from the data
        data = msg.data[2:]

        operation_init = (data[0] & 0x06) >> 1
        can_ctrl = (data[0] & 0x01) 

        self._set_bic_property("system_config", {
            "operation_init": operation_init,
            "can_ctrl": can_ctrl,
        })

    def _handle_cmd_bidirectional_config(self, msg: can.message.Message) -> None:
        # trim the command from the data
        data = msg.data[2:]

        self._set_bic_property("bidirectional_config", {
            "mode": data[0] & 0x01,
            })

    def _handle_cmd_direction_ctrl(self, msg: can.message.Message) -> None:
        # trim the command from the data
        data = msg.data[2]

        self._set_bic_property("direction_ctrl", data)

    def _handle_cmd_reverse_vout(self, msg: can.message.Message) -> None:
        rev_v_out_raw, = struct.unpack("<H", msg.data[2: msg.dlc])

        self._set_bic_property("reverse_v_out", rev_v_out_raw * self._bic.scaling_factor["v_out"])

    def _handle_cmd_reverse_iout(self, msg: can.message.Message) -> None:
        rev_i_out_raw, = struct.unpack("<H", msg.data[2: msg.dlc])

        self._set_bic_property("reverse_i_out", rev_i_out_raw * self._bic.scaling_factor["i_out"])

    def _handle_cmd_read_iout(self, msg: can.message.Message) -> None:
        i_out_raw, = struct.unpack("<h", msg.data[2: msg.dlc])

        self._set_bic_property("i_out", i_out_raw * self._bic.scaling_factor["i_out"])
