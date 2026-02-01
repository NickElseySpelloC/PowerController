# Power Controller Overview
The Power Controller is a Python-based automation tool that schedules and controls a power load based on electricity pricing and user-configurable parameters. It integrates with the Amber API to fetch real-time electricity prices and optimizes the device operation to minimize costs while maintaining required run-time thresholds.

# Features
* Multiple output devices supported. 
* Extract of Tesla charging data and pricing of the same.
* Support for meter only outputs
* Dynamic Scheduling: Adjusts device operation based on real-time electricity prices.
* Normal scheduling: Turn devices on / off based on a time of day / day of week schedule, including support for dusk / dawn triggers. Schedule can be used for fall back if Amber pricing unavailable. 
* Simple web app to view the current state of each device and manually override if needed. 
* Configurable Parameters: Uses a YAML configuration file to set API credentials, run-time schedules, and file paths.
* Historical Tracking: Maintains past days of device runtime to optimize future scheduling.
* Automatic Configuration Handling: Creates a default configuration file if one does not exist.
* Optionally integrate with the [PowerControllerViewer app](https://github.com/NickElseySpelloC/PowerControllerViewer) so that yu can view light status, schedules and history via a web interface.
* Email notification for critical errors.
* Integration with the BetterStack uptime for heatbeat monitoring

# Installation & Setup
## Prerequisites
* Python 3.x installed:
macOS: `brew install python3`
* UV for Python installed:
macOS: 'brew install uvicorn'

The shell script used to run the app (*launch.sh*) is uses the *uv sync* command to ensure that all the prerequitie Python packages are installed in the virtual environment. When running in production, we recommend you do this via a systemd file (see 'Running the App via systemd' below.)

## Running on Mac
If you're running the Python script on macOS, you need to allow the calling application (Terminal, Visual Studio) to access devices on the local network: *System Settings > Privacy and Security > Local Network*

# Configuration File 
The script uses the *config.yaml* YAML file for configuration. An example of included with the project (*config.yaml.example*). Copy this to *config.yaml* before running the app for the first time.  Here's an example config file:

```yaml
# General settings for the Power Controller application
General:
  # A label for this installation - used in the email subject and web viewer app
  Label: MyPower
  # Number of seconds to sleep between each check of the run plan and possible changes to outputs. Recommended 30 seconds or more.
  PollingInterval: 120
  # Some critical errors can trigger email notifications - for example the AmberAPI not responding. This is the time in minutes for an issue to 
  # persist before we send an email notification. Leave blank to disable.
  ReportCriticalErrorsDelay: 30
  # Print some basic information to the console during startup and operation
  PrintToConsole: True
  # A default price to use if the Amber API is not available and there is no schedule price defined
  DefaultPrice: 32.0
  # Output consumption data file - leave blank to disable
  ConsumptionDataFile: output_consumption_data.csv
  ConsumptionDataMaxDays: 30    # Maximum number of days to keep in the consumption data file. Set to -1 to disable truncation.


# Settings for the built-in web server that provides a web interface to view and control the power controller
Website:
  HostingIP: 0.0.0.0          # The IP address to host the web server on. Use 0.0.0.0 to listen on all interfaces
  Port: 8080                  # The port to host the web server on
  PageAutoRefresh: 30         # How often to refresh the web page (in seconds). Set to 0 to disable auto-refresh.
  DebugMode: True             # Enable or disable debug mode for the web server (should be False in production)
  AccessKey: <Your website API key here>   # An access key to secure the web interface. Alternatively, set the WEBAPP_ACCESS_KEY environment variable. Leave blank to disable access control.


# Settings for the Amber API integration
AmberAPI:
  # Operating mode for the Amber API: Live (attempt to download prices), Offline (pretend Amber API is offline, use cached prices). Disabled (fall back to schedule)
  Mode: Live
  APIURL: https://api.amber.com.au/v1   # The base URL for the Amber API
  APIKey: <Your API key here>    # The API key for your account, get one at app.amber.com.au/developers. Alternatively, set the AMBER_API_KEY environment variable.
  Timeout: 15               # How long to wait in second for a response from the Amber API
  MaxConcurrentErrors: 4    # Send an email notification if we get this number of concurrent errors from Amber
  RefreshInterval: 15       # How often to refresh the pricing data from Amber (in minutes) 
  # Save usage data to a CSV file for offline use. Leave blank to disable
  UsageDataFile: amber_usage_data.csv
  UsageMaxDays: 30       # Maximum number of days to keep. Set to -1 to disable truncation.
  PricesCacheFile: latest_prices.json   # The name of the file to cache Amber pricing data


# Use this section to configure your Shelly devices used to control the lights. See this page for more information: https://nickelseyspelloc.github.io/sc_utility/guide/shelly_control/
ShellyDevices:
  AllowDebugLogging: False      # Set to True to enable debug logging for Shelly devices
  ResponseTimeout: 3            # How long to wait in seconds for a response from a Shelly device
  RetryCount: 1                 # Number of times to retry a request to a Shelly device if it fails
  RetryDelay: 2                 # Number of seconds to wait between retries
  MaxConcurrentErrors: 4        # Send an email notification if we get this number of concurrent errors
  PingAllowed: True             # Set to True if it's possible to ping your Shelly device to check if they are online (if they are on the same subnet as the controller)
  WebhooksEnabled: True         # Enable or disable the webhook listener
  WebhookHost: 0.0.0.0          # IP to listen for webhooks on. This should be the IP address of the machine running the app. Defaults to 0.0.0.0
  WebhookPort: 8787             # Port to listen for webhooks on. Defaults to 8787.
  WebhookPath: /shelly/webhook  # The URI path that webhooks will post to.
  Devices:                      # List of Shelly devices to control
    - Name: Shelly Pool 1        # A name for this device
      Model: Shelly2PMG3        # The model of Shelly device - see https://nickelseyspelloc.github.io/sc_utility/guide/shelly_models_list
      Hostname: 192.168.1.20   # The IP address or hostname of the Shelly device
      Simulate: False           # Set to True to simulate the device (for testing)
      DeviceAlertTemp: 75.0    # Temperature in Celsius that will trigger an alert email if the device exceeds this temperature
      Inputs:                   # List of inputs on the Shelly device to monitor
        - Name: "Filter Pump Override"
          Webhooks: True
        - Name: "Solar Pump Override"
          Webhooks: True
      Outputs:                  # List of outputs on the Shelly device to control your devices
        - Name: "Filter Pump Power"
        - Name: "Solar Pump Power"
      Meters:                  # List of meters on the Shelly device to monitor energy usage
        - Name: "Filter Pump Energy"
        - Name: "Solar Pump Energy"
    - Name: Shelly Pool 2
      Model: Shelly2PMG3        
      Hostname: 192.168.1.21   
      Simulate: False           
      Inputs:                   
        - Name: "Shelly Pool 2 I1"
        - Name: "Shelly Pool 2 I2"
      Outputs:                  
        - Name: "Solar Valve Actuator"
        - Name: "Shelly Pool 2 O2"
      Meters:                  
        - Name: "Shelly Pool 2 M1"
        - Name: "Shelly Pool 2 M2"
      TempProbes: 
        - Name: "Temp Pool Water"
          RequiresOutput: "Filter Pump Power"  # Only read this probe when the specified output is ON
        - Name: "Temp Solar Return"
          RequiresOutput: "Solar Pump Power"  # Only read this probe when the specified output is ON
        - Name: "Temp Roof"
    - Name: Spello Hot Water
      Model: Shelly2PMG3
      Hostname: 192.168.86.39
      ExpectOffline: True       # Expect that this device will sometimes be offline and so don't report warnings when it happens
      Outputs:
        - Name: "Hot Water O1"
        - Name: "Hot Water O2"
      Meters:
        - Name: "Hot Water M1"
        - Name: "Hot Water M2"
    - Name: Panel EM1
      Model: ShellyEMG3
      Hostname: 192.168.86.44
      ExpectOffline: True
      Meters:
        - Name: "Panel EM1.1"
        - Name: "Panel EM1.2"   

# Define the operating schedules for your devices. These are used to determine when a device is allowed to run when not using the Amber pricing data.
OperatingSchedules:
  - Name: Pool Pump           # A name for this schedule - used in the Outputs section
    Windows:                  # List of time windows when the schedule is active
      - StartTime: "00:00"
        EndTime: "07:30"
        DaysOfWeek: All       # Days of the week this window applies to - Mon, Tue, Wed, Thu, Fri, Sat, Sun or All. Multiple days can be specified separated by commas
        Price: 20
      - StartTime: "07:30"
        EndTime: "09:00"
        DaysOfWeek: All
        Price: 16
      - StartTime: "09:00"
        EndTime: "15:00"
        DaysOfWeek: All
        Price: 13
      - StartTime: "15:00"
        EndTime: "17:00"
        DaysOfWeek: All
        Price: 33
      - StartTime: "17:00"
        EndTime: "21:00"
        DaysOfWeek: All
        Price: 51
      - StartTime: "21:00"
        EndTime: "23:59"
        DaysOfWeek: All
        Price: 22
  - Name: Pool Heating
    Windows: 
      - StartTime: "10:00"
        EndTime: "16:00"
        DaysOfWeek: All
      - StartTime: "22:00"
        EndTime: "23:59"
        DaysOfWeek: All
  - Name: Hot Water
    Windows: 
      - StartTime: "00:00"
        EndTime: "14:00"
        DaysOfWeek: All
        Price: 18
      - StartTime: "22:00"
        EndTime: "23:59"
        DaysOfWeek: All
        Price: 20


# Configure each switched output that controls your devices and how they behave
Outputs:  
  - Name: Pool Pump                 # A name for this output - used in the web interface  
    Type: shelly                    # The type of output - shelly (default), teslamate or meter
    DeviceOutput: Filter Pump Power  # The Shelly device output that controls this device - must match a Name in the ShellyDevices: Devices: Outputs section
    Mode: BestPrice                 # Operating mode: BestPrice (run for target hours at best price), Schedule (run according to schedule only)
    Schedule: Pool Pump             # The operating schedule to use when in Schedule mode - must match a Name in the OperatingSchedules section
    ConstraintSchedule: Pool Heating  # An optional constraint schedule that limits when the output can run, even in BestPrice mode
    AmberChannel: general           # The Amber pricing channel to use for this device, typically general or controlledLoad
    DaysOfHistory: 7                # How many days of history to keep for this device
    MinHours: 2                     # Minimum number of hours to run each day
    MaxHours: 10                    # Maximum number of hours to run each day
    TargetHours: 7                  # Target number of hours to run each day. Set to -1 to run for all hours that fall within best price or the schedule
    MonthlyTargetHours:             # Override the TargetHours for a specific month of the year 
      January: 8
      February: 8
      June: 6
      July: 6
      August: 6
      December: 8     
    MaxShortfallHours: 4            # Maximum number of shortfall hours we can carry forward from previous days. Ignored if TargetHours is -1. Set to 0 to disable.
    MaxBestPrice: 23.0              # The maximum price to run at when in BestPrice mode. 
    MaxPriorityPrice: 35.0          # The maximum price to run when we haven't run for the minimum number of hours yet.
    DatesOff:                       # Optional list of date ranges when the output should not run
      - StartDate: 2024-07-01
        EndDate: 2024-09-30
    DeviceMeter: Filter Pump Energy  # The Shelly device meter to use to track energy usage - must match a Name in the ShellyDevices: Devices: Meters section
    MaxDailyEnergyUse: 6000         # Maximum energy use expected in Wh per day. An email warning will be sent if this is exceeded.
    DeviceInput: Filter Pump Override   # Optional: The Shelly device input to used override the state of the output - must match a Name in the ShellyDevices: Devices: Inputs section
    DeviceInputMode: TurnOn         # If a DeviceInput is specified, this controls how is is used. Ignore: Ignore the state of the inputs. TurnOn: Turn output on if input is off. TurnOff: Turn output off if input is on.
    StopOnExit: True                # If True, attempt to turn off the outputs when the application exits
    MinOnTime: 30                   # Minimum minutes to stay on once turned on
    MinOffTime: 10                  # Minimum minutes to stay off (prevent rapid cycling). Cannot be set if MaxffTime is set.
    MaxOffTime:                     # Maximum minutes to stay off. Cannot be set if MinOffTime is set.
  - Name: Solar Heating
    Type: shelly
    DeviceOutput: Solar Pump Power
    Mode: Schedule
    Schedule: Pool Heating
    AmberChannel: general
    TargetHours: -1
    MaxBestPrice: 23.0
    MaxPriorityPrice: 35.0
    DeviceMeter: Solar Pump Energy
    ParentOutput: Pool Pump               # Optional: The name of a parent output that must be ON for this output to run
    TurnOnSequence: Turn On Solar Pump    # Optional: Name of the output sequence to run when turning on this output
    TurnOffSequence: Turn Off Solar Pump  # Optional: Name of the output sequence to run when turning off this output
    MaxAppOnTime: 60               # If we turned this output on via the app, revert to auto after this number of minutes. Set to 0 to disable.
    MaxAppOffTime: 60              # If we turned this output off via the app, revert to auto after this number of minutes. Set to 0 to disable.
    TempProbeConstraints:       # Optional list of temperature probe constraints that must be met for the output to run
      - TempProbe: Temp Roof
        Condition: GreaterThan
        Temperature: 32.0
      - TempProbe: Temp Pool Water
        Condition: LessThan
        Temperature: 30.0    
  - Name: Hot Water Heater
    Type: shelly
    DeviceOutput: Hot Water O1
    Mode: BestPrice
    Schedule: Hot Water
    AmberChannel: controlledLoad
    TargetHours: -1
    MaxBestPrice: 23.0
    MaxPriorityPrice: 30.0
    DeviceMeter: Hot Water M1
    HideFromWebApp: True      # If True, this output will not be shown in the built-in web app
    HideFromViewerApp: True  # If True, this output will not be shown in the PowerControllerViewer app
  - Name: Tesla
    Type: teslamate
    CarID: 1                   # The ID of the car in TeslaMate to control (this is usually 1 if you only have one car)
    DaysOfHistory: 14            # How many days of history to keep for this device in the system state file
    AmberChannel: general       # The Amber pricing channel to use for pricing this device, typically general or controlledLoad
    Schedule: General           # The operating schedule to use for pricing this device when not using Amber pricing - must match a Name in the OperatingSchedules section
  - Name: "EM1.1 Living & Beds"
    Type: meter
    DeviceMeter: Panel EM1.1
    Mode: BestPrice
    Schedule: General
    PowerOnThresholdWatts: 40
    PowerOffThresholdWatts: 10
    MinEnergyToLog: 20
    HideFromWebApp: False
    HideFromViewerApp: True
  - Name: "EM1.2 Kitchen & Laundry"
    Type: meter
    DeviceMeter: Panel EM1.2
    Mode: BestPrice
    Schedule: General
    PowerOnThresholdWatts: 40
    PowerOffThresholdWatts: 10
    MinEnergyToLog: 20
    HideFromWebApp: False
    HideFromViewerApp: True

# Use this to define a sequence of actions to perform on outputs when turning On or off
OutputSequences:
  - Name: "Turn On Solar Pump"
    Description: "Turn on the actuator valve, wait for 1 minute then turn on the solar booster pump"
    Timeout: 90
    Steps:
      - Type: CHANGE_OUTPUT
        OutputIdentity: "Solar Valve Actuator"
        State: True
        Retries: 2
        RetryBackoff: 1.0
      - Type: SLEEP
        Seconds: 60.0
      - Type: CHANGE_OUTPUT
        OutputIdentity: "Solar Pump Power"
        State: True
        Retries: 2
        RetryBackoff: 1.0
  - Name: "Turn Off Solar Pump"
    Description: "Turn off the solar booster pump, wait for 10 seconds then turn off the actuator valve"
    Timeout: 30
    Steps:
      - Type: CHANGE_OUTPUT
        OutputIdentity: "Solar Pump Power"
        State: False
        Retries: 2
        RetryBackoff: 1.0
      - Type: SLEEP
        Seconds: 10.0
      - Type: CHANGE_OUTPUT
        OutputIdentity: "Solar Valve Actuator"
        State: False
        Retries: 2
        RetryBackoff: 1.0

# Optionally use this section to enable logging of output energy consumption data to CSV and the system state file
OutputMetering:
  Enable: True    # Set to True to enable logging of output energy consumption data
  DataFile: logs/output_consumption_data.csv     # Record to CSV data file. Required
  DataFileMaxDays: -1  # Maximum number of days to keep in the CSV data file. Set to -1 for unlimited.
  OutputsToLog:   # A list of outputs to log. These must have a meter associated with them (Outputs: [Item]: DeviceMeter field)
    - Output: Pool Pump
      DisplayName: Pool
    - Output: Solar Heating
      DisplayName: Solar
      HideFromViewerApp: True   # If True, exclude this output from the viewer app's metering display page
    - Output: Hot Water Heater
      DisplayName: Hot Water
    - Output: Tesla
    - Output: "EM1.1 Living & Beds"
      DisplayName: "Living & Beds"
    - Output: "EM1.2 Kitchen & Laundry"
      DisplayName: "Kitchen & Laundry"

# Optionally enable temperature probe logging. The temperature probes must be defined in the Shelly device configuration above.
TempProbeLogging:
    Enable: True
    Probes:   # A list of temp probes to monitor.
      - Name: Temp Pool Water
        DisplayName: Pool Water
        Colour: Blue  # Colour to use when charting this probe
      - Name: Temp Roof
      - Name: Temp Solar Return
        HideFromViewerApp: True      # If True, probe will be logged in CSV file but hidden from the PowerControllerViewer app
    LoggingInterval: 30  # Log temp probe readings every N minutes
    LastReadingWithinMinutes: 180  # Only log readings that have been updated within this number of minutes. 0 to disable.
    SavedStateFileMaxDays: 7  # Number of days to keep in the data in the system state file. Try to keep this as low as possible to reduce file size. 0 to disable.
    HistoryDataFile: temp_probe_history.csv  # Leave blank to disable logging to a CSV file.
    HistoryDataFileMaxDays: 90  # Maximum number of days to keep in the history data file.  0 to disable.
    Charting:   # This contains settings for generating temperature charts for the web viewer app (future) and the PowerControllerViewer website.
      Enable: True
      Charts:
        - Name: "Pool Temps"
          Probes:
            - Temp Pool Water
            - Temp Solar Return
          DaysToShow: 30
        - Name: "Roof Temp"
          Probes:
            - Temp Roof
          DaysToShow: 30

# Optionally use this section to specify the geographic location and timezone of your installation. This is used to determine the dawn and dusk times for scheduled events.
# You can do this in one of three ways:
# 1. Use a Shelly device's location (using IP lookup)- just specify the device name in the UseShellyDevice field
# 2. Use a Google Maps URL to extract the location - specify the GoogleMapsURL field and the Timezone field.
# 3. Manually specify the latitude and longitude - specify the Timezone, Latitude and Longitude fields.
Location:
  # UseShellyDevice: "Shelly Pool 1"
  Timezone: Europe/London     # See https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
  GoogleMapsURL:              # A Google Maps URL containing the latitude and longitude of your location, e.g. https://www.google.com/maps/place/London,+UK/@51.5012694,-0.1425182,18.41z
  Latitude:                   # The latitude of your location, e.g. - 51.50185169072752
  Longitude:                  # The longitude of your location. e.g. -0.1406533148232459


# Settings for various log and state files
Files:
  SavedStateFile: system_state.json    # The name of the saved state file. This is used to store the state of the device between runs.
  LogfileName: logfile.log             # The name of the log file
  LogfileMaxLines: 10000               # The maximum number of lines to keep in the log file
  LogfileVerbosity: debug              # How much information do we write to the log file. One of: none; error; warning; summary; detailed; debug; all
  ConsoleVerbosity: detailed           # How much information do we write to the console. One of: error; warning; summary; detailed; debug; all
  

# Enter your settings here if you want to be emailed when there's a critical error 
Email:
  EnableEmail: True                         # Set to True to enable email notifications 
  SendEmailsTo: <Your email address here>   # The email address to send notifications to
  SMTPServer: <Your SMTP server here>       # The SMTP server to use to send the email
  SMTPPort: 587                             # The SMTP server port
  SMTPUsername: <Your SMTP username here>   # The SMTP username. Alternatively, set the SMTP_USERNAME environment variable.
  SMTPPassword: <Your SMTP password here>   # The SMTP password or app password. Alternatively, set the SMTP_PASSWORD environment variable.
  SubjectPrefix: "[My PowerController]: "   # A prefix to add to the email subject line


# Use this section to configure integration with the PowerControllerViewer app - see https://github.com/NickElseySpelloC/PowerControllerViewer
ViewerWebsite:
  Enable: False                   # Set to True to enable integration with the PowerControllerViewer app
  BaseURL: http://localhost:8000  # The base URL of the PowerControllerViewer app
  AccessKey: <Your website API key here>  # The access key for the PowerControllerViewer app. Alternatively, set the VIEWER_ACCESS_KEY environment variable.
  APITimeout: 5                   # How long to wait in seconds for a response from the PowerControllerViewer app
  Frequency: 10                   # How often to post the state to the web viewer app (in seconds)


# Use this section to configure integration with the BetterStack Heartbeat monitoring service - see https://betterstack.com/heartbeat/
HeartbeatMonitor:
  Enable: False              # Set to True to enable integration with the Heartbeat monitoring service
  WebsiteURL: https://uptime.betterstack.com/api/v1/heartbeat/myheartbeatid    # The URL of the website to monitor for availability
  HeartbeatTimeout: 5        # How long to wait for a response from the website before considering it down in seconds
  Frequency: 10              # How often to post the state to the heartbeat monitor (in seconds)

# Optionally use this sectionto configure integration with the TeslaMate database to import Tesla charging session data
TeslaMate:
  Enable: False           # Set to True to enable integration with the TeslaMate database
  RefreshInterval: 10     # How often to refresh the TeslaMate data (in minutes)
  Host: 127.0.0.1         # The host address of the TeslaMate database (or use the TESLAMATE_DB_HOST environment variable)
  Port: 5432              # The port number of the TeslaMate database (or use the TESLAMATE_DB_PORT environment variable)
  DatabaseName: teslamate # The name of the TeslaMate database (or use the TESLAMATE_DB_NAME environment variable)
  DBUsername: teslamate   # The username to connect to the TeslaMate database (or use the TESLAMATE_DB_USER environment variable)
  DBPassword: <Your password here>  # The password to connect to the TeslaMate database (or use the TESLAMATE_DB_PASSWORD environment variable)
  GeofenceName: Home     # Optionally, only query the charging data within this geofence name. Leave blank to disable.
  SaveRawData: False    # Save the raw imported TeslaMate data the system state file for debugging. Set to False (the default) to reduce file size.

```
## Configuration Parameters
### Section: General

General settings for the Power Controller application.

| Parameter | Description | 
|:--|:--|
| Label | The label (name) that your installation. Used in the email subject and web viewer app |
| PollingInterval | Number of seconds to sleep between each check of the run plan and possible changes to outputs. Recommended 30 seconds or more. |
| ReportCriticalErrorsDelay | Some critical errors can trigger email notifications - for example the AmberAPI not responding. This is the time in minutes for an issue to persist before we send an email notification. Leave blank to disable. |
| PrintToConsole | Print some basic information to the console during startup and operation |
| DefaultPrice | A default price to use if the Amber API is not available and there is no schedule price defined |


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

