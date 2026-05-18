v0.2.3 (2026-05-18)
===================

New Features
------------

- Added reconnect retry handling for unexpected controller disconnects. (`OSW-2112 <https://rubinobs.atlassian.net//browse/OSW-2112>`_)


Bug Fixes
---------

- Added functionality to fault if the controller disconnects. (`OSW-1789 <https://rubinobs.atlassian.net//browse/OSW-1789>`_)


v0.2.2 (2026-01-26)
===================

Performance Enhancement
-----------------------

- Updated ts-conda-build dependency version and conda build string. (`OSW-1277 <https://rubinobs.atlassian.net//browse/OSW-1277>`_)



v0.2.1
======

* Reconfigured connect/disconnect to use `handle_summary_state`.

v0.2.0
======

* Added the `driveVoltage` telemetry and the `maximumDriveFrequency` event.

v0.1.1
======

* Added safeguards to avoid race conditions in unit tests as much as possible.

v0.1.0
======
* Initial implementation of the ATBuilding CSC functionality.
