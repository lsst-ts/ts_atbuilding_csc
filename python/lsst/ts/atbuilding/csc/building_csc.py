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

__all__ = ["ATBuildingCsc", "run_atbuilding"]

import asyncio
import json
from collections import defaultdict
from typing import Any

from lsst.ts import salobj, tcpip, utils
from lsst.ts.xml.enums.ATBuilding import FanDriveState, VentGateState

from . import __version__
from .config_schema import CONFIG_SCHEMA
from .enums import ErrorCode
from .mock_controller import MockVentController

# Max time (sec) to wait for the mock controller to start.
MOCK_CTRL_START_TIMEOUT = 2

# Max time (sec) to wait for a TCP/IP command to complete.
TCP_TIMEOUT = 1

# Max time (sec) to receive a message from the server.
# This might be a while if no commands are active.
SERVER_MESSAGE_TIMEOUT = 30


class ATBuildingCsc(salobj.ConfigurableCsc):
    """AuxTel Building CSC (dome vents and fan)

    Parameters
    ----------
    initial_state : `salobj.State` or `int` (optional)
        The initial state of the CSC. This is provided for unit testing,
        as real CSCs should start up in `lsst.ts.salobj.StateSTANDBY`,
        the default.
    simulation_mode : `int` (optional)
        Simulation mode.

    Raises
    ------
    salobj.ExpectedError
        If initial_state or simulation_mode is invalid.

    Notes
    -----
    **Simulation Modes**

    Supported simulation modes

    * 0: regular operation
    """

    valid_simulation_modes = (0, 1)
    version = __version__

    def __init__(
        self,
        config_dir=None,
        initial_state=salobj.State.STANDBY,
        simulation_mode=0,
    ):
        super().__init__(
            name="ATBuilding",
            index=0,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode,
        )

        # Mock controller, used if simulation_mode is 1
        self.mock_ctrl = None

        # Task that waits while connecting to the TCP/IP controller.
        self.connect_task = utils.make_done_future()

        # Task that waits for messages from the TCP/IP controller.
        self.listen_task = utils.make_done_future()

        self.cmd_lock = asyncio.Lock()

        # Set up a dummy tcpip client, to connect to later.
        self.client = tcpip.Client(host="", port=0, log=self.log)

        self.response_queue = defaultdict(asyncio.Queue)

        self.callbacks = {
            "telemetry": self.handle_telemetry,
            "evt_extraction_fan_drive_fault_code": self.handle_extraction_fan_drive_fault_code,
            "evt_extraction_fan_drive_state": self.handle_extraction_fan_drive_state,
            "evt_vent_gate_state": self.handle_vent_gate_state,
        }

    async def handle_telemetry(self, message_json: dict[str, Any]) -> None:
        """Accepts a telemetry JSON message from the server and writes to the
        CSC's telemetry."""

        drive_frequency = message_json["data"]["tel_extraction_fan"]
        await self.tel_extractionFan.set_write(
            driveFrequency=drive_frequency,
        )

    async def handle_vent_gate_state(self, message_json: dict[str, Any]) -> None:
        """Accepts an evt_ventGateState JSON message from the server and
        invokes the event in the CSC.
        """

        state = [VentGateState(i) for i in message_json["data"]]
        await self.evt_ventGateState.set_write(state=state)

    async def handle_extraction_fan_drive_state(
        self, message_json: dict[str, Any]
    ) -> None:
        """Accepts an evt_extractionFanDriveState JSON message from the
        server and invokes the event in the CSC.
        """

        state = FanDriveState(message_json["data"])
        await self.evt_extractionFanDriveState.set_write(state=state)

    async def handle_extraction_fan_drive_fault_code(
        self, message_json: dict[str, Any]
    ) -> None:
        """Accepts an evt_extractionFanDriveFaultCode JSON message from the
        server and invokes the event in the CSC.
        """

        state = message_json["data"]
        await self.evt_extractionFanDriveFaultCode.set_write(state=state)

    @staticmethod
    def get_config_pkg():
        return "ts_config_attcs"

    async def configure(self, config):
        self.config = config

    async def do_enable(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Enable the CSC."""
        await self.connect()
        await super().do_enable(data)

    async def close(
        self, exception: Exception | None = None, cancel_start: bool = True
    ) -> None:
        """Close the CSC."""
        self.log.debug("CSC close")
        await self.disconnect()
        await super().close(exception=exception, cancel_start=cancel_start)

    async def connect(self):
        """Connect to the building RPi's TCP/IP port."""
        if self.simulation_mode == 1:
            await self.start_mock_ctrl()
            host = self.mock_ctrl.host
            port = self.mock_ctrl.port
        else:
            host = self.config.host
            port = self.config.port

        if self.config is None:
            raise RuntimeError("Not yet configured")
        if self.client.connected:
            raise RuntimeError("Already connected")

        self.log.debug(f"Connecting to host={host}, port={port}")
        try:
            async with self.cmd_lock:
                self.client = tcpip.Client(host=host, port=port, log=self.log)
                await asyncio.wait_for(
                    self.client.start_task, timeout=self.config.connection_timeout
                )
                asyncio.create_task(self.listen_for_messages())
            self.log.debug("connected")
        except Exception as e:
            err_msg = f"Could not open connection to host={host}, port={port}: {e!r}"
            self.log.exception(err_msg)
            await self.fault(code=ErrorCode.TCPIP_CONNECT_ERROR, report=err_msg)
            return

    async def disconnect(self):
        """Disconnect from the TCP/IP controller, if connected, and stop
        the mock controller, if running.
        """
        self.log.debug("disconnect")

        self.connect_task.cancel()
        await self.client.close()
        self.listen_task.cancel()
        await self.stop_mock_ctrl()

    async def start_mock_ctrl(self):
        """Start the controller with the mock object as server."""
        try:
            assert self.simulation_mode == 1
            self.mock_ctrl = MockVentController(port=0, log=self.log)
            await asyncio.wait_for(
                self.mock_ctrl.start_task, timeout=MOCK_CTRL_START_TIMEOUT
            )
        except Exception as e:
            err_msg = f"Failed to start mock controller: {e!r}"
            self.log.exception(err_msg)
            await self.fault(code=ErrorCode.MOCK_CTRL_START_ERROR, report=err_msg)
            raise

    async def stop_mock_ctrl(self):
        """Stop the mock controller."""
        mock_ctrl = self.mock_ctrl
        self.mock_ctrl = None
        if mock_ctrl is not None:
            await mock_ctrl.close()

    async def do_closeVentGate(self, data):
        """Implement the ``closeVentGate`` command."""
        self.assert_enabled()
        args = " ".join([str(i) for i in data.gate])
        await self.run_command(f"close_vent_gate {args}")

    async def do_openVentGate(self, data):
        """Implement the ``openVentGate`` command."""
        self.assert_enabled()
        args = " ".join([str(i) for i in data.gate])
        await self.run_command(f"open_vent_gate {args}")

    async def do_resetExtractionFanDrive(self, data):
        """Implement the ``resetExtractionFanDrive`` command."""
        self.assert_enabled()
        await self.run_command("reset_extraction_fan_drive")

    async def do_setExtractionFanDriveFreq(self, data):
        """Implement the ``setExtractionFanDriveFreq`` command."""
        self.assert_enabled()
        await self.run_command(f"set_extraction_fan_drive_freq {data.targetFrequency}")

    async def do_setExtractionFanManualControlMode(self, data):
        """Implement the ``setExtractionFanControlMode`` command."""
        self.assert_enabled()
        await self.run_command(
            f"set_extraction_fan_manual_control_mode {data.enableManualControlMode}"
        )

    async def do_startExtractionFan(self, data):
        """Implement the ``startExtractionFan`` command."""
        self.assert_enabled()
        await self.run_command("start_extraction_fan")

    async def do_stopExtractionFan(self, data):
        """Implement the ``stopExtractionFan`` command."""
        self.assert_enabled()
        await self.run_command("stop_extraction_fan")

    async def run_command(self, command: str) -> None:
        """Sends a command to the RPi. It writes to the TCP port,
        and then monitors an `asyncio.Queue`. The response is
        written to the queue by the `listen_for_messages` method.
        """
        await asyncio.wait_for(
            self.client.write_str(command + "\r\n"), timeout=TCP_TIMEOUT
        )

        # Wait for a response
        command_name = command.split()[0]
        response = await asyncio.wait_for(
            self.response_queue[command_name].get(), timeout=TCP_TIMEOUT
        )
        if response["error"] != 0:
            # If an error code is supplied, log the error and
            # raise an exception.
            self.log.error(
                "Error response received from command: "
                + command
                + " --> "
                + json.dumps(response)
            )
            raise salobj.ExpectedError(json.dumps(response))

        return response

    async def listen_for_messages(self):
        """Receives messages from the RPi. If the message contains an event
        (command starts with "evt_") or telemetry (command is "telemetry") it
        passes the message to the appropriate handler. Otherwise, it sends it
        to the queue for that command, to be handled by the method that
        called that command.
        """
        while self.client.connected:
            try:
                # Receive a message and format it as JSON.
                self.listen_task = asyncio.create_task(self.client.read_str())
                message = await asyncio.wait_for(
                    self.listen_task, timeout=SERVER_MESSAGE_TIMEOUT
                )

                message = message.strip()
                message_json = json.loads(message)
                command = message_json["command"]

                if command in self.callbacks:
                    # The callbacks dictionary maps telemetry and events to
                    # handler methods.
                    await self.callbacks[command](message_json)
                else:
                    # Response queues provide the response back to the
                    # command that sent them.
                    await self.response_queue[command].put(message_json)
            except asyncio.TimeoutError:
                self.log.debug("Timeout while waiting for server response.")
            except asyncio.CancelledError:
                pass
            except Exception:
                self.log.exception("Exception while handling server response.")


def run_atbuilding():
    """Run the ATBuilding CSC."""
    asyncio.run(ATBuildingCsc.amain(index=None))
