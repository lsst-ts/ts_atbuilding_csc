# This file is part of ts_atbuilding_csc
#
# Developed for Vera C. Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License

__all__ = ["MockVentController"]

import asyncio
import json
import logging
import traceback
from collections import deque

from lsst.ts import tcpip, utils
from lsst.ts.vent.controller import cast_string_to_type
from lsst.ts.xml.enums.ATBuilding import FanDriveState, VentGateState


class MockVentController(tcpip.OneClientReadLoopServer):
    """A mock controller for the vent and fan. Cribbed heavily from
    lsst-ts/ts_atbuilding_vents/python/lsst/ts/atbuilding/vents/controller/dispatcher.py.
    """

    def __init__(self, port: int, log: logging.Logger):
        self.log = log
        log.info("MockVentController.__init__")

        self.dispatch_dict = {
            "close_vent_gate": [int, int, int, int],
            "open_vent_gate": [int, int, int, int],
            "reset_extraction_fan_drive": [],
            "set_extraction_fan_drive_freq": [float],
            "set_extraction_fan_manual_control_mode": [bool],
            "start_extraction_fan": [],
            "stop_extraction_fan": [],
            "ping": [],
        }

        # Controller state:
        #  * Fan on/off/frequency
        #  * Vent gate limits
        #  * Manual control mode
        #  * Fault codes

        self.fan_frequency = 0.0  # Hz, 0.0 is off
        self.vent_states = [VentGateState.CLOSED] * 4
        self.manual_control_mode = True
        self.fault_codes = deque([22] * 8, maxlen=8)
        self.fan_drive_state = FanDriveState.STOPPED
        self.extraction_fan_drive_was_reset = False

        self.monitor_sleep_task = utils.make_done_future()
        self.vent_gate_state_task = utils.make_done_future()

        self.telemetry_count = 0
        self.TELEMETRY_INTERVAL = 10

        super().__init__(
            port=port, log=log, connect_callback=self.on_connect, terminator=b"\r"
        )

    async def respond(self, message: str) -> None:
        await self.write_str(message + "\r\n")

    async def read_and_dispatch(self) -> None:
        """Read, parse and execute a command, and send a response."""
        data = await self.read_str()
        data = data.strip()
        if not data:
            return

        self.log.debug(f"Received command: {data!r}")

        command, *args = (
            data.split()
        )  # Tokenize the command and break out the first word as the method.

        if command not in self.dispatch_dict:
            # If the command string is not in the dictionary, send back an
            # error and do nothing.
            await self.respond(
                json.dumps(
                    dict(
                        command=command,
                        error=1,
                        exception_name="NotImplementedError",
                        message="No such command",
                        traceback="",
                    )
                )
            )
            return

        # Pull the handler and the argument list from the dictionary.
        types = self.dispatch_dict[command]
        if len(args) != len(types):
            # If the arguments don't match the list in the dictionary, send
            # back an error.
            await self.respond(
                json.dumps(
                    dict(
                        command=command,
                        error=1,
                        exception_name="TypeError",
                        message=f"Error while handling command {command}.",
                        traceback="",
                    )
                )
            )
            return

        try:
            # Convert the arguments to their expected type.
            args = [cast_string_to_type(t, arg) for t, arg in zip(types, args)]
            # Call the method with the specified arguments.
            await getattr(self, command)(*args)
            # Send back a success response.
            await self.respond(
                json.dumps(
                    dict(
                        command=command,
                        error=0,
                        exception_name="",
                        message="",
                        traceback="",
                    )
                )
            )
        except Exception as e:
            self.log.exception(f"Exception raised while handling command {command}")
            await self.respond(
                json.dumps(
                    dict(
                        command=command,
                        error=1,
                        exception_name=type(e).__name__,
                        message=str(e),
                        traceback=traceback.format_exc(),
                    )
                )
            )

    async def _set_vent_state(self, gate: int, state: VentGateState) -> None:
        await asyncio.sleep(1.0)
        self.vent_states[gate] = state

    async def close_vent_gate(
        self, gate1: int, gate2: int, gate3: int, gate4: int
    ) -> None:
        for gate in (gate1, gate2, gate3, gate4):
            if gate == -1:
                continue

            if not gate >= 0 and gate <= 3:
                raise ValueError(f"Invalid gate number: {gate}")

            if self.vent_states[gate] != VentGateState.CLOSED:
                self.vent_gate_state_task = asyncio.ensure_future(
                    self._set_vent_state(gate, VentGateState.CLOSED)
                )

    async def open_vent_gate(
        self, gate1: int, gate2: int, gate3: int, gate4: int
    ) -> None:
        for gate in (gate1, gate2, gate3, gate4):
            if gate == -1:
                continue

            if not gate >= 0 and gate <= 3:
                raise ValueError(f"Invalid gate number: {gate}")

            if self.vent_states[gate] != VentGateState.OPENED:
                self.vent_gate_state_task = asyncio.ensure_future(
                    self._set_vent_state(gate, VentGateState.OPENED)
                )

    async def reset_extraction_fan_drive(self) -> None:
        self.extraction_fan_drive_was_reset = True

    async def set_extraction_fan_drive_freq(self, target_frequency: float) -> None:
        self.fan_frequency = target_frequency

    async def set_extraction_fan_manual_control_mode(
        self, enable_manual_control_mode: bool
    ) -> None:
        self.manual_control_mode = enable_manual_control_mode

    async def start_extraction_fan(self) -> None:
        self.fan_frequency = 50.0

    async def stop_extraction_fan(self) -> None:
        self.fan_frequency = 0.0

    async def ping(self) -> None:
        pass

    async def on_connect(self, bcs: tcpip.BaseClientOrServer) -> None:
        if self.connected:
            self.log.info("Connected to client.")
            asyncio.create_task(self.monitor_status())
        else:
            self.log.info("Disconnected from client.")

    async def close(self) -> None:
        self.monitor_sleep_task.cancel()
        self.vent_gate_state_task.cancel()
        await super().close()

    async def monitor_status(self) -> None:
        vent_state = None
        last_fault = None
        fan_drive_state = None

        while self.connected:
            new_vent_state = self.vent_states
            new_last_fault = self.fault_codes[0]
            new_fan_drive_state = self.fan_drive_state

            # Check whether the vent state has changed
            if vent_state != new_vent_state:
                self.log.debug(f"Vent state changed: {vent_state} -> {new_vent_state}")
                data = [int(state) for state in new_vent_state]
                await self.respond(
                    json.dumps(
                        dict(
                            command="evt_vent_gate_state",
                            error=0,
                            exception_name="",
                            message="",
                            traceback="",
                            data=data,
                        )
                    )
                )
                vent_state = list(new_vent_state)

            # Check whether the fan drive state has changed
            if fan_drive_state != new_fan_drive_state:
                self.log.debug(
                    f"Fan drive state changed: {fan_drive_state} -> {new_fan_drive_state}"
                )
                await self.respond(
                    json.dumps(
                        dict(
                            command="evt_extraction_fan_drive_state",
                            error=0,
                            exception_name="",
                            message="",
                            traceback="",
                            data=new_fan_drive_state,
                        )
                    )
                )
                fan_drive_state = new_fan_drive_state

            # Check whether the last fault has changed
            if last_fault != new_last_fault:
                self.log.debug(f"Last fault changed: {last_fault} -> {new_last_fault}")
                await self.respond(
                    json.dumps(
                        dict(
                            command="evt_extraction_fan_drive_fault_code",
                            error=0,
                            exception_name="",
                            message="",
                            traceback="",
                            data=new_last_fault,
                        )
                    )
                )
                last_fault = new_last_fault

            # Send telemetry every TELEMETRY_INTERVAL times through the loop
            self.telemetry_count -= 1
            if self.telemetry_count < 0:
                self.telemetry_count = self.TELEMETRY_INTERVAL
                telemetry = {
                    "tel_extraction_fan": self.fan_frequency,
                }
                await self.respond(
                    json.dumps(
                        dict(
                            command="telemetry",
                            error=0,
                            exception_name="",
                            message="",
                            traceback="",
                            data=telemetry,
                        )
                    )
                )

            try:
                self.monitor_sleep_task = asyncio.ensure_future(asyncio.sleep(0.1))
                await self.monitor_sleep_task
            except asyncio.CancelledError:
                continue
