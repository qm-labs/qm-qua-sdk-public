# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## Unreleased


## [1.2.3a1] - 2025-05-11

- Requires Python >=3.8, <3.13
- Tested against QOP 3.4


### Fixed
- Fixed a bug that caused `generate_qua_script` to raise an error when attempting to serialize a program and configuration without a `QuantumMachineManager` instance opened.


## [1.2.2] - 2025-04-01

- Requires Python >=3.8, <3.13
- Tested against QOP 3.3, 2.4.4


## [1.2.2a4] - 2025-03-20

- Requires Python >=3.8, <3.13

### Added
- Added `qm.qua.type_hints` file to allow the import of type hints relevant to the QUA DSL.

### Fixed
- `qm.get_config()` and `job.get_compilation_config()` now return the correct default values for analog output filters.
- The `Math.dot()` function in qm.qua.lib supports different data types for the x and y arguments.

### Changed
- Made parameters `feedforward` and `feedback` optional in `qm.set_output_filter_by_element` (OPX+)


## [1.2.2a3] - 2025-03-04

- Requires Python >=3.8, <3.13
- Tested against QOP 3.3

### Fixed
- Fixed `mypy` returning false positive type errors.
- The DSL now is fully typed.
- A `JobNotFoundException` is now raised when trying to get a job that does not exist (using functions - `qm.get_job`, `qm.get_job_by_id()` and `qmm.get_job()`).
- Fixed a QUA program serialization error casued by malparsing of certain variable names.
- Fixed wrong serialization for a random number with a seed.
- QOP 3.3 - It is now possible to fetch results with a large number of data points, and it will not result in a gRPC timeout.
- Fixed a bug that prevented calibration of octave with frequencies of type np.int32.

### Changed
- Supports the new simulator flow in QOP 3.3 in which the `simulate` command becomes non-blocking and the job object can be interacted with. Most Job APIs are not supported yet.
- `qm.get_job()`, `qm.get_job_by_id()` and `qmm.get_job()` can now return a simulated job.
- Added new fields for filters in the LF-FEM config: `exponential` and `high_pass`. These are used in QOP 3.3 for a new mechanism for analog output IIR filters.
- Improved labels for the simulators' samples plot and waveform report plot
- The simulator's samples plot will no longer plot waveforms that are all zeros (not changed in the simulation)
- Refined connection error handling: Errors are now caught specifically for connection issues, rather than broadly across larger scopes as was previously the case. 

### Added
- Added `broadcast` object to the QUA DSL, supporting the functions: `broadcast.and_()`, `broadcast.or_()` and `broadcast.xor_()`, supported from QOP 3.3.
- Raise an error when trying to fetch results but there is data loss on the OPX1000
- Added the ability to export the capabilities of the QOP, using `qmm.capabilities`.
- Added the ability to set capabilities without connecting to a QOP server, using the static function `QuantumMachinesManager.set_capabilities_offline()`.
- Added arguments to the constructor of `QuantumMachinesManager` to allow control of the connection redirection:
  - `follow_gateway_redirections` (bool): If True (default), the client will follow redirections to find a QuantumMachinesManager and Octaves. Otherwise, it will only connect to the given host and port.
  - `async_follow_redirects` (bool): If False (default), async httpx will not follow redirections, relevant only in case follow_gateway_redirections is True.
  - `async_trust_env` (bool): If True (default), async httpx will read the environment variables for settings as proxy settings, relevant only in case follow_gateway_redirections is True.


### Deprecated
- The `measure` command signature has changed, `stream` has been renamed `adc_stream` and moved to the end of the arguments list. The old signature is deprecated and will be removed in the future.
- The field `outputPulseParameters` in the element part of the config has been deprecated and will be replaced with the field `timeTaggingParameters`.
- `"Ascending"` and  `"Descending"` have been deprecated and are replaced by `"Above"` and `"Below"` for the fields of the polarity in `timeTaggingParameters`
- The field `thread` in the element part of the config has been deprecated and will be replaced with the field `core`.
- In QOP >= 3.3, the function `fast_frame_rotation` is deprecated as it is no longer faster than frame_rotation_2pi (and in fact, it is less efficient). It will be removed in future versions.


## [1.2.2a2] - 2024-12-11

- Requires Python >=3.8, <3.13

