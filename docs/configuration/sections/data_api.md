# Data API

Enable a data API that can be used to get the current state of the system and recent history for integration with other applications or custom dashboards.

| Key | Description | 
|:--|:--|
| Enable | Set to False to disable the API server. If you do this when the app is alrewady running, the server will return a 503 error code (API data not available). If this is set to False at start up, the API server won't even start. |
| HostingIP | The IP to listen on. Set to 0.0.0.0 to listen on all interfaces. |
| Port | The port to listen on |
| RefreshInterval | The interval in seconds between internal refrehes of the API data cache. Set to 0 to refresh every polling interval. |
| AccessKey | Optionally you can set an access key that the client app must either pass as a URL argument:<br>_curl "http://localhost:8081/energyprices?access_key=abc123"_<br>...or in the request header:<br>_curl -H "Authorization: Bearer abc123" "http://localhost:8081/meters"_<br>This paraameter can also be set via the DATAAPI_ACCESS_KEY environment variable. |
| Outputs | A list of outputs to include in the /outputs end-point response. Each entry must define a **Name** that must match an [Outputs: Name:](outputs.md) entry and optionally a **DisplayName**. | 
| Meters  | A list of meters to include in the /meters end-point response. Each entry must define a **Name** that must match a [SCSmartDevices: Devices: Meters: Name:](devices.md) entry and optionally a **DisplayName**. | 
| TempProbes | A list of temperature to include in the /tempprobes end-point response. Each entry must define a **Name** that must match a [SCSmartDevices: Devices: TempProbes: Name:](devices.md) entry and optionally a **DisplayName**. | 
| TempProbeHistoryDays | The number of days of temperature probe history to include with each temp probe history. If this is set, then this probe must be configured in a HistoryDataFileMaxDays: Probes: Name entry and the days of temp probe logging history (HistoryDataFileMaxDays: HistoryDataFileMaxDays: ) must be greater than this parameter. |
| EnergyPrices | Configure the response for the /energyprices end-point, which returns the current and forecast Amber energy prices. If this section is anbled, you must have [Amber energy pricing enabled](amber_api.md). The following parameters are supported:<br>**AmberChannel**: The Amber pricing channel to report on, typically either **general** or **controlledLoad**. <br>**IntervalTime**: Interval for each forecast period in minutes (e.g. 30 for half-hourly prices, 60 for hourly prices)<br>**NumIntervals**: Number of intervals to return in the forecast (e.g. 48 for 24 hours of half-hourly prices, 24 for 24 hours of hourly prices)<br>**WarningPrice**: If the price exceeds this value, the API will include a warning in the response for this interval. Set to 0 to disable warnings.<br>**CriticalPrice** If the price exceeds this value, the API will include a critical warning in the response for this interval. Set to 0 to disable critical warnings. |

## API End Points

The Data API response to the following end-points

### /all

Return all the sections listed below.

### /outputs

Return output information, as configured in the _DataAPI: Outputs:_ parameter above. 

