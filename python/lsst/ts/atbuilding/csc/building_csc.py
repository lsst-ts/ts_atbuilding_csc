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

from lsst.ts import salobj, tcpip
from lsst.ts.xml.enums.ATBuilding import (
    FanDriveState,
    VentGateState,
)

from . import __version__
from .config_schema import CONFIG_SCHEMA
from .enums import ErrorCode

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

    valid_simulation_modes = (0,)
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

        # Set up a dummy tcpip client, to connect to later.
        self.client = tcpip.Client(host="", port=0, log=self.log)

    @staticmethod
    def get_config_pkg():
        return "ts_config_attcs"
    
    async def configure(self, config):
        self.config = config
        # TODO Actual config here

    async def connect(self):
        """Connect to the building RPi's TCP/IP port."""

        self.log.debug("connect")
        if self.config is None:
            raise RuntimeError("Not yet configured")
        if self.client.connected:
            raise RuntimeError("Already connected")

        host = self.config.host
        port = self.config.port
        try:
            async with self.cmd_lock:
                self.client = tcpip.Client(host=host, port=port, log=self.log)
                await asyncio.wait_for(
                    self.client.start_task, timeout=self.config.connection_timeout
                )
                # drop welcome message
                await asyncio.wait_for(
                    self.client.readuntil(b">"), timeout=self.config.read_timeout
                )
            self.log.debug("connected")
        except Exception as e:
            err_msg = f"Could not open connection to host={host}, port={port}: {e!r}"
            self.log.exception(err_msg)
            await self.fault(code=ErrorCode.TCPIP_CONNECT_ERROR, report=err_msg)
            return

    async def do_closeVentGate(self, data):
        """Implement the ``closeVentGate`` command."""
        self.assert_enabled()
        await self.run_command(f"closeVentGate {data.gate}")

    async def do_openVentGate(self, data):
        """Implement the ``openVentGate`` command."""
        self.assert_enabled()
        await self.run_command(f"openVentGate {data.gate}")

    async def do_resetExtractionFanDrive(self, data):
        """Implement the ``resetExtractionFanDrive`` command."""
        self.assert_enabled()
        await self.run_command("resetExtractionFanDrive")

    async def do_setExtractionFanDriveFreq(self, data):
        """Implement the ``setExtractionFanDriveFreq`` command."""
        self.assert_enabled()
        await self.run_command(f"setExtractionFanDriveFreq {data.targetFrequency}")

    async def do_setExtractionFanManualControlMode(self, data):
        """Implement the ``setExtractionFanControlMode`` command."""
        self.assert_enabled()
        await self.run_command(f"setExtractionFanControlMode {data.enableManualControlMode}")

    async def do_startExtractionFan(self, data):
        """Implement the ``startExtractionFan`` command."""
        self.assert_enabled()
        await self.run_command("startExtractionFan")

    async def do_stopExtractionFan(self, data):
        """Implement the ``stopExtractionFan`` command."""
        self.assert_enabled()
        await self.run_command("stopExtractionFan")

    async def run_command(self, command: str) -> None:
        pass

def run_atbuilding():
    """Run the ATBuilding CSC."""
    asyncio.run(ATBuildingCsc.amain(index=None))
