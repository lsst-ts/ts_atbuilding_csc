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

import asyncio
import unittest

from lsst.ts import salobj
from lsst.ts.atbuilding import csc
from lsst.ts.xml.enums.ATBuilding import FanDriveState, VentGateState


class ATBuildingTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    def basic_make_csc(
        self, initial_state: salobj.State, config_dir: str | None, simulation_mode: int
    ) -> csc.ATBuildingCsc:
        return csc.ATBuildingCsc(
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
        )

    async def test_open_one_vent(self) -> None:
        """Use openVentGate to open one vent."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            await self.assert_next_sample(
                topic=self.remote.evt_ventGateState,
                state=[VentGateState.CLOSED] * 4,
                flush=False,
            )
            await self.remote.cmd_openVentGate.set_start(gate=[0, -1, -1, -1])
            await asyncio.sleep(1)
            await self.assert_next_sample(
                topic=self.remote.evt_ventGateState,
                state=[VentGateState.OPENED] + [VentGateState.CLOSED] * 3,
                flush=False,
            )

    async def test_open_vents(self) -> None:
        """Use openVentGate to open all vents."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            await self.assert_next_sample(
                topic=self.remote.evt_ventGateState,
                state=[VentGateState.CLOSED] * 4,
                flush=False,
            )
            await self.remote.cmd_openVentGate.set_start(gate=[0, 1, 2, 3])
            await self.assert_next_sample(
                topic=self.remote.evt_ventGateState,
                state=[VentGateState.OPENED] * 4,
                flush=False,
            )

    async def test_close_one_vent(self) -> None:
        """Use closeVentGate to close one vent."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            self.csc.mock_ctrl.vent_states = [VentGateState.OPENED] * 4
            await self.assert_next_sample(
                topic=self.remote.evt_ventGateState,
                state=[VentGateState.OPENED] * 4,
                flush=True,
            )
            await self.remote.cmd_closeVentGate.set_start(gate=[0, -1, -1, -1])
            await self.assert_next_sample(
                topic=self.remote.evt_ventGateState,
                state=[VentGateState.CLOSED] + [VentGateState.OPENED] * 3,
                flush=True,
            )

    async def test_close_vents(self) -> None:
        """Use closeVentGate to close all vents."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            self.csc.mock_ctrl.vent_states = [VentGateState.OPENED] * 4
            await self.assert_next_sample(
                topic=self.remote.evt_ventGateState,
                state=[VentGateState.OPENED] * 4,
                flush=True,
            )
            await self.remote.cmd_closeVentGate.set_start(gate=[0, 1, 2, 3])
            await asyncio.sleep(1)
            await self.assert_next_sample(
                topic=self.remote.evt_ventGateState,
                state=[VentGateState.CLOSED] * 4,
                flush=False,
            )

    async def test_reset_extraction_fan_drive(self) -> None:
        """Use resetExtractionFanDrive to reset the extraction fan drive."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            self.assertFalse(self.csc.mock_ctrl.extraction_fan_drive_was_reset)
            await self.remote.cmd_resetExtractionFanDrive.set_start()
            self.assertTrue(self.csc.mock_ctrl.extraction_fan_drive_was_reset)

    async def test_set_extraction_fan_drive_freq(self) -> None:
        """Use setExtractionFanDriveFreq to set the extraction fan drive
        frequency.
        """
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            await self.remote.cmd_setExtractionFanDriveFreq.set_start(
                targetFrequency=12.5
            )
            self.assertAlmostEqual(self.csc.mock_ctrl.fan_frequency, 12.5)

    async def test_set_extraction_fan_manual(self) -> None:
        """Use setExtractionFanManualControlMode to set the extraction
        fan drive to manual control mode.
        """
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            await self.remote.cmd_setExtractionFanManualControlMode.set_start(
                enableManualControlMode=False
            )
            self.assertFalse(self.csc.mock_ctrl.manual_control_mode)

            await self.remote.cmd_setExtractionFanManualControlMode.set_start(
                enableManualControlMode=True
            )
            self.assertTrue(self.csc.mock_ctrl.manual_control_mode)

    async def test_start_extraction_fan(self) -> None:
        """Use startExtractionFan to start the extraction fan."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            self.csc.mock_ctrl.fan_frequency = 0
            await self.remote.cmd_startExtractionFan.set_start()
            self.assertAlmostEqual(self.csc.mock_ctrl.fan_frequency, 50)

    async def test_stop_extraction_fan(self) -> None:
        """Use stopExtractionFan to stop the extraction fan."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            self.csc.mock_ctrl.fan_frequency = 50
            await self.remote.cmd_stopExtractionFan.set_start()
            self.assertAlmostEqual(self.csc.mock_ctrl.fan_frequency, 0)

    async def test_old_telemetry(self) -> None:
        """Test that the telemetry is published with the old controller."""
        async with self.make_csc(
            initial_state=salobj.State.DISABLED, config_dir=None, simulation_mode=1
        ):
            await self.assert_next_summary_state(salobj.State.DISABLED)

            # Delete the new commands from the mock controller.
            await self.csc.start_mock_ctrl()
            self.csc.mock_ctrl.delete_new_commands()

            # Set the CSC to ENABLED.
            await self.remote.cmd_enable.start()
            await self.assert_next_summary_state(salobj.State.ENABLED)

            # Now ready to go with old controller...

            driveFrequency = (
                await self.remote.tel_extractionFan.next(flush=True)
            ).driveFrequency
            self.assertAlmostEqual(driveFrequency, 0)
            self.csc.mock_ctrl.fan_frequency = 10
            await asyncio.sleep(2)
            driveFrequency = (
                await self.remote.tel_extractionFan.next(flush=True)
            ).driveFrequency
            self.assertAlmostEqual(driveFrequency, 10)

    async def test_new_telemetry(self) -> None:
        """Test that the telemetry is published with the new controller."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            extraction_fan = await self.remote.tel_extractionFan.next(flush=True)
            self.assertAlmostEqual(extraction_fan.driveFrequency, 0)
            if hasattr(extraction_fan, "driveVoltage"):
                self.assertAlmostEqual(
                    extraction_fan.driveVoltage,
                    self.csc.mock_ctrl.drive_voltage,
                    places=2,
                )
            self.csc.mock_ctrl.fan_frequency = 10
            await asyncio.sleep(2)
            extraction_fan = await self.remote.tel_extractionFan.next(flush=True)
            self.assertAlmostEqual(extraction_fan.driveFrequency, 10)
            if hasattr(extraction_fan, "driveVoltage"):
                self.assertAlmostEqual(
                    extraction_fan.driveVoltage,
                    self.csc.mock_ctrl.drive_voltage,
                    places=2,
                )

    async def test_drive_fault_code(self) -> None:
        """Test the fan drive fault code event."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            await self.assert_next_sample(
                topic=self.remote.evt_extractionFanDriveFaultCode,
                state=22,  # default value
                flush=False,
            )
            self.csc.mock_ctrl.fault_codes = [123] * 8
            await self.assert_next_sample(
                topic=self.remote.evt_extractionFanDriveFaultCode,
                state=123,
                flush=False,
            )

    async def test_drive_state(self) -> None:
        """Test the fan drive state event."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            await self.assert_next_sample(
                topic=self.remote.evt_extractionFanDriveState,
                state=FanDriveState.STOPPED,
                flush=False,
            )
            self.csc.mock_ctrl.fan_drive_state = FanDriveState.OPERATING
            await self.assert_next_sample(
                topic=self.remote.evt_extractionFanDriveState,
                state=FanDriveState.OPERATING,
                flush=False,
            )

    async def test_old_controller(self) -> None:
        """Test the CSC with an old controller protocol."""
        async with self.make_csc(
            initial_state=salobj.State.DISABLED, config_dir=None, simulation_mode=1
        ):
            await self.assert_next_summary_state(salobj.State.DISABLED)

            # Delete the new commands from the mock controller.
            await self.csc.start_mock_ctrl()
            self.csc.mock_ctrl.delete_new_commands()

            # Set the CSC to ENABLED.
            await self.remote.cmd_enable.start()
            await self.assert_next_summary_state(salobj.State.ENABLED)


if __name__ == "__main__":
    unittest.main()