```json
{
    "Outputs": [
        {
            "Name": "Pool Pump",
            "DisplayName": "Pool",
            "Type": "smart device",
            "AppMode": "auto",
            "State": "ON",
            "NextChange": "2026-03-06T14:59:00+11:00",
            "NextChange__datatype": "datetime",
            "SystemState": "Automatic control based on schedule or best price",
            "Reason": "Run plan dictates that the output should be on",
            "LastChanged": "2026-03-06T10:05:14.619047+11:00",
            "LastChanged__datatype": "datetime",
            "OutputName": "Pool Pump Output",
            "DeviceMode": "BestPrice",
            "ScheduleName": "General",
            "AmberChannel": "general",
            "MinHours": 2,
            "MaxHours": 10,
            "TargetHours": 6,
            "PlannedHours": 4.9,
            "MaxBestPrice": 25.0,
            "MaxPriorityPrice": 30.0,
            "ActualHoursToday": 1.2284398791666666,
            "RunPlan": [
                {
                    "Date": "2026-03-06",
                    "Date__datatype": "date",
                    "StartDateTime": "2026-03-06T10:05:00+11:00",
                    "StartDateTime__datatype": "datetime",
                    "EndDateTime": "2026-03-06T14:59:00+11:00",
                    "EndDateTime__datatype": "datetime",
                    "Minutes": 294,
                    "Price": 16.14,
                    "ForecastEnergyUsage": 4889.304361034673,
                    "EstimatedCost": 0.7889866552532078,
                    "SlotCount": 59
                }
            ],
            "EnergyUsage": {
                "1hr": {
                    "Hours": 1,
                    "EnergyUsed": 1017.067198107691,
                    "TotalCost": 0.16674767951499742,
                    "AveragePrice": 16.394952056780575
                },
                "24hr": {
                    "Hours": 24,
                    "EnergyUsed": 6153.821788686064,
                    "TotalCost": 1.052588584471647,
                    "AveragePrice": 17.104632220693393
                }
            }
        },
        {
            "Name": "Solar Pump",
            "DisplayName": "Solar",
            "Type": "smart device",
            "AppMode": "auto",
            "State": "OFF",
            "NextChange": "2026-03-06T10:05:00+11:00",
            "NextChange__datatype": "datetime",
            "SystemState": "Automatic control based on schedule or best price",
            "Reason": "A temperature probe constraint requires the output to be off",
            "LastChanged": "2026-03-06T10:05:14.622337+11:00",
            "LastChanged__datatype": "datetime",
            "OutputName": "Solar Pump",
            "DeviceMode": "Schedule",
            "ScheduleName": "Pool Solar",
            "AmberChannel": "general",
            "MinHours": 2,
            "MaxHours": 6,
            "TargetHours": null,
            "PlannedHours": 5.916666666666667,
            "MaxBestPrice": 25.0,
            "MaxPriorityPrice": 30.0,
            "ActualHoursToday": 0.0,
            "RunPlan": [
                {
                    "Date": "2026-03-06",
                    "Date__datatype": "date",
                    "StartDateTime": "2026-03-06T10:05:00+11:00",
                    "StartDateTime__datatype": "datetime",
                    "EndDateTime": "2026-03-06T16:00:00+11:00",
                    "EndDateTime__datatype": "datetime",
                    "Minutes": 355,
                    "Price": 15.0,
                    "ForecastEnergyUsage": 3492.525301210315,
                    "EstimatedCost": 0.5238787951815472,
                    "SlotCount": 1
                }
            ],
            "EnergyUsage": {
                "1hr": {
                    "Hours": 1,
                    "EnergyUsed": 0.0,
                    "TotalCost": 0.0,
                    "AveragePrice": 0
                },
                "24hr": {
                    "Hours": 24,
                    "EnergyUsed": 1395.6509999999835,
                    "TotalCost": 0.20934764999999744,
                    "AveragePrice": 14.999999999999995
                }
            }
        },
        {
            "Name": "Network Rack",
            "DisplayName": "Network",
            "Type": "smart device",
            "AppMode": "auto",
            "State": "ON",
            "NextChange": "2026-03-07T00:00:00+11:00",
            "NextChange__datatype": "datetime",
            "SystemState": "Automatic control based on schedule or best price",
            "Reason": "Run plan dictates that the output should be on",
            "LastChanged": "2026-03-06T10:05:14.633633+11:00",
            "LastChanged__datatype": "datetime",
            "OutputName": "Network Rack O1",
            "DeviceMode": "BestPrice",
            "ScheduleName": "General",
            "AmberChannel": "general",
            "MinHours": -1,
            "MaxHours": -1,
            "TargetHours": null,
            "PlannedHours": 13.916666666666666,
            "MaxBestPrice": 60.0,
            "MaxPriorityPrice": 65.0,
            "ActualHoursToday": 10.235384890833332,
            "RunPlan": [
                {
                    "Date": "2026-03-06",
                    "Date__datatype": "date",
                    "StartDateTime": "2026-03-06T10:05:00+11:00",
                    "StartDateTime__datatype": "datetime",
                    "EndDateTime": "2026-03-07T00:00:00+11:00",
                    "EndDateTime__datatype": "datetime",
                    "Minutes": 835,
                    "Price": 29.82,
                    "ForecastEnergyUsage": 0.0,
                    "EstimatedCost": 0.0,
                    "SlotCount": 167
                }
            ],
            "EnergyUsage": {
                "1hr": {
                    "Hours": 1,
                    "EnergyUsed": 0.0,
                    "TotalCost": 0.0,
                    "AveragePrice": 0
                },
                "24hr": {
                    "Hours": 24,
                    "EnergyUsed": 0.0,
                    "TotalCost": 0.0,
                    "AveragePrice": 0
                }
            }
        }
    ],
    "LastRefresh": "2026-03-06T10:14:07.481844+11:00"
}
```

### /meters

Return energy meter information, as configured in the _DataAPI: Meters:_ parameter above. 

