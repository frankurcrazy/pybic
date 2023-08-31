import can
import threading

def format_can_message(msg: can.message.Message) -> str:
    data_hex = "".join(f"{x:02x}" for x in msg.data[:msg.dlc])
    direction = "rx" if msg.is_rx else "tx"

    return f"<Message arbitration_id=0x{msg.arbitration_id:04x} " + \
           f"dlc={msg.dlc} data=0x{data_hex} direction={direction}" + \
           ">"

class Promise:
    def __init__(self):
        self._ev = threading.Event()
        self._result = None

    def set_result(self, result):
        self._result = result
        self._ev.set()

    @property
    def result(self):
        self._ev.wait()
        return self._result

