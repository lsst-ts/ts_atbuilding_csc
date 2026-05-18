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
from typing import Any, DefaultDict

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

# Reconnect behavior (seconds).
RECONNECT_INITIAL_DELAY = 10.0
RECONNECT_BACKOFF = 1.5
RECONNECT_MAX_RETRIES = 10


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
    * 1: mock controller
    """

    valid_simulation_modes = (0, 1)
    version = __version__

    def __init__(
        self,
        config_dir: str | None = None,
        initial_state: salobj.State = salobj.State.STANDBY,
        simulation_mode: int = 0,
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
        self.mock_ctrl: MockVentController | None = None

        # Task that waits for messages from the TCP/IP controller.
        self.listen_task = utils.make_done_future()

        # Task that retries connection on disconnect.
        self.reconnect_task = utils.make_done_future()

        # Set up a dummy tcpip client, to connect to later.
        self.client: tcpip.Client | None = None

        self.response_queue: DefaultDict[str, asyncio.Queue] = defaultdict(
            asyncio.Queue
        )

        self.callbacks = {
            "telemetry": self.handle_telemetry,
            "evt_extraction_fan_drive_fault_code": self.handle_extraction_fan_drive_fault_code,
            "evt_extraction_fan_drive_state": self.handle_extraction_fan_drive_state,
            "evt_vent_gate_state": self.handle_vent_gate_state,
        }

    async def handle_telemetry(self, message_json: dict[str, Any]) -> None:
        """Accepts a telemetry JSON message from the server and writes to the
        CSC's telemetry.

        Parameters
        ----------
        message_json : dict[str, Any]
            The message received from the server containing an
            extractionFanDriveFaultCode event. The message must contain
            a "data" key providing a dictionary of telemetry data
            to emit.
        """

        drive_frequency = message_json["data"]["tel_extraction_fan"]
        drive_voltage = message_json["data"].get("tel_drive_voltage", None)

        await self.tel_extractionFan.set_write(
            driveFrequency=drive_frequency,
            driveVoltage=drive_voltage,
        )

    async def handle_vent_gate_state(self, message_json: dict[str, Any]) -> None:
        """Accepts an evt_ventGateState JSON message from the server and
        invokes the event in the CSC.

        Parameters
        ----------
        message_json : dict[str, Any]
            The message received from the server containing an
            ventGateState event. The message must contain
            a "data" key providing the value of the state to write
            into the event.
        """

        state = [VentGateState(i) for i in message_json["data"]]
        await self.evt_ventGateState.set_write(state=state)

    async def handle_extraction_fan_drive_state(
        self, message_json: dict[str, Any]
    ) -> None:
        """Accepts an evt_extractionFanDriveState JSON message from the
        server and invokes the event in the CSC.

        Parameters
        ----------
        message_json : dict[str, Any]
            The message received from the server containing an
            extractionFanDriveState event. The message must contain
            a "data" key providing the value of the state to write
            into the event.
        """

        state = FanDriveState(message_json["data"])
        await self.evt_extractionFanDriveState.set_write(state=state)

    async def handle_extraction_fan_drive_fault_code(
        self, message_json: dict[str, Any]
    ) -> None:
        """Accepts an evt_extractionFanDriveFaultCode JSON message from the
        server and invokes the event in the CSC.

        Parameters
        ----------
        message_json : dict[str, Any]
            The message received from the server containing an
            extractionFanDriveFaultCode event. The message must contain
            a "data" key providing the value of the state to write
            into the event.
        """

        state = message_json["data"]
        await self.evt_extractionFanDriveFaultCode.set_write(state=state)

    @staticmethod
    def get_config_pkg() -> str:
        return "ts_config_attcs"

    async def configure(self, config: Any) -> None:
        self.config = config

    async def handle_summary_state(self) -> None:
        self.log.debug("handle_summary_state()")
        if self.disabled_or_enabled:
            if self.client is None or not self.client.connected:
                await self.connect()
        else:
            self._cancel_reconnect()
            await self.disconnect()

    async def close_tasks(self) -> None:
        """Disconnect from the TCP/IP controller, if connected, and stop
        the mock controller, if running.
        """
        await self.disconnect()

    async def connect(self, allow_fault: bool = True) -> bool:
        """Connect to the building RPi's TCP/IP port.

        Parameters
        ----------
        allow_fault : `bool`
            If True (the default), transition the CSC to FAULT on a
            connection failure. Set to False when called from the
            reconnect loop, which handles the FAULT transition itself
            only after retries are exhausted.

        Returns
        -------
        connected : `bool`
            True if the connection succeeded (or was already open),
            False if the attempt failed. When False and ``allow_fault``
            is True, the CSC has also been driven to FAULT.
        """
        if self.simulation_mode == 0:
            host = self.config.host
            port = self.config.port
        elif self.simulation_mode == 1:
            await self.start_mock_ctrl()
            assert self.mock_ctrl is not None
            host = self.mock_ctrl.host
            port = self.mock_ctrl.port

        if self.config is None:
            raise RuntimeError("Not yet configured")
        if self.client is not None and self.client.connected:
            return True

        self.log.debug(f"Connecting to host={host}, port={port}")
        try:
            self.client = tcpip.Client(host=host, port=port, log=self.log)
            await asyncio.wait_for(
                self.client.start_task, timeout=self.config.connection_timeout
            )
            asyncio.create_task(self.listen_for_messages())
            self.log.debug("connected")

            max_freq_response = await self.run_command("get_fan_drive_max_frequency")
            max_frequency = max_freq_response["return_value"]
            await self.evt_maximumDriveFrequency.set_write(
                driveFrequency=max_frequency,
            )
            self.log.debug("Emitted maximumDriveFrequency event")

            self._cancel_reconnect()
            return True
        except Exception as e:
            err_msg = f"Could not open connection to host={host}, port={port}: {e!r}"
            self.log.exception(err_msg)
            if self.client is not None:
                await self.client.close()
            if allow_fault:
                await self.fault(code=ErrorCode.TCPIP_CONNECT_ERROR, report=err_msg)
            return False

    async def disconnect(self) -> None:
        """Disconnect from the TCP/IP controller, if connected, and stop
        the mock controller, if running.
        """
        self.log.debug("disconnect")

        self._cancel_reconnect()
        await self._close_client()
        await self.stop_mock_ctrl()
        self.log.debug("disconnect done")

    async def start_mock_ctrl(self) -> None:
        """Start the controller with the mock object as server."""
        if self.mock_ctrl is not None:
            return

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

    async def stop_mock_ctrl(self) -> None:
        """Stop the mock controller."""
        mock_ctrl = self.mock_ctrl
        self.mock_ctrl = None
        if mock_ctrl is not None:
            await mock_ctrl.close()

    async def do_closeVentGate(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Implement the ``closeVentGate`` command."""
        self.assert_enabled()
        args = " ".join([str(i) for i in data.gate])
        await self.run_command(f"close_vent_gate {args}")

    async def do_openVentGate(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Implement the ``openVentGate`` command."""
        self.assert_enabled()
        args = " ".join([str(i) for i in data.gate])
        await self.run_command(f"open_vent_gate {args}")

    async def do_resetExtractionFanDrive(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        """Implement the ``resetExtractionFanDrive`` command."""
        self.assert_enabled()
        await self.run_command("reset_extraction_fan_drive")

    async def do_setExtractionFanDriveFreq(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        """Implement the ``setExtractionFanDriveFreq`` command."""
        self.assert_enabled()
        await self.run_command(f"set_extraction_fan_drive_freq {data.targetFrequency}")

    async def do_setExtractionFanManualControlMode(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        """Implement the ``setExtractionFanControlMode`` command."""
        self.assert_enabled()
        await self.run_command(
            f"set_extraction_fan_manual_control_mode {data.enableManualControlMode}"
        )

    async def do_startExtractionFan(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Implement the ``startExtractionFan`` command."""
        self.assert_enabled()
        await self.run_command("start_extraction_fan")

    async def do_stopExtractionFan(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Implement the ``stopExtractionFan`` command."""
        self.assert_enabled()
        await self.run_command("stop_extraction_fan")

    async def run_command(self, command: str) -> dict[str, Any]:
        """Sends a command to the RPi. It writes to the TCP port,
        and then monitors an `asyncio.Queue`. The response is
        written to the queue by the `listen_for_messages` method.

        Parameters
        ----------
        command : str
            The command string to send to the server.
        """
        assert self.client is not None
        if not self.client.connected:
            self._start_reconnect("Command issued while disconnected.")
            raise RuntimeError("Cannot send a command when not connected.")
        await asyncio.wait_for(self.client.write_str(command), timeout=TCP_TIMEOUT)

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

    async def listen_for_messages(self) -> None:
        """Receives messages from the RPi. If the message contains an event
        (command starts with "evt_") or telemetry (command is "telemetry") it
        passes the message to the appropriate handler. Otherwise, it sends it
        to the queue for that command, to be handled by the method that
        called that command.
        """
        assert self.client is not None
        disconnect_reason = "Controller disconnected unexpectedly"
        while self.client is not None and self.client.connected:
            try:
                # Receive a message and format it as JSON.
                self.listen_task = asyncio.create_task(self.client.read_str())
                message = await asyncio.wait_for(
                    self.listen_task, timeout=self.config.read_timeout
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
                self.log.warning(
                    "Timed out waiting for controller message after %.1f sec.",
                    self.config.read_timeout,
                )
                disconnect_reason = "Timed out waiting for controller message"
                self.listen_task.cancel()
                break
            except asyncio.IncompleteReadError:
                # Incomplete read implies disconnect
                break
            except Exception:
                self.log.exception("Exception while handling server response.")

        if self.disabled_or_enabled:
            self._start_reconnect(disconnect_reason)

    async def _close_client(self) -> None:
        """Close the TCP client and cancel the active read task.

        Sets ``self.client`` to None *before* awaiting the close, so any
        concurrent coroutine checking the attribute sees the disconnected
        state immediately rather than racing against the close.
        """
        client = self.client
        self.client = None
        if client is not None:
            await client.close()
        self.listen_task.cancel()

    def _cancel_reconnect(self) -> None:
        """Cancel the running reconnect task, if any.

        Has no effect if no reconnect is in progress, or if the caller
        is itself the reconnect task (which would otherwise cancel
        itself mid-execution).
        """
        current_task = asyncio.current_task()
        if not self.reconnect_task.done() and self.reconnect_task is not current_task:
            self.reconnect_task.cancel()

    def _start_reconnect(
        self, reason: str, fault_code: ErrorCode = ErrorCode.UNEXPECTED_DISCONNECT
    ) -> None:
        """Schedule a background reconnect loop.

        Does nothing if the CSC is not in the DISABLED or ENABLED state,
        or if a reconnect task is already running. The CSC will be driven
        to FAULT with ``fault_code`` only if every retry in
        ``_reconnect_loop`` fails.

        Parameters
        ----------
        reason : `str`
            Human-readable description of why the reconnect was triggered.
            Logged on each attempt and included in the final FAULT report.
        fault_code : `ErrorCode`
            Error code to report if all retries are exhausted. Defaults
            to ``ErrorCode.UNEXPECTED_DISCONNECT``.
        """
        if not self.disabled_or_enabled:
            self.log.info("Not reconnecting in summary state %s", self.summary_state)
            return
        if not self.reconnect_task.done():
            return
        self.log.warning("Starting reconnect loop: %s", reason)
        self.reconnect_task = asyncio.create_task(
            self._reconnect_loop(reason, fault_code)
        )

    async def _reconnect_loop(self, reason: str, fault_code: ErrorCode) -> None:
        """Retry the controller connection with exponential backoff.

        Closes any existing client (and mock controller, in simulation
        mode), then makes up to ``RECONNECT_MAX_RETRIES`` attempts,
        sleeping ``RECONNECT_INITIAL_DELAY`` seconds before the first
        attempt and multiplying the delay by ``RECONNECT_BACKOFF``
        after each failure. Returns early if the CSC leaves the
        DISABLED/ENABLED states, if the client becomes connected
        by other means, or if the task is cancelled. If every attempt
        fails, drives the CSC to FAULT with ``fault_code``.

        Parameters
        ----------
        reason : `str`
            Human-readable cause of the disconnect, propagated to log
            messages and the FAULT report.
        fault_code : `ErrorCode`
            Error code to use if retries are exhausted.
        """
        await self._close_client()
        if self.simulation_mode == 1:
            await self.stop_mock_ctrl()
        delay = RECONNECT_INITIAL_DELAY
        for attempt in range(1, RECONNECT_MAX_RETRIES + 1):
            if self.client is not None and self.client.connected:
                return
            self.log.warning(
                "Reconnect attempt %d/%d in %.1f sec (%s).",
                attempt,
                RECONNECT_MAX_RETRIES,
                delay,
                reason,
            )
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return

            if not self.disabled_or_enabled:
                self.log.info(
                    "Reconnect loop canceled due to summary state %s",
                    self.summary_state,
                )
                return

            if await self.connect(allow_fault=False):
                self.log.info("Reconnect succeeded.")
                return
            delay *= RECONNECT_BACKOFF

        await self.fault(
            code=fault_code,
            report=(
                f"Reconnect failed after {RECONNECT_MAX_RETRIES} attempts: {reason}"
            ),
        )


def run_atbuilding() -> None:
    """Run the ATBuilding CSC."""
    asyncio.run(ATBuildingCsc.amain(index=None))
