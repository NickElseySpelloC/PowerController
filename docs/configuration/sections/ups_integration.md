# Configuration file - UPSIntegration section

Define one or more UPS units that can modify the behaviour of an Output. 

In the context of the PowerController app a UPS is considered "healthy" or "unhealthy". An unhealthy UPS -
 - Is discharging and it's current battery charge and/or remaining runtime is below a set threshold (e.g. charge below 10%)
 - Is charging and it's current battery charge and/or remaining runtime is below a set threshold (e.g. charge below 90%)

Use this in conjunction with the UPSIntegration: entry in the Outputs section to dictate how an unhealthy UPS will override the state of the output.

Note: The section is optionaly, but if you use it, the required keys below are shown in **bold**.

| Key | Description | 
|:--|:--|
| **Name** | A name for this UPS. You will reference this name in the Outputs: UPSIntegration: UPS: entry.  |
| **Script** | The shell script to run to get this current state of the UPS. The script must return the information in JSON format to stdout. Can include a realtive or absolute path.  |
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

Where:

- **battery_state** is one of "charging", "discharging" or "charged"
- **battery_charge_percent** is a number between 0 and 100
- **battery_runtime_seconds** is the remaining runtime in seconds.

_battery_charge_percent_ or _battery_runtime_seconds_ can be null, but not both. See the _shell_scripts/apc_ups_runtime.sh_ script as an example script for a retail APC UPS.