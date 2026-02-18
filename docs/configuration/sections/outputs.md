# Configuration file - Outputs section

This is wehre the action happens. This section configures your switched outputs and energy meters and controls how they behave. You must define at least one Output for the app to work.

There are three fundametal types of Output device.

1. **shelly**: This the default - a specific output relay of a Shelly Smart switch. shelly type of outputs are used to switch electrical devices on and off.
2. **meter**: A Shelly energy meter. This is used to  monitor and log energy usage for a electrical circuit. 
3. **teslamate**: A special type of energy meter that imports Tesla vehicle charging data from using TeslaMate. Requires the [TeslaMate](teslamate.md) section to be properly configured.

The Output device type is set via the Mode key. 

There's a lot of keys in this section, but not all are applicable to all types:

| Setting | shelly | meter | teslamate |
|:--|:--|:--|:--|
| Name | ✓ | ✓ | ✓ |
| Type | ✓ | ✓ | ✓ |
| DeviceOutput | ✓ | ✓ |  |
| Mode | ✓ | ✓ | ✓ |
| Schedule | ✓ | ✓ | ✓ |
| ConstraintSchedule | ✓ |   |   |
| AmberChannel | ✓ | ✓ | ✓ |
| CarID |   |   | ✓ |
| DaysOfHistory | ✓ | ✓ | ✓ |
| MinHours | ✓ |   |   |
| MaxHours | ✓ |   |   |
| TargetHours | ✓ |   |   |
| MonthlyTargetHours | ✓ |   |   |
| MaxShortfallHours | ✓ |   |   |
| MaxBestPrice | ✓ |   |   |
| MaxPriorityPrice | ✓ |   |   |
| DatesOff | ✓ |   |   |
| DeviceMeter | ✓ | ✓ |   |
| MaxDailyEnergyUse | ✓ | ✓ |   |
| DeviceInput | ✓ |   |   |
| DeviceInputMode | ✓ |   |   |
| StopOnExit | ✓ |   |   |
| MinOnTime | ✓ |   |   |
| MinOffTime | ✓ |   |   |
| ParentOutput | ✓ |   |   |
| TurnOnSequence | ✓ |   |   |
| TurnOffSequence  ✓ |   |   |
| MaxAppOnTime | ✓ |   |   |
| MaxAppOffTime | ✓ |   |   |
| UPSIntegration | ✓ |   |   |
| PowerOnThresholdWatts |  | ✓  |   |
| PowerOffThresholdWatts |  | ✓  |   |
| MinEnergyToLog |  | ✓  |   |
| HideFromWebApp | ✓ | ✓ | ✓ |
| HideFromViewerApp | ✓ | ✓ | ✓ |
| TempProbeConstraints | ✓ |   |   |

The complete list of keys applicable in this section are as follows:

Note: Required keys are shown in **bold**.

| Key | Description | 
|:--|:--|
| **Name** | A name for this output - used in the web interface. |
| Type | Configures what type of output this is as decribed above:<br>**shelly**: A fully functional Shelly smart switch output. <br>**meter**: A Shelly energy meter. <br>**teslamate**: Imports Tesla charging data from using TeslaMate.  |
| DeviceOutput | Specify the Shelly device output that controls this device - must match a Name in the ShellyDevices: Devices: Outputs section. |
| Mode | Operating mode:<br>**BestPrice**: Run for target hours at best price<br>**Schedule**: Run according to schedule only. |
| Schedule | The operating schedule to use when in Schedule mode - must match a Name in the OperatingSchedules section. |
| ConstraintSchedule | An constraint schedule that limits when the output can run, even in BestPrice mode. |
| AmberChannel | The Amber pricing channel to use for this device, typically either **general** or **controlledLoad**. |
| CarID | The numeric ID of the Tesla you want to import data for. Leave blank to get data for all vehicles. You can get the CarID from the URL parameter car_id= in the TeslaMate "charges" dashboard. |
| DaysOfHistory | How many days of history to keep for this device |
| MinHours | Minimum number of hours to run each day |
| MaxHours | Maximum number of hours to run each day |
| TargetHours | Target number of hours to run each day. Set to -1 to run for all hours comply with the price and/or schedule constaints. |
| MonthlyTargetHours | Override the TargetHours for a specific month of the year |
| MaxShortfallHours | Maximum number of shortfall hours we can carry forward from previous days. |
| MaxBestPrice | The maximum price to run at when in BestPrice mode. |
| MaxPriorityPrice | The maximum price to run when we haven't run for the minimum number of hours (MinHours) yet. |
| DatesOff | Optional list of date ranges when the output should not run. A list of StartDate and EndDate pairs. Dates are in the format yyyy-mm-dd |
| DeviceMeter | The Shelly device meter to use to track energy usage - must match a Name in the ShellyDevices: Devices: Meters section |
| MaxDailyEnergyUse | Maximum energy use expected in Wh per day. An email warning will be sent if this is exceeded. |
| DeviceInput | The Shelly device input to used override the state of the output - must match a Name in the ShellyDevices: Devices: Inputs section |
| DeviceInputMode | If a DeviceInput is specified, this controls how is is used. <br>**Ignore**: Ignore the state of the inputs.<br>**TurnOn**: Turn output on if input is off. <br>**TurnOff**: Turn output off if input is on. |
| StopOnExit | If True, attempt to turn off the outputs when the application exits |
| MinOnTime | Minimum minutes to stay on once turned on. |
| MinOffTime | Minimum minutes to stay off (prevent rapid cycling). Cannot be set if MaxffTime is set. |
| MaxOffTime | Maximum minutes to stay off. Cannot be set if MinffTime is set. Recommend using this in conjunction with MinOnTime, otherwise if the run plan requires the output to be off, it turn off again immediatly after turning on due to this trigger. |
| ParentOutput | This output is slaved to the designated parent output. In addition to the other criteria defined for this output, it'll only run when the parent is running. | 
| TurnOnSequence | Name of the output sequence to run when turning on this output. The sequence name must be defined in the [OutputSequences](output_sequences.md) section |
| TurnOffSequence | Name of the output sequence to run when turning off this output. |
| MaxAppOnTime | If we turned this output on via the app, revert to auto after this number of minutes.  |
| MaxAppOffTime | If we turned this output off via the app, revert to auto after this number of minutes.  |
| UPSIntegration | This section must contain two entries:<br>**UPS**: The name of the UPS, as defined in the UPSINtegrations section (see below).<br> **ActionIfUnhealthy**: One of: _TurnOn_ or _TurnOff_. |
| PowerOnThresholdWatts | Only applies to meter style outouts. The minimum power draw before we start recording energy use (output is considered "On"). |
| PowerOffThresholdWatts | Only applies to meter style outouts. The maximum power draw before this output will be considered "Off". |
| MinEnergyToLog | If a device run is logged with less than this number of Watts, the entry will be discarded. |
| HideFromWebApp | If True, this output will not be shown in the built-in web app. |
| HideFromViewerApp | If True, this output will not be shown in the PowerControllerViewer app. |
| TempProbeConstraints | List of temperature probe constraints that must be met for the output to run. Each entry must include:<br>**TempProbe**: The name of the temperature probe that constrains this output. Must be defined in the ShellyDevices: Devices: TempProbes section.<br>**Condition**: Either _GreaterThan_ or _LessThan_<br>**Temperature**: The threshold temperature on degress C. |

Take a look at the [example configuration file](../example_config.md) for some real world examples.
