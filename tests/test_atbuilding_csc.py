# This file is part of ts_atbuilding_csc.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import asyncio
import unittest
from unittest.mock import patch

from lsst.ts import salobj
from lsst.ts.atbuilding import csc
from lsst.ts.atbuilding.csc import building_csc
from lsst.ts.atbuilding.csc.enums import ErrorCode
from lsst.ts.xml.enums.ATBuilding import FanDriveState, VentGateState

STD_TIMEOUT = 30.0


class ATBuildingTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    def basic_make_csc(
        self, initial_state: salobj.State, config_dir: str | None, simulation_mode: int
    ) -> csc.ATBuildingCsc:
        return csc.ATBuildingCsc(
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
        )

    async def wait_for_vent_gate_state(
        self, expected_state: list[VentGateState], timeout: float = STD_TIMEOUT
    ) -> None:
        expected = [int(state) for state in expected_state]

        async def wait_for_match() -> None:
            while True:
                data = await self.remote.evt_ventGateState.next(flush=False)
                actual = [int(state) for state in data.state]
                if actual == expected:
                    return

        await asyncio.wait_for(wait_for_match(), timeout=timeout)

    async def test_open_one_vent(self) -> None:
        """Use openVentGate to open one vent."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            await self.wait_for_vent_gate_state([VentGateState.CLOSED] * 4)
            await self.remote.cmd_openVentGate.set_start(gate=[0, -1, -1, -1])
            await self.wait_for_vent_gate_state(
                [VentGateState.OPENED] + [VentGateState.CLOSED] * 3
            )

    async def test_open_vents(self) -> None:
        """Use openVentGate to open all vents."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            await self.wait_for_vent_gate_state([VentGateState.CLOSED] * 4)
            await self.remote.cmd_openVentGate.set_start(gate=[0, 1, 2, 3])
            await self.wait_for_vent_gate_state([VentGateState.OPENED] * 4)

    async def test_close_one_vent(self) -> None:
        """Use closeVentGate to close one vent."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            self.csc.mock_ctrl.vent_states = [VentGateState.OPENED] * 4
            await self.wait_for_vent_gate_state([VentGateState.OPENED] * 4)
            await self.remote.cmd_closeVentGate.set_start(gate=[0, -1, -1, -1])
            await self.wait_for_vent_gate_state(
                [VentGateState.CLOSED] + [VentGateState.OPENED] * 3
            )

    async def test_close_vents(self) -> None:
        """Use closeVentGate to close all vents."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            self.csc.mock_ctrl.vent_states = [VentGateState.OPENED] * 4
            await self.wait_for_vent_gate_state([VentGateState.OPENED] * 4)
            await self.remote.cmd_closeVentGate.set_start(gate=[0, 1, 2, 3])
            await self.wait_for_vent_gate_state([VentGateState.CLOSED] * 4)

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

    async def test_timed_out_command_does_not_poison_next(self) -> None:
        """A command whose response arrives after run_command times out must
        not have that late response delivered to the next command of the same
        name.

        Regression test: responses were once matched to commands only by a
        shared, per-name queue, so a reply that arrived after the 1 s timeout
        stayed queued and was handed to the *next* same-named command, shifting
        every subsequent response by one.
        """
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            assert self.csc.mock_ctrl is not None

            command = "get_fan_drive_max_frequency"

            # Hold the controller's reply to the first call until we release
            # it, so the CSC-side run_command is guaranteed to time out first.
            release_first = asyncio.Event()
            call_count = 0

            async def slow_first() -> float:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    await release_first.wait()
                return self.csc.mock_ctrl.max_frequency

            self.csc.mock_ctrl.get_fan_drive_max_frequency = slow_first

            with patch.object(building_csc, "TCP_TIMEOUT", 0.5):
                # First command: the controller stalls, so this times out. The
                # value it will *eventually* report is deliberately distinct.
                self.csc.mock_ctrl.max_frequency = 111.0
                with self.assertRaises(asyncio.TimeoutError):
                    await self.csc.run_command(command)

                # Now let the stalled first response come back (late). It must
                # be discarded, not saved for the next command.
                release_first.set()
                await asyncio.sleep(0.1)

                # Second command gets its OWN response, not the stale 111.0.
                self.csc.mock_ctrl.max_frequency = 222.0
                response = await self.csc.run_command(command)
                self.assertAlmostEqual(response["return_value"], 222.0)

            # No leftover waiters remain for that command name.
            self.assertEqual(len(self.csc.response_waiters[command]), 0)

    async def test_unexpected_disconnect_reconnects(self) -> None:
        """Test that an unexpected disconnect reconnects successfully."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            assert self.csc.mock_ctrl is not None
            await self.csc.start_mock_ctrl()

            await asyncio.sleep(1)
            self.remote.evt_errorCode.flush()
            self.remote.evt_summaryState.flush()

            with (
                patch.object(building_csc, "RECONNECT_INITIAL_DELAY", 0.01),
                patch.object(building_csc, "RECONNECT_BACKOFF", 1.0),
                patch.object(building_csc, "RECONNECT_MAX_RETRIES", 2),
            ):
                original_reconnect_task = self.csc.reconnect_task
                await self.csc.mock_ctrl.close()

                with self.assertRaises(salobj.AckError):
                    await self.remote.cmd_openVentGate.set_start(gate=[0, -1, -1, -1])

                async def wait_for_reconnect_start() -> None:
                    while self.csc.reconnect_task is original_reconnect_task:
                        await asyncio.sleep(0.05)

                await asyncio.wait_for(wait_for_reconnect_start(), timeout=5)
                await asyncio.wait_for(
                    asyncio.shield(self.csc.reconnect_task), timeout=5
                )
                await self.remote.cmd_openVentGate.set_start(gate=[0, -1, -1, -1])
                await self.wait_for_vent_gate_state(
                    [VentGateState.OPENED] + [VentGateState.CLOSED] * 3
                )

    async def test_unexpected_disconnect_faults_after_retries(self) -> None:
        """Test that reconnect retries exhaust to UNEXPECTED_DISCONNECT."""
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=None, simulation_mode=1
        ):
            assert self.csc.mock_ctrl is not None
            await self.csc.start_mock_ctrl()

            await asyncio.sleep(1)
            self.remote.evt_errorCode.flush()
            self.remote.evt_summaryState.flush()

            connect_attempts = 0

            async def fake_connect(allow_fault: bool = True) -> bool:
                nonlocal connect_attempts
                connect_attempts += 1
                return False

            with (
                patch.object(building_csc, "RECONNECT_INITIAL_DELAY", 0.01),
                patch.object(building_csc, "RECONNECT_BACKOFF", 1.0),
                patch.object(self.csc, "connect", fake_connect),
            ):
                await self.csc.mock_ctrl.close()

                await self.assert_next_summary_state(salobj.State.FAULT)
                await self.assert_next_sample(
                    topic=self.remote.evt_errorCode,
                    errorCode=int(ErrorCode.UNEXPECTED_DISCONNECT),
                    flush=False,
                )
                self.assertEqual(connect_attempts, building_csc.RECONNECT_MAX_RETRIES)


if __name__ == "__main__":
    unittest.main()
