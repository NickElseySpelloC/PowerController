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
| Meters  | A list of meters to include in the /meters end-point response. Each entry must define a **Name** that must match a [ShellyDevices: Devices: Meters: Name:](shelly_devices.md) entry and optionally a **DisplayName**. | 
| TempProbes | A list of temperature to include in the /tempprobes end-point response. Each entry must define a **Name** that must match a [ShellyDevices: Devices: TempProbes: Name:](shelly_devices.md) entry and optionally a **DisplayName**. | 
| TempProbeHistoryDays | The number of days of temperature probe history to include with each temp probe history. If this is set, then this probe must be configured in a HistoryDataFileMaxDays: Probes: Name entry and the days of temp probe logging history (HistoryDataFileMaxDays: HistoryDataFileMaxDays: ) must be greater than this parameter. |
| EnergyPrices | Configure the response for the /energyprices end-point, which returns the current and forecast Amber energy prices. If this section is anbled, you must have [Amber energy pricing enabled](amber_api.md). The following parameters are supported:<br>**AmberChannel**: The Amber pricing channel to report on, typically either **general** or **controlledLoad**. <br>**IntervalTime**: Interval for each forecast period in minutes (e.g. 30 for half-hourly prices, 60 for hourly prices)<br>**NumIntervals**: Number of intervals to return in the forecast (e.g. 48 for 24 hours of half-hourly prices, 24 for 24 hours of hourly prices)<br>**WarningPrice**: If the price exceeds this value, the API will include a warning in the response for this interval. Set to 0 to disable warnings.<br>**CriticalPrice** If the price exceeds this value, the API will include a critical warning in the response for this interval. Set to 0 to disable critical warnings. |

## API End Points

The Data API response to the following end-points

### /outputs

Return output information, as configured in the _DataAPI: Outputs:_ parameter above. 

### /meters

Return Shelly energy meter information, as configured in the _DataAPI: Meters:_ parameter above. 

### /tempprobes

Return Shelly temperature probe information, as configured in the _DataAPI: TempProbes:_ parameter above. 


### /energyprices

Return Amber electricity forecast price information, as configured in the _DataAPI: EnergyPrices:_ parameter above. 