### Fixed
- Fixed the function `job.update_oscillator_frequency` to work on the latest QOP 3.2.
- Fixed a bug for OPX1000 in which `qm.get_digital_delay()` would return the digital buffer instead.
- Fix usage of removeprefix for Python 3.8 compatibility.

### Deprecated
- The method `job.update_oscillator_frequency` is replaced by `job.set_converter_frequency` and will be removed in the future.

### Changed
- Improved the implementation of `wait_for_all_values` in OPX1000 to reduce latency.

## [1.2.2a1] - 2024-11-28

- Requires Python >=3.8, <3.13

### Added
- Added the method `add_octave_to_opx_port_mapping` to the `QmOctaveConfig`. When defined, it allows calibration of an Octave connected to multiple FEMs. This method is deprecated and will be removed in the future.
- Added `AbstractCalibrationDB` class to allow for custom Octave calibration databases. (`from qm.octave import AbstractCalibrationDB`)
- `QuantumMachinesManager` can now accept an object of type `AbstractCalibrationDB` in its `octave_calibration_db_path` argument

## [1.2.1.1a1] - 2024-12-17

- Requires Python >=3.8, <3.13

### Fixed
- Fixed a bug in the MW-FEM samples returned from the cloud simulator (using `qm-saas`) which prevented plotting them

### Changed
- Improved labels for the simulators' samples plot and waveform report plot
- The simulator's samples plot will no longer plot waveforms that are all zeros (not changed in the simulation)

## [1.2.1] - 2024-11-20

- Requires Python >=3.8, <3.13
- Tested against QOP 2.4, 3.2

### Fixed
- Fixed a bug with qm.get_config() in the OPX1000.


## [1.2.1a3] - 2024-11-06

- Requires Python >=3.8, <3.13

### Fixed
- Fixed serialization for the `.image()` and `.real()` operations in the stream processor.
- Fixed a false positive `Cable swap detected` error when opening a QuantumMachine with an octave when the order of the ports in the controller does not match the octave definition.

### Added
- Python 3.12 is now supported.
- Serializing a QUA program after it was executed will now also include the `CompilerOptions` it was executed with.

## [1.2.1a2] - 2024-09-16

- Requires Python >=3.8, <3.12
- Tested against QOP 3.2

### Changed
- Changed the package license to BSD-3
- The configuration of the digital upconverters of the MW-FEM (OPX1000) is now done in ports instead of elements, the elements now reference the relevant upconverter through the MWInput/MWOutput part of the config.
- `qmm.version()` - Return type has changed, `qmm.version_dict()` will give the same output as `qmm.version()` did in previous versions.
- Setting `close_other_qm=True` when opening a qm will no longer close **all** qms, it will only close those that are blocking the new qm (Using the same ports). If you wish to close **all** qms, please use `qmm.close_all_qms()` before.

### Fixed
- Fixed an octave bug that raised an error when trying to run get_lo_source() from RF input 2
- Fixed the way connection to octave upconverters is done, to allow for more than one upconverter to same opx ports.
- Fixed `qm.get_config()` for a config with OPX1000
- Fixed a bug when opening a QM with an OPX1000, when `close_other_qm` to false, it will no longer close other quantum machines and will raise an error if a QM cannot be opened. 

### Added
- Added support of 2 Gs/s sampling rate in LF-FEM analog inputs (OPX1000 only)
- Added a QUA function for resetting global phase - `reset_global_phase`
- Octave calibrations can be done now with the octave connected to two different FEMS/controllers.
- Added an `octave_calibration_db_path` argument to the `QuantumMachinesManager` constructor that can be set when opening a `QuantumMachinesManager`.
- Added an option to set the `octave_calibration_db_path` in the `UserConfig` file.

### Deprecated
- The method `reset_phase` is replaced by `reset_if_phase` and will be removed in the future.
- `octave_config.set_calibration_db` in moved to the `QuantumMachinesManager` class.

### Removed
- The following deprecated files were removed:
    - QmJob.py - Class can be imported directly `from qm`.
    - QmPendingJob.py - Class can be imported directly `from qm`.
    - QmQueue.py - Class can be imported directly `from qm`.
    - Program.py - Class can be imported directly `from qm`.
    - QuaNodeVisitor.py - Class can be imported `from qm.serialization.qua_serializing_visitor`.
    - `capabilities.py` - Can be imported `from qm.api.models.capabilitie`.
    - `logger.py` - To use, `import logging` and then `logging.getLogger("qm")`.

