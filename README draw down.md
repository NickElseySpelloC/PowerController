### Section: General


### Section: Website

Settings for the built-in web server that provides a web interface to view and control the power controller.

| Parameter | Description | 
|:--|:--|
| HostingIP | The IP address to host the web server on. Use 0.0.0.0 to listen on all interfaces |
| Port | The port to host the web server on |
| PageAutoRefresh |  How often to refresh the web page (in seconds). Set to 0 to disable auto-refresh. |
| DebugMode | Enable or disable debug mode for the web server (should be False in production) |
| AccessKey | An access key to secure the web interface. Alternatively, set the WEBAPP_ACCESS_KEY environment variable. Leave blank to disable access control. |

### Section: AmberAPI

| Parameter | Description | 
|:--|:--|
| Mode | Operating mode for the Amber API: Live (attempt to download prices), Offline (pretend Amber API is offline, use cached prices). Disabled (fall back to schedule) | 
| APIURL | Base URL for API requests. This the servers URL on the Amber developer's page, currently: https://api.amber.com.au/v1 |
| APIKey | Your Amber API key for authentication. Alternatively, set the AMBER_API_KEY environment variable. Login to  app.amber.com.au/developers/ and generate a new Token to get your API key.| 
| Timeout | Number of seconds to wait for Amber to respond to an API call | 
| MaxConcurrentErrors | Send an email notification if we get this number of concurrent errors from Amber. |
| RefreshInterval | How often to refresh the pricing data from Amber (in minutes). |
| UsageDataFile | Set to the name of a CSV file to log hourly energy usage and costs as reported by Amber. |
| UsageMaxDays | Maximum number of days to keep in the usage data file. |
| PricesCacheFile | The name of the file to cache Amber pricing data. | 

### Section: ShellyDevices