```json
{
    "Meters": [
        {
            "Name": "Panel EM1.1",
            "Type": "meter",
            "DisplayName": "Living & Beds",
            "Power": 286.0
        },
        {
            "Name": "Panel EM1.2",
            "Type": "meter",
            "DisplayName": "Kitchen & Laundry",
            "Power": 210.7
        },
        {
            "Name": "Panel EM2.1",
            "Type": "meter",
            "DisplayName": "Cooking",
            "Power": 0.0
        },
        {
            "Name": "Panel EM2.2",
            "Type": "meter",
            "DisplayName": "Bedroom A/C",
            "Power": 0.0
        },
        {
            "Name": "Panel EM3.1",
            "Type": "meter",
            "DisplayName": "Living A/C",
            "Power": 26.52
        },
        {
            "Name": "Panel EM3.2",
            "Type": "meter",
            "DisplayName": "Study A/C",
            "Power": 50.06
        }
    ],
    "LastRefresh": "2026-03-06T10:15:28.138335+11:00"
}
```

### /tempprobes

Return temperature probe information, as configured in the _DataAPI: TempProbes:_ parameter above. 

```json
{
    "TempProbes": [
        {
            "Name": "Temp Pool Water",
            "Type": "temp_probe",
            "DisplayName": "Pool",
            "Temperature": 25.9,
            "LastReadingTime": "2026-03-06T10:16:13.619495+11:00",
            "LastReadingTime__datatype": "datetime",
            "History": [
                {
                    "Timestamp": "2026-03-01T10:26:17.871014+11:00",
                    "Timestamp__datatype": "datetime",
                    "Temperature": 24.8
                },
                {
                    "Timestamp": "2026-03-01T11:26:23.062229+11:00",
                    "Timestamp__datatype": "datetime",
                    "Temperature": 24.9
                },
                {
                    "Timestamp": "2026-03-01T12:26:33.873555+11:00",
                    "Timestamp__datatype": "datetime",
                    "Temperature": 24.9
                },
                ...
            ]
        },
        {
            "Name": "Temp Roof",
            "Type": "temp_probe",
            "DisplayName": "Roof",
            "Temperature": 27.1,
            "LastReadingTime": "2026-03-06T10:16:13.620818+11:00",
            "LastReadingTime__datatype": "datetime",
            "History": [...]
        },
        {
            "Name": "Temp Air",
            "Type": "temp_probe",
            "DisplayName": "Air",
            "Temperature": 24.3,
            "LastReadingTime": "2026-03-06T10:16:13.621942+11:00",
            "LastReadingTime__datatype": "datetime",
            "History": [...]
        }
    ],
    "LastRefresh": "2026-03-06T10:16:14.728099+11:00"
}
```

### /energyprices

Return Amber electricity forecast price information, as configured in the _DataAPI: EnergyPrices:_ parameter above. 

```json
{
    "EnergyPrices": [
        {
            "StartDateTime": "2026-03-06T10:10:00+11:00",
            "StartDateTime__datatype": "datetime",
            "EndDateTime": "2026-03-06T10:40:00+11:00",
            "EndDateTime__datatype": "datetime",
            "Minutes": 30,
            "Price": 16.25,
            "Status": "OK",
            "Type": "Current"
        },
        {
            "StartDateTime": "2026-03-06T10:40:00+11:00",
            "StartDateTime__datatype": "datetime",
            "EndDateTime": "2026-03-06T11:10:00+11:00",
            "EndDateTime__datatype": "datetime",
            "Minutes": 30,
            "Price": 15.87,
            "Status": "OK",
            "Type": "Forecast"
        },
        {
            "StartDateTime": "2026-03-06T11:10:00+11:00",
            "StartDateTime__datatype": "datetime",
            "EndDateTime": "2026-03-06T11:40:00+11:00",
            "EndDateTime__datatype": "datetime",
            "Minutes": 30,
            "Price": 15.87,
            "Status": "OK",
            "Type": "Forecast"
        },
        {
            "StartDateTime": "2026-03-06T11:40:00+11:00",
            "StartDateTime__datatype": "datetime",
            "EndDateTime": "2026-03-06T12:10:00+11:00",
            "EndDateTime__datatype": "datetime",
            "Minutes": 30,
            "Price": 16.03,
            "Status": "OK",
            "Type": "Forecast"
        },
        ...
    ],
    "LastRefresh": "2026-03-06T10:12:34.701514+11:00"
}
```