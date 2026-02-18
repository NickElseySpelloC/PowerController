# Configuration file - OutputSequences section

Define the sequence of events that must happen to turn an Output On or Off. In our example config file, turning on our pool solar heating booster pump requires that we first turn on an actuator valve, wait for a minute and then turn on the solar booster pump. 

Note: The section is optionaly, but if you use it, the required keys below are shown in **bold**.

| Key | Description | 
|:--|:--|
| **Name** | A name for this sequence.  |
| Description | A description for this sequence. |
| Timeout | How long to wait for all the steps in the sequence to complete. |
| **Steps** | A list of steps for this sequence - see below. |

Each step entry in the sequence can include the following parameters:

| Key | Description |
|:--|:--|
| **Type** | What type of step is this. One of:<br>**CHANGE_OUTPUT** - Change an output to On or Off.<br>**SLEEP** - Sleep for X seconds before the next step.<br>**GET_LOCATION** - Get the geo-location data from the specified Shelly device. <br>**REFRESH_STATUS** - Refresh the status of all Shelly devices. |
| OutputIdentity | If the step type is **CHANGE_OUTPUT**, set the name of the output here. This must be an output named in the ShellyDevices: Devices: [Device]: Outputs section. |
| DeviceIdentity | If the step type is Define a sequence of actions to perform on outputs when turning On or off, set the name of the Shelly device here. This must be a device named in the ShellyDevices: Devices section. |
| Seconds | If the step type is Define a sequence of actions to perform on outputs when turning On or off, use this to specify the sleep time. |
| State | If the step type is Define a sequence of actions to perform on outputs when turning On or off, set this to True to turn the output on, False to turn it off. |
| Retries | How many retry attempts to make on this step before giving up. |
| RetryBackoff  | How many seconds to wait between retry attempts. |