In this section you can configure one or more Shelly Smart switches, one of which will be used to contro your pool pump or water heater and optionally monitor its energy usage. See the [Shelly Getting Started guide](https://nickelseyspelloc.github.io/sc_utility/guide/shelly_control/) for details on how to configure this section.

### Section: OperatingSchedules

Define the operating schedules for your devices. These are used to determine when a device is allowed to run when not using the Amber pricing data.

| Parameter | Description | 
|:--|:--|
| Name | A name for this schedule - used in the Outputs section | 
| Windows | A list of one or more StartTime / StopTime events for this schedule. Each window can have the following elements.... | 

| Window Paramater | Description | 
|:--|:--|
| StartTime | The start time in miliary format, for example "13:30". Must be enclosed in double quotes |
| EndTime | The start time in miliary format, for example "17:30". Must be enclosed in double quotes |
| DaysOfWeek | Days of the week this window applies to - Mon, Tue, Wed, Thu, Fri, Sat, Sun or All. Multiple days can be specified separated by commas. |
| Price | The average eletricity price in c/kWh for energy during this window. Used to forecast costs when running on a schedule rather than Amber prices |

### Section: Outputs

Configure each switched output that controls your devices and how they behave. This setion is a list of one or more Outputs, each one supporting the following parameters:

| Parameter | Description | 
|:--|:--|
| Name | A name for this output - used in the web interface. |
| Type | Configures what type of output this is:<br>shelly: The default. A fully functional Shelly relay output with associated metering, input controls, etc. <br>meter: A Shelly only meter. Useful if you want to monitor and log energy usage from a Shelly energy meter.<br>teslamate: A special "output" this imports Tesla charging data from using TeslaMate. Requires the TeslaMate: section to be properly configured (see below.)  |
| DeviceOutput | The Shelly device output that controls this device - must match a Name in the ShellyDevices: Devices: Outputs section |
| Mode | Operating mode: BestPrice (run for target hours at best price), Schedule (run according to schedule only) |
| Schedule | The operating schedule to use when in Schedule mode - must match a Name in the OperatingSchedules section |
| ConstraintSchedule | An optional constraint schedule that limits when the output can run, even in BestPrice mode. |
| AmberChannel | The Amber pricing channel to use for this device, typically general or controlledLoad |
| CarID | The numeric ID of the Tesla you want to import data for. Leave blank to get data for all vehicles. You can get the CarID from the URL parameter car_id= in the TeslaMate "charges" dashboard |
| DaysOfHistory | How many days of history to keep for this device |
| MinHours | Minimum number of hours to run each day |
| MaxHours | Maximum number of hours to run each day |
| TargetHours | Target number of hours to run each day. Set to -1 to run for all hours that fall within best price or the schedule |
| MonthlyTargetHours | Override the TargetHours for a specific month of the year |
| MaxShortfallHours | Maximum number of shortfall hours we can carry forward from previous days. Set to 0 to disable. |
| MaxBestPrice | The maximum price to run at when in BestPrice mode.  |
| MaxPriorityPrice | The maximum price to run when we haven't run for the minimum number of hours yet. |
| DatesOff | Optional list of date ranges when the output should not run. A list of StartDate and EndDate pairs. Dates are in the format yyyy-mm-dd |
| DeviceMeter | The Shelly device meter to use to track energy usage - must match a Name in the ShellyDevices: Devices: Meters section |
| MaxDailyEnergyUse | Maximum energy use expected in Wh per day. An email warning will be sent if this is exceeded. |
| DeviceInput | Optional: The Shelly device input to used override the state of the output - must match a Name in the ShellyDevices: Devices: Inputs section |
| DeviceInputMode | If a DeviceInput is specified, this controls how is is used. Ignore: Ignore the state of the inputs. TurnOn: Turn output on if input is off. TurnOff: Turn output off if input is on. |
| StopOnExit | If True, attempt to turn off the outputs when the application exits |
| MinOnTime | Minimum minutes to stay on once turned on |
| MinOffTime | Minimum minutes to stay off (prevent rapid cycling). Cannot be set if MaxffTime is set. |
| MaxOffTime | Maximum minutes to stay off. Cannot be set if MinffTime is set. Recommend using this in conjunction with MinOnTime, otherwise if the run plan requires the output to be off, it turn off again immediatly after turning on due to this trigger.  |
| ParentOutput | This output is slaved to the designated parent output. In addition to the other criteria defined for this output, it'll only run when the parent is running. | 
| TurnOnSequence | Name of the output sequence to run when turning on this output. The sequence name must be defined in the OutputSequences section (see below.) |
| TurnOffSequence | Name of the output sequence to run when turning off this output |
| MaxAppOnTime | If we turned this output on via the app, revert to auto after this number of minutes. Set to 0 to disable. |
| MaxAppOffTime | If we turned this output off via the app, revert to auto after this number of minutes. Set to 0 to disable. |
| UPSIntegration | This section must contain two entries:<br>**UPS**: The name of the UPS, as defined in the UPSINtegrations section (see below).<br> **ActionIfUnhealthy**: One of: TurnOn or TurnOff |
| PowerOnThresholdWatts | Only applies to meter style outouts. The minimum power draw before this output will be considered "On" |
| PowerOffThresholdWatts | Only applies to meter style outouts. The maximum power draw before this output will be considered "Off" |
| MinEnergyToLog | Only applies to meter style outouts.  If a device run is logged with less than this number of Watts, the entry will be discarded |
| HideFromWebApp | If True, this output will not be shown in the built-in web app |
| HideFromViewerApp | If True, this output will not be shown in the PowerControllerViewer app |
| TempProbeConstraints | Optional list of temperature probe constraints that must be met for the output to run. Each entry must include:<br>**TempProbe**: The name of the temperature probe that constrains this output. Must be defined in the ShellyDevices: Devices: [Device]: TempProbes section.<br>**Condition**: Either _GreaterThan_ or _LessThan_<br>**Temperature**: The threshold temperature on degress C. |

Some of the Output settings are only applicable to some fo the output Types:

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

### Section: OutputSequences

Optionally use this section to define the sequence of events that must happen to turn an Output On or Off. In our example config file, turning on our pool solar heating booster pump requires that we first turn on an actuator valve, wait for a minute and then turn on the solar booster pump. 

| Parameter | Description | 
|:--|:--|
| Name | A name for this sequence.  |
| Description | A description for this sequence. |
| Timeout | How long to wait for all the steps in the sequence to complete. |
| Steps | A list of steps for this sequence - see below. |

Each step entry in the sequence can include the following parameters:

| Parameter | Description |
|:--|:--|
| Type | What type of step is this. One of:<br>**CHANGE_OUTPUT** - Change an output to On or Off.<br>**SLEEP** - Sleep for X seconds before the next step.<br>**GET_LOCATION** - Get the geo-location data from the specified Shelly device. <br>**REFRESH_STATUS** - Refresh the status of all Shelly devices. |
| OutputIdentity | If the step type is CHANGE_OUTPUT, set the name of the output here. This must be an output named in the ShellyDevices: Devices: [Device]: Outputs section. |
| DeviceIdentity | If the step type is GET_LOCATION, set the name of the Shelly device here. This must be a device named in the ShellyDevices: Devices section. |
| Seconds | If the step type is SLEEP, use this to specify the sleep time. |
| State | If the step type is CHANGE_OUTPUT, set this to True to turn the output on, False to turn it off. |
| Retries | How many retry attempts to make on this step before giving up. |
| RetryBackoff  | How many seconds to wait between retry attempts. |


### Section: UPSIntegration

Optionally defined one or more UPS units. In the context of the PowerController app a UPS is considered "healthy" or "unhealthy". An unhealthy UPS -
 - Is discharging and it's current battery charge and/or remaining runtime is below a set threshold (e.g. charge below 10%)
 - Is charging and it's current battery charge and/or remaining runtime is below a set threshold (e.g. charge below 90%)

Use this in conjunction with the UPSIntegration: entry in the Outputs section to dictate how an unhealthy UPS will override the state of the output.

| Parameter | Description | 
|:--|:--|
| Name | A name for this UPS. You will reference this name in the Outputs: UPSIntegration: UPS: entry.  |
| Script | The shell script to run to get this current state of the UPS. The script must return the information in JSON format to stdout.  |
| MinRuntimeWhenDischarging | Minimum runtime remaining in seconds to when UPS is discharging to consider the UPS as "healthy". |
| MinChargeWhenDischarging | Minimum charge remaining in percent when discharging to consider the UPS as "healthy". |
| MinRuntimeWhenCharging |  Minimum runtime remaining in seconds to when UPS is charging to consider the UPS as "healthy". |
| MinChargeWhenCharging | Minimum charge remaining in percent when charging to consider the UPS as "healthy". |

The UPS script should return a JSON object with the following format:
```json
{
    "timestamp": "2024-06-01T12:00:00Z",
    "battery_state": "charging",
    "battery_charge_percent": 85,
    "battery_runtime_seconds": 600
}
```

See the _shell_scripts/apc_ups_runtime.sh_ script as an example script for a retail APC UPS.

### Section: OutputMetering

Optionally use this section to enable logging of output energy consumption data to CSV and the system state file. You can list any output here that has a meter.

If the web viewer app is enabled (see ViewerWebsite section below), then usage summaries will be show for each output for the following reporting periods:
 - Prior 30 days (ending yesterday)
 - Prior 7 days (ending yesterday)
 - Yesterday
 - Today to date

| Parameter | Description | 
|:--|:--|
| Enable | Set to False to disable all output meter logging. |
| DataFile | The name / path of the CSV file to log to |
| DataFileMaxDays | Maximum number of days to keep in the CSV data file. Set to -1 for unlimited. |
| OutputsToLog | A list of outputs to include in the logs. Each entry can include:<br>**Output**: The name of the output. Must match a Outputs: [item]: Name entry.<br>**DisplayName**: Optionally use this alternative name in the CSV file and in the web view app.<br>**HideFromViewerApp**: If True, log this output int he CSV file but don't show it in the viewer app.   |


### Section: TempProbeLogging

Optionally use this section to log temperature probe readings to the system state JSON file and/or a CSV file. 

| Parameter | Description |
|:--|:--|
| Enable | Set to True or False |
| Probes | A list of temp probe names, as defined in the ShellyDevices: Devices: [Device]: TempProbes section. You can optionally add:<br: - A **DisplayName** here to be used in logging.<br>A **Colour** to use when charting this probe.<br>Set **HideFromViewerApp** to True to only log to the CSV file  |
| LoggingInterval | Log temp probe readings every N minutes |
| LastReadingWithinMinutes | Only log readings that have been updated within this number of minutes. 0 to disable. |
| SavedStateFileMaxDays | Number of days to keep in the data in the system state file. Try to keep this as low as possible to reduce file size. 0 to disable. |
| HistoryDataFile | Leave blank to disable logging to a CSV file. |
| HistoryDataFileMaxDays | Maximum number of days to keep in the history data file.  0 to disable. |
| Charting | Optionally use this section to configure how the PowerControllerViewer web app charts temperature reading history. | 


### Section: Location

Use this section to specify the geographic location and timezone of your installation. This is used to determine the dawn and dusk times for lighting control. You can do this in one of three ways:
1. Use a Shelly device's location (using IP lookup)- just specify the device name in the UseShellyDevice field
2. Use a Google Maps URL to extract the location - specify the GoogleMapsURL field and the Timezone field.
3. Manually specify the latitude and longitude - specify the Timezone, Latitude and Longitude fields.

### Section: Files

| Parameter | Description | 
|:--|:--|
| SavedStateFile | JSON file name to store the Power Controller's device current state and history. | 
| LogfileName | A text log file that records progress messages and warnings. | 
| LogfileMaxLines| Maximum number of lines to keep in the log file. If zero, file will never be truncated. | 
| LogfileVerbosity | The level of detail captured in the log file. One of: none; error; warning; summary; detailed; debug; all | 
| ConsoleVerbosity | Controls the amount of information written to the console. One of: error; warning; summary; detailed; debug; all. Errors are written to stderr all other messages are written to stdout | 

### Section: Email

| Parameter | Description | 
|:--|:--|
| EnableEmail | Set to *True* if you want to allow the PowerController to send emails. If True, the remaining settings in this section must be configured correctly. | 
| SMTPServer | The SMTP host name that supports TLS encryption. If using a Google account, set to smtp.gmail.com |
| SMTPPort | The port number to use to connect to the SMTP server. If using a Google account, set to 587 |
| SMTPUsername | Your username used to login to the SMTP server. Alternatively, set the SMTP_USERNAME environment variable. If using a Google account, set to your Google email address. |
| SMTPPassword | The password used to login to the SMTP server. Alternatively, set the SMTP_PASSWORD environment variable. If using a Google account, create an app password for the PowerController at https://myaccount.google.com/apppasswords  |
| SubjectPrefix | If set, the PowerController will add this text to the start of any email subject line for emails it sends. |

### Section: ViewerWebsite

Use this section to configure integration with the PowerControllerViewer app - see https://github.com/NickElseySpelloC/PowerControllerViewer

| Parameter | Description | 
|:--|:--|
| Enable | Set to True to enable integration with the PowerControllerViewer app | 
| BaseURL | The base URL of the PowerControllerViewer app | 
| AccessKey | The access key for the PowerControllerViewer app. Alternatively, set the VIEWER_ACCESS_KEY environment variable. | 
| APITimeout | How long to wait in seconds for a response from the PowerControllerViewer app | 
| Frequency | How often to post the state to the web viewer app (in seconds) | 


### Section: HeartbeatMonitor

| Parameter | Description | 
|:--|:--|
| Enable | Set to True to enable integration with the Heartbeat monitoring service | 
| WebsiteURL | Each time the app runs successfully, you can have it hit this URL to record a heartbeat. This is optional. If the app exist with a fatal error, it will append /fail to this URL. | 
| HeartbeatTimeout | How long to wait for a response from the website before considering it down in seconds. | 
| Frequency | How often to post the state to the heartbeat monitor (in seconds) | 

### Section: TeslaMate

This can be used to import Tesla charging data from a local network instance of [TeslaMate ](https://docs.teslamate.org/docs/installation/docker). This feature is a work in progress, for now it only logs charging data to the system state file. 

If you want to limit data imports to home charging, first set a geofence name in the TeslaMaste dashboard (Home > Dashboards > TeslaMate > Charges) and then set this geofence name in the GeofenceName config parameter.


# Setting up the Smart Switch
The Power Controller is currently designed to physically start or stop the pool device via one or more Shelly Smart switches. These are relays that can be connected to your local Wi-Fi network and controlled remotely via an API call. A detailed setup guide is beyond the scope of this document, but the brief steps are as follows:
* Purchase a Shelly Smart Switch. See the [Models Library](https://nickelseyspelloc.github.io/sc_utility/guide/shelly_models_list/) for a list of supported models and which of these have an energy meter built in.
* Install the switch so that the relay output controls power to your device. 
* Download the Shelly App from the app store (links on [this page](https://www.shelly.com/pages/shelly-app)) and get the switch setup via the app so that you can turn the relay on and off via Wi-Fi (not Bluetooth).
* Update the ShellyDevices section of your *config.yaml* file. 
* If possible, create a DHCP reservation for the Shelly device in your local router so that the IP doesn't change.

# Running the PowerController app 
You can manually run the app via the launch.sh script. We suggest you do this first to check that it's been properly configured. 

Once properly setup, we recommend creating a systemd file so that the app will run automatically including after a system restart. See 'Running the App via systemd' below. 

# Web Interface 
There's a companion web app that can be used to monitor the Power Controller status. This is a simple web page that shows the current state of the device and the last 7 days of history. It can support multiple instances of the Power Controller running on different devices. 

Please see https://github.com/NickElseySpelloC/PowerControllerViewer for more information on how to install and run the web app.

# Running the App via systemd

This section shows you how to configure the app to run automatically at boot on a RaspberryPi.

## 1. Create a service file

Create a new service file at _/etc/systemd/system/PowerController.service_. Edit the content below as appropriate
```
[Unit]
Description=PowerController app
After=network.target

[Service]
ExecStart=/home/pi/scripts/PowerController/launch.sh
WorkingDirectory=/home/pi/scripts/PowerController
StandardOutput=journal
StandardError=journal
User=pi
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/home/pi/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Logging and restart behavior
Restart=on-failure        # Only restart on non-zero exit code
RestartSec=10             # Wait 10 seconds before restarting

# Limit restart attempts (3 times in 60 seconds)
StartLimitIntervalSec=60
StartLimitBurst=3

[Install]
WantedBy=multi-user.target
```
Key options:

- **Restart=on-failure**: restart if the script exits with a non-zero code.
- **RestartSec=5**: wait 5 seconds before restarting.
- **StandardOutput=journal**: logs go to journalctl.


## 2. Enable and start the service

```bash
sudo systemctl daemon-reexec       # re-executes systemd in case of changes
sudo systemctl daemon-reload       # reload service files
sudo systemctl enable PowerController   # enable on boot
sudo systemctl start PowerController    # start now
```

## 3. View logs

```bash
journalctl -u PowerController -f
```