- The following deprecated methods were removed: 
    - `save_to_store` - Function is removed.
    - `job.id()` - Function removed, use `job.id` instead. 
    - `qm.manager()` - Function removed. 
    - `qm.peek()` - Function removed. 
    - `qm.poke()` - Function removed. 
    - `qmm.close()` - Function removed.

## [1.2.1a1] - 2024-07-30

- Requires Python >=3.8, <3.12
- Tested against QOP 2.4.1

### Added
- Added new math functions - atan, atan_2pi, atan2, atan2_2pi - supported from QOP 2.4.
- When getting the devices using 'qmm.get_devices()', temperature information will also be returned (not available for OPX1000 yet).
- Added an optional flag 'keep_dc_offsets_when_closing' to 'open_qm()' that prevents resetting the DC voltages back to zero when the QM is closed (not available for OPX1000 yet).

### Fixed
- At the end of the calibration, dc-offsets are set to their initial values, and not to the last values calibrated (both inputs and outputs).

### Changed
- After calibration, dc offsets are set only if found LO *and* IF frequencies that match the current element state. 

## [1.2.0] - 2024-07-02

- Requires Python >=3.8, <3.12
- Tested against QOP 3.1

**Note, this version was [Yanked](https://pypi.org/help/#yanked), it was supposed to be pre-released as 1.2.0a1**

### Changed
- QuantumMachinesManager API
    - `qmm.get_controllers()` - returns also the types of the FEMs they contain.  For QOP2.x (OPX+) it returns single FEM.
    - QOP 3.x (OPX1000) users will get a new object based return when calling `qmm.version()`. For QOP 2.x (OPX+) users the returned object stays the same.

- QuantumMachine API
    - When closing a QM with `qm.close()`, `None` will be returned instead of `True`.

- Job API
    - `job.id` is changed to `job.get_job_id()`.
    - When a job has data loss, an error is raised instead of a warning.

- General
    - Simulation of MW signals returns a complex signal of the I and Q quadratures, before the upconversion.
    - The MW-FEM ADC stream is returned as a complex float representing the I and Q quadratures.

### Fixed
- Fixed a bug that opened a redundant communication with Octaves in the cluster when opening a QM, even if the Octaves were not in the config.
- Removed the duplication of keys we have in simulation results, keys are now prefixed with "1-" or "2-" to indicate the fem index (also for OPX).
- Fixed an error that occurred when setting the Octave to default connectivity and also adding the OPX input ports manually to the readout element.
- Fixed a bug introduced in 1.1.7 that prevented multiple Octaves to be used in the same QM in some cases.
- Fixed validation of the pulse configuration to catch typos in operation value.
- Fixed a bug that set the Octave's input attenuators to 0 regardless of the config.
- At the end of the calibration, dc-offsets are set to their initial values, and not to the last values calibrated.

### Added
- QuantumMachinesManager API
    - Added `qmm.list_open_qms()` which replaced `qmm.list_open_quantum_machines()`. 
    - Added `qmm.close_all_qms()` which replaced `qmm.close_all_quantum_machines()`. 
    - Added `qmm.get_jobs(filter_options)` to get a list of jobs that match the filter options. This function is currently only available for QOP 3.x (OPX1000) users.
    - Added `qmm.get_job(job_id)` to get an instance of running job by its ID. This function is currently only available for QOP 3.x (OPX1000) users.
    - Added `qmm.get_job_result_handles(job_id)` to get the results of a job by its ID. This is a backwards compatible solution that will be also removed soon.
    - Added `qmm.get_devices()` which returns both the OPX controllers and also the Octaves connected to the system.

- QuantumMachine API
    - Added `qm.update_config(config)` function that sets/update the **physical** properties of the qm. This function is currently only available for QOP 3.x (OPX1000) users.
    - Added `qm.get_jobs(filter_options)` to get the jobs on the current machine.

- Job API - These function are currently only available for QOP 3.x (OPX1000) users.
    - Added `job.get_compilation_config()` that returns the config with which the running program was compiled.
    - Added `job.__str__` and `job.__repr__` methods for the `QmJob` class.
    - Added `job.get_status()` to get the status of a job.
    - Added `job.set_io_values()` to set the IO values to the running program.
    - Added `job.set_io1_value()` to set the IO value to the running program.
    - Added `job.set_io2_value()` to set the IO value to the running program.
    - Added `job.get_io_values(io1_type, io2_type)` to get the IO values from the running program.
    - Added `job.get_io1_values(as_type)` to get the IO value from the running program.
    - Added `job.get_io2_values(as_type)` to get the IO value from the running program.
    - Added `job.wait_until(status)` to get the job status.
    - Added `job.is_running()` to check if the program is still actively running.
    - Added `job.is_finished()` to check if the program is done (or canceled, or has an error).
    - Added `job.set/get_element_correction(...)` to set/get the correction matrix currently used by the element.
    - Added `job.set/get_intermediate_frequency(...)` to set/get the current intermediate frequency of the element
    - Added `job.set/get_output_digital_delay(...)` to set/get the current digital delay of the element's port.
    - Added `job.set/get_output_digital_buffer(...)` to set/get the current digital buffer of the element's port.
    - Added `job.set/get_output_dc_offset_by_element(...)` to set/get the current dc offset of the element's port.
    - Added `job.update_oscillator_frequency(...)` to update the MW-FEM upconverter and downconverter frequencies.

- Job API
    - Added `job.push_to_input_stream()` which replaces `job.insert_input_stream()`
    - Added `job.cancel()` which cancels a job in the queue or halts a running job.

- QUA
    - `dual_demod.full()` can now be called without referencing the element's outputs, and default values are set: `dual_demod.full("cos", "sin", I)` -> `dual_demod.full("cos", "out1", "sin", "out2", I)`. This is compatible with performing demodulation with the MW-FEM. 
    - A new QUA context manager `port_condition` is introduced that allows faster conditional play for the entire port, supported with the MW-FEM.

- Config
    - Added an FEM type called `MW`, which has its own set of properties. 
    - There is a new input to an element called `MWInput`, that references one output port in the MW-FEM.
    - There is a new output called `MWOutput`, that references one input port in the MW-FEM.

- General
    - Added two new stream processing commands `.real()` and `.image()`, that can be applied to a MW-FEM ADC stream.

### Deprecated
- QuantumMachinesManager API
    - `qmm.list_open_quantum_machines()` has been replaced by `qmm.list_open_qms()`
    - `qmm.close_all_quantum_machines()` has been replaced by `qmm.close_all_qms()`
    - `qmm.open_qm_from_file()` is deprecated and will be removed in the future.
    - `qmm.clear_all_job_results()` is deprecated and will be removed in the future.

- QuantumMachine API - These changes are currently only for QOP 3.x (OPX1000) users
    - `save_config_to_file` is deprecated and will be removed in the future.
    - The following methods will be moved to the job API:
        - `qm.get_digital_buffer()` -> `job.get_output_digital_buffer()`
        - `qm.set_digital_buffer()` -> `job.set_output_digital_buffer()`
        - `qm.get_digital_delay()` -> `job.getoutput__digital_delay()`
        - `qm.set_digital_delay()` -> `job.setoutput__digital_delay()`
        - `qm.get_input_dc_offset_by_element()` -> `job.get_input_dc_offset_by_element()`
        - `qm.set_input_dc_offset_by_element()` -> `job.set_input_dc_offset_by_element()`
        - `qm.get_io1_value()` -> `job.get_io1_value()`
        - `qm.set_io1_value()` -> `job.set_io1_value()`
        - `qm.get_io2_value()` -> `job.get_io2_value()`
        - `qm.set_io2_value()` -> `job.set_io2_value()`
        - `qm.get_io_values()` -> `job.get_io_values()`
        - `qm.set_io_values()` -> `job.set_io_values()`
        - `qm.get_intermediate_frequency()` -> `job.get_intermediate_frequency()`
        - `qm.set_intermediate_frequency()` -> `job.set_intermediate_frequency()`
        - `qm.get_output_dc_offset_by_element()` -> `job.get_output_dc_offset_by_element()`
        - `qm.set_output_dc_offset_by_element()` -> `job.set_output_dc_offset_by_element()`
    - The following methods will be deprecated, these values can be set/get from the config:
        - `qm.set_mixer_correction()`
        - `qm.get_smearing()`
        - `qm.get_time_of_flight()`
        - `qm.list_controllers()`
    - The following methods will be deprecated:
        - `qm.get_running_job()`
    - `qm.queue` is being deprecated, management of the queue is moving to the QM itself:
        - `qm.queue.count()` -> `qm.get_queue_count()`
        - `qm.queue.pending_jobs()` -> `qm.get_pending_jobs()`
        - `qm.queue.add()` -> `qm.add_to_queue()`
        - `qm.queue.add_compiled()` -> `qm.add_compiled()`
        - `qm.queue.clear()` -> `qm.clear_queue()`
        - `qm.queue.get()` -> `qm.get_job_by_id()`
        - `qm.queue.get_by_user_id()` -> `qm.get_jobs_by_user_id()`
        - `qm.queue.remove_by_user_id()` -> `qm.clear_jobs_by_user_id()`
    - `qm.queue` is being deprecated, this methods will be removed in the future:
        - `qm.queue.add_to_start()`
        - `qm.queue.get_at()`
        - `qm.queue.remove_by_id()`
        - `qm.queue.remove_by_position()`

- Job API
    - `job.insert_input_stream()` is renamed to `job.push_to_input_stream()`
    - `job.halt()` is renamed to `job.cancel()`.
    
- Job API - These changes are currently only for QOP 3.x (OPX1000) users
    - The `job.status` property is deprecated, and will be removed in the future. Please use `job.get_status()`, which has a different return type.
    - `job.position_in_queue()` is deprecated and will be removed in the future.
    - `job.wait_for_execution()` is deprecated and will be removed in the future. Please use `job.wait_until("Running")` instead.
    - The property `job.manager` has been removed.

## [1.1.7] - 2024-02-19

- Requires Python >=3.8, <3.12
- Tested against QOP 1.2, 2.2

### Changed
- Changed the flag `check_for_errors` default, in all fetching functions, to `True`. This will produce a warning if any run-time errors are detected during the job execution.
- Importing everything from `qm.qua` (`from qm.qua import *`) will no longer import external libraries such as NumPy and logging.

### Fixed
- Fixed a bug that disabled external loggers when importing the qm-qua package.
- Fixed a bug that prevented the waveform reporting from generating.
- Fixed the plot label units in the waveform report.
- Optimized the program's execution latency, especially for larger programs.
- Optimized the latency for setting and reading the Octave's LO frequency.
- Speed up QMM initialization by removing an unneeded call to Octave clients.
- Fixed the Octave calibration algorithm to shut down upconverters and downconverters during calibration, so that the calibration will not be affected by RF in.
- Fixed cases in which compilation errors related to elements were given without a location.
- Fixed a bug that prevents setting the downconverter's frequency when connected through a loopback.
- Fixed a bug that prevented connecting one pair of OPX outputs to different Octave upconverters.

### Added
- Added the option to receive Octaves with the cluster when opening a QuantumMachinesManager, instead of manually giving their addresses using `OctaveConfig`. This requires QOP 2.4.0 or above.
- Added `program.to_protobuf(config)` and `program.to_file('my_program.pb', config)` to save a program to memory or to disk.
- Added `Program.from_protobuf(config)` and `Program.from_file('my_program.pb', config)` to load a serialized program from memory or to disk.
- Added support for OPX1000 – The config controller seciotn now accepts a controller of type "OPX1000", and the element’s input and output ports can now indicate which FEM is to be used.
- `Variable` class is now exported to allow type checking.
- Connections’ headers are now forwarded to the Octaves.
- Connections’ headers are now indicating to which device the message belongs to.

### Deprecation
- Deprecated old Octave configuration API; these functions will be removed in a future version.
- Deprecated `Program.build`; this function will be removed in the next minor version. Instead, you can use `Program.qua_program`.


### Removed
- Dropped support of Python 3.7.

### Known Issues
- At the end of the Octave calibration, dc-offsets stay at the last values calibrated.
- Connecting an octave to two or more FEMs / OPX+es is unsupported and will give an undescriptive error.
- An Octave connected to a 2 Gs/s OPX1000 port will not calibrate and will give a compilation error. As a workaround, set the port to 1 Gs/s, calibrate, and then set it back to 2 Gs/s.


## [1.1.6] - 2023-11-19
### Fixed
- Fixed the serialization if a list was used for port definition instead of a tuple
- Fixed a bug which prevented the waveform reporting from generating plots (bad encoding)

### Added
- When empty loopback is given, it is treated as no loopbacks interface.
- Python 3.11 is now supported


## [1.1.5.1] - 2023-10-30
### Fixed
- Downgrading from this version will not break the Octave (Introduced in 1.1.5)
- Saving timestamps directly to a string will now not mess up adc saving
- Improved serialization handling of streams, fixes issues in some cases


## [1.1.5] - 2023-10-22

**Note, this version was [Yanked](https://pypi.org/help/#yanked), downgrading from this version could lead to issues, this was fixed in 1.1.5.1**

### Fixed
- Fixed simulations with negative IF frequency (in mixer).
- Deprecation warnings will now be shown for imports in IPython
- Improved octave calibration algorithm.

### Added
- Added new API for octave configuration, through the QUA config dict (except for the octave's IP and port) 

### Deprecation
- All the functions that config octave through the OctaveConfig object
- All the functions that config the octave through the QMOctave object 

## [1.1.4] - 2023-09-07
### Deprecation
- Starting from version 1.2.0, `QuantumMachinesMananger.version()` will have a different return type.
- `ServerDetails.qop_version` has been renamed to `ServerDetails.server_version`.

### Added
- Added `QuantumMachinesMananger.version_dict()` which returns a dict with two keys `qm-qua` and `QOP`.
- Two new keys were added to the dict returned by `QuantumMachinesMananger.version()`: `qm-qua` and `QOP`. 

### Fixed
- Fixed missing import of `ClockMode`.
- Fixed simulations with negative IF frequency (in mixer).
- Fixed simulations with the new sticky API.
- Fixed conversion back to ns of the sticky duration for the config received from the OPX.
- Fixed rare cases in which the octave failed to boot.
- Fixed the serialization for a list in a `.maps(FUNCTION.average(list))` call in the stream processing. 
- Serialization will now not give an error if it fails to generate a config with the QMM configuration.
- Intermediate frequency returns with the same sign as it was set in te config. 
- Deprecation warnings are now shown by default.

### Changed
- If no port is given to `QuantumMachinesManager`, and there isn't a saved configuration file, it will default to `80` (instead of `80` & `9510`)


## [1.1.3] - 2023-05-29
### Fixed
- Fixed negative IF freq handling in config builder
- Sticky Element duration is to be given in ns and not clock cycles
- Fixed a bug that prevents opening many QMMs/QMs due to thread exhaustion when creating Octave clients. 
- The deprecated `strict` and `flags` arguments now work but give a deprecation warning. 
- Fixed the version of typing-extensions, to prevent import-error


## [1.1.2] - 2023-05-11
### Deprecation
- Moved `qm.QuantumMachinesManager.QuantumMachinesManager` path to `qm.quantum_machines_manager.QuantumMachinesManager`. Old path will be removed in 1.2.0

### Added
- Added `qmm.validate_qua_config()` for config validation without opening a qm
- Added support for getting clusters by name in `QuantumMachinesManager` 
- Added a `py.typed` file, that marks the package as supporting type-hints.
- Added a default (minimal) duration for sticky elements
- Added `qm.get_job(job_id)` to retreieve previously ran jobs

### Fixed
- Fixed creating credentials for authentication in gRPC
- Removed redundant entry from element generated class (`up_converted`)
- Float frequency support - fixed the creation of config classes so integer frequency will always exist
- Fixed creating a mixer dict-config from protobuf class instance
- Fixed error raised when fetching saved data in the backwards compatible
- Fixed creating a digital port dict-config from protobuf class instance
- Fixed event-loop Windows bug of creating multiple instances of QuantumMachine

## [1.1.1] - 2023-03-20
### Fixed
- Fixed long delay while waiting for values

## [1.1.0] - 2023-03-16

**Note, this version (and all future versions) does not support QOP 2.0.0 or 2.0.1**

### Deprecation
- The `hold_offset` entry in the config is deprecated and is replaced by a new `sticky` entry with an improved API
- Moved `_Program` path to `qm.program.program.Program`. Old path will be removed in 1.2.0
- Moved `QmJob` path to `qm.jobs.qm_job.QmJob`. Old path will be removed in 1.2.0
- Moved `QmPendingJob` path to `qm.jobs.pending_job.QmPendingJob`. Old path will be removed in 1.2.0
- Moved `QmQueue` path to `qm.jobs.job_queue.QmQueue`. Old path will be removed in 1.2.0
- Renamed `JobResults` into `StreamingResultFetcher`. Old name will be removed in 1.2.0
- Moved `StreamingResultFetcher` path to `qm.results.StreamingResultFetcher`. 
- `QmJob.id()` is deprecated, use `QmJob.id` instead, will be removed in 1.2.0
- `QmJob` no longer has `manager` property 
- `QmPendingJob.id()` is deprecated, use `QmPendingJob.id` instead, will be removed in 1.2.0
- `QuantumMachine` no longer has `manager` property
- `QuantumMachine.peek` is removed (was never implemented)
- `QuantumMachine.poke` is removed (was never implemented)
- `IsInt()` function for qua variables is deprecated, use `is_int()` instead, will be removed in 1.2.0
- `IsFixed()` function for qua variables is deprecated, use `is_fixed()` instead, will be removed in 1.2.0 
- `IsBool()` function for qua variables is deprecated, use `is_bool()` instead, will be removed in 1.2.0 
- `set_clock` method of the octave changed API, old API will be removed in 1.2.0.
- Deprecated the `strict` and `flags` kwargs arguments in the `execute` and `simulate` functions.

### Added
- Added autocorrection for config dict in IDEs, when creating a config, add the following: `config: DictQuaConfig = {...}`.
- Added the option to invert the digital markers in a quantum machine by indicating it in the config.
- Support `fast_frame_rotation`, a frame rotation with a cosine and sine rotation matrix rather than an angle.  
- Added support for floating point numbers in the `intermediate_frequency` field of `element` .
- Conditional `play` is extended to both the digital pulse if defined for operation. 
- Extended the sticky capability to include the digital pulse (optional)
- Added option to validate QUA config with protobuf instead of marshmallow. It is usually faster when working with large configs, to use this feature, set `validate_with_protobuf=True` while opening a quantum machine.
- Added type hinting for all `qua` functions and programs
- Added another way of getting results from job results: `job.result_handles["result_name"]`.`
- Octave reset request command added to "Octave manager".
- Added support for octave configuration inside the QUA-config dictionary, this will later deprecate the `OctaveConfig` object, which is still supported
- Added objects that reflects the elements in the `QuantumMachine` instance.
- Added the waveform report for better displaying simulation results.

### Changed
- Updated `play` docstrings to reflect that the changes to conditional digital pulse.
- Changed octave's `set_clock` API.
- Changed and improved internal grpc infrastructure
- Changed and improved async infrastructure

## [1.0.2] - 2023-01-01
### Removed
- Removed deprecated `math` library (use {class}`~qm.qua.lib.Math` instead).
- Removed deprecated `qrun_` context manager (use {func}`~qm.qua._dsl.strict_timing_` instead).

### Added
- Better exception error printing.
- An api to add more information to error printing `activate_verbose_errors`
- Add support for OPD (Please check [the OPD documentation](https://qm-docs.qualang.io/hardware/dib) for more details).
- Added timestamps for {func}`~qm.qua._dsl.play` and {func}`~qm.qua._dsl.measure` statements.
- Support for numpy float128.
- Added the function {func}`qm.user_config.create_new_user_config` to create a configuration file with the QOP host IP & Port to allow opening {func}`~qm.QuantumMachinesManager.QuantumMachinesManager` without inputs.
- Added infrastructure for anonymous log sending (by default, no logs are sent).

### Fixed
- Serializer - Added support for averaging on different axes.
- Serializer - Remove false message about lacking `play(ramp()...)` support.
- Serializer - Fixed the serialization when `.length()` is used.
- Serializer - Fixed cases in which the serializer did not deal with `adc_trace=true` properly.
- Serializer - The serializer does not report failed serialization when the only difference is the streams' order.
- Serializer - The serializer now correctly serialize the configuration when an element's name has a `'`.

## [1.0.1] - 2022-09-22
### Changed
- Octave - Added a flag to not close all the quantum machines in {func}`~qm.octave.qm_octave.QmOctaveBase.calibrate_element`.
- Octave - The quantum machine doing the calibrations will be closed after the calibration is done.

## [1.0.0] - 2022-09-04
- Removed deprecated entries from the configuration schema
- Removed dependency in `qua` package
### Fixed
- QuantumMachineManager - Fixed a bug where you could not connect using SSL on python version 3.10+
- Serializer - Fixed `declare_stream()` with `adc_true=True`
### Changed
- Update betterproto version.
- OctaveConfig: changed `set_device_info` name to `add_device_info`
- OctaveConfig: changed `add_opx_connections` name to `add_opx_octave_port_mapping`
- OctaveConfig: changed `get_opx_octave_connections` name to `get_opx_octave_port_mapping`
### Added
- API to control Octave - an up-conversion and down-conversion module with built-in Local Oscillator (LO) sources.
- Support Numpy as input - Support numpy scalars and arrays as valid input. Numpy object can now be used interchangeably with python scalars and lists. This applies to all statements imported with `from qm.qua import *`
- Serializer - Added support for legacy save

## [0.3.8] - 2022-07-10
### Fixed
- Serializer - Fixed a bug which caused binary expression to fail
### Changed
- QuantumMachineManager will try to connect to 80 before 9510 if the user did not specify a port.
- QuantumMachineManager will give an error if no host is given and config file does not contain one.
- QRun - Change qrun to strict_timing
- Input Stream - Fixed API for input stream
### Added
- Serializer - add strict_timing to serializer
- Logger - Can now add an environment variable to disable the output to stdout

## [0.3.7] - 2022-05-31
### Fixed
- Serializer - Fixed a bug which caused the serializer to fail when given completely arbitrary integration weights
- Serializer - Fixed a bug which caused the serializer to fail when given a list of correction matrices
- Serializer - Added support for "pass" inside blocks (if, for, etc). "pass" inside "else" is not supported.
### Added
- play - Add support for continue chirp feature
- High Resolution Time Tagging - Add support for high resolution time-tagging measure process
- Input Stream - Add support for streaming data from the computer to the program
- OPD - Added missing OPD timetagging function
### Changed
- set_dc_offset - 2nd input for function was renamed from `input_reference` to `element_input`
- QuantumMachineManager will try to connect to ports 9510 and 80 if the user did not specify a port.
- set_output_dc_offset_by_element - can now accept a tuple of ports and offsets
- `signalPolarity` in the timetagging parameters (`outputPulseParameters` in configuration) now accept `Above` and `Below` instead of `Rising` and `Falling`, which better represent it's meaning.

## [0.3.6] - 2022-01-23
### Added
- `signalPolarity` in the timetagging parameters (`outputPulseParameters` in configuration) now accept also `Rising` and `Falling`, which better represent it's meaning.
- `derivativePolarity` in the timetagging parameters (`outputPulseParameters` in configuration) now accept also `Above` and `Below`, which better represent it's meaning.
- Add unsafe switch to `generate_qua_config` function.
- Add library functions and `amp()` in measure statement to `generate_qua_config` function.
### Changed
- Better error for library functions as save source

## [0.3.5] - 2021-12-27
### Added
- Raises an error when using Python logical operators
- Add elif statement to `generate_qua_config` function

### Changed
- Fix indentation problem on the end of for_each block in `generate_qua_config` function
- The `generate_qua_config` now compresses lists to make the resulting file smaller and more readable

## [0.3.4] - 2021-12-05
### Added
- Define multiple elements with shared oscillator.
- Define an analog port with channel weights.
- Add measure and play features to `generate_qua_config` function
- format `generate_qua_config` function output
- improve `wait_for_all_values` execution time

## [0.3.3] - 2021-10-24
### Added
- Define an analog port with delay.
- New `set_dc_offset()` statement that can change the DC offset of element input in real time.
- New input stream capabilities facilitating data transfer from job to QUA.
- New flag for stream processing fft operator to control output type.
- Add information about demod on a tuple.
- Added best practice guide.
### Changed
- Validate that element has one and only one of the available input type QMQUA-26

## [0.3.2] - 2021-10-03
### Added
- QuantumMachinesManager health check shows errors and warnings.
- Fetching job results indicates if there were execution errors.
- Define an element with multiple input ports.
- Stream processing demod now supports named argument `integrate`. If `False` is provided the demod will not sum the items, but only multiply by weights.
### Changed
- Documentation structure and content.

## [0.3.1] - 2021-09-13
### Fixed
- Fixed serialization of IO values.
- Support running `QuantumMachinesManager` inside ipython or jupyter notebook.
### Changed
- Removing deprecation notice from `with_timestamps` method on result streams.
- Setting `time_of_flight` or `smearing` are required if element has `outputs` and must not appear if it does not.

## [0.3.0] - 2021-09-03
### Changed
- Support for result fetching of both versions of QM Server.
- Now the SDK supports all version of QM server.

## [0.2.1] - 2021-09-01
### Changed
- Default port when creating new `QuantumMachineManager` is now `80` and user config file is ignored.

## [0.2.0] - 2021-08-31
### Added
- The original QM SDK for QOP 2.

## [0.1.0] - 2021-08-31
### Added
- The original QM SDK for QOP 1.
