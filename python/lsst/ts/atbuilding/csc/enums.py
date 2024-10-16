# This file is part of ts_atdome.
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

import enum


class ErrorCode(enum.IntEnum):
    """CSC error codes when going to fault state."""

    TCPIP_CONNECT_ERROR = 1
    TCPIP_READ_ERROR = 2
    CANNOT_START_MOCK_CONTROLLER = 3
    MOCK_CTRL_START_ERROR = 4
