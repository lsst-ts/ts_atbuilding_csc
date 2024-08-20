# This file is part of ts_atbuilding_csc.
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

import unittest
from importlib.util import find_spec
from unittest.mock import AsyncMock

from lsst.ts import salobj
from lsst.ts.atbuilding import csc
from lsst.ts.xml.enums.ATBuilding import VentGateState

RPI_AVAILABLE = find_spec("lsst.ts.vent.controller") is not None


@unittest.skipIf(not RPI_AVAILABLE, "Raspberry Pi not available")
class VentSimulationTest(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    """These tests consider the entire stack from the CSC to the RPi
    controller. They are only run if the RPi is available. They follow
    the general structure of the tests in test_atbuilding_csc.py, but
    are constrained by the features of the simulated RPi.
    """

    def basic_make_csc(self, initial_state, config_dir, simulation_mode):
        return csc.ATBuildingCsc(
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
        )

    async def test_open_one_vent(self):
        """Use openVentGate to open one vent."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=2
        ):
            await self.remote.cmd_openVentGate.set_start(gate=[0, -1, -1, -1])
            await self.assert_next_sample(
                topic=self.remote.evt_ventGateState,
                state=[VentGateState.OPENED] + [VentGateState.CLOSED] * 3,
                flush=True,
            )

    async def test_close_one_vent(self):
        """Use closeVentGate to close one vent."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=2
        ):
            await self.remote.cmd_openVentGate.set_start(gate=[0, -1, -1, -1])
            await self.assert_next_sample(
                topic=self.remote.evt_ventGateState,
                state=[VentGateState.OPENED] + [VentGateState.CLOSED] * 3,
                flush=True,
            )

            await self.remote.cmd_closeVentGate.set_start(gate=[0, -1, -1, -1])
            await self.assert_next_sample(
                topic=self.remote.evt_ventGateState,
                state=[VentGateState.CLOSED] * 4,
                flush=True,
            )

    async def test_reset_extraction_fan_drive(self):
        """Use resetExtractionFanDrive to reset the extraction fan drive."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=2
        ):
            self.csc.simulated_controller.vfd_fault_reset = AsyncMock()
            await self.remote.cmd_resetExtractionFanDrive.set_start()
            self.assertTrue(self.csc.simulated_controller.vfd_fault_reset.called)

    async def test_set_extraction_fan_drive_freq(self):
        """Use setExtractionFanDriveFreq to set the extraction fan drive
        frequency.
        """
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=2
        ):
            await self.csc.simulated_controller.set_fan_frequency(0)
            await self.remote.cmd_setExtractionFanDriveFreq.set_start(
                targetFrequency=12.5
            )
            self.assertAlmostEqual(
                await self.csc.simulated_controller.get_fan_frequency(), 12.5
            )

    async def test_set_extraction_fan_manual(self):
        """Use setExtractionFanManualControlMode to set the extraction
        fan drive to manual control mode.
        """
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=2
        ):
            await self.remote.cmd_setExtractionFanManualControlMode.set_start(
                enableManualControlMode=False
            )
            self.assertFalse(
                await self.csc.simulated_controller.get_fan_manual_control()
            )

            await self.remote.cmd_setExtractionFanManualControlMode.set_start(
                enableManualControlMode=True
            )
            self.assertTrue(
                await self.csc.simulated_controller.get_fan_manual_control()
            )

    async def test_start_extraction_fan(self):
        """Use startExtractionFan to start the extraction fan."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=2
        ):
            await self.csc.simulated_controller.set_fan_frequency(0)
            await self.remote.cmd_startExtractionFan.set_start()
            self.assertAlmostEqual(
                await self.csc.simulated_controller.get_fan_frequency(), 50
            )

    async def test_stop_extraction_fan(self):
        """Use stopExtractionFan to stop the extraction fan."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=2
        ):
            await self.csc.simulated_controller.set_fan_frequency(50)
            await self.remote.cmd_stopExtractionFan.set_start()
            self.assertAlmostEqual(
                await self.csc.simulated_controller.get_fan_frequency(), 0
            )

    async def test_telemetry(self):
        """Test that the telemetry is published."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=2
        ):
            driveFrequency = (
                await self.remote.tel_extractionFan.next(flush=True)
            ).driveFrequency
            self.assertAlmostEqual(driveFrequency, 0)
            await self.csc.simulated_controller.set_fan_frequency(10)
            driveFrequency = (
                await self.remote.tel_extractionFan.next(flush=True)
            ).driveFrequency
            self.assertAlmostEqual(driveFrequency, 10)


if __name__ == "__main__":
    unittest.main()
