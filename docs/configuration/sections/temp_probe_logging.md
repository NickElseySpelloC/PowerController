# Configuration file - TempProbeLogging section

Log temperature probe readings to the system state JSON file and/or a CSV file. 

Temperature readings can be aquired from two sources:

1. One or more ds18b20 digital temperature probes connected to a Shelly Addon device (see [Shelly Setup](../../installation/shelly_setup.md) for more information. )
2. An internal temperature probe that's included in most modern Shelly smart switches.

Note: The section is optionaly, but if you use it, the required keys below are shown in **bold**.

| Key | Description |
|:--|:--|
| Enable | Set to True or False |
| **Probes** | A list of temp probe names, as defined in the ShellyDevices: Devices: [Device]: TempProbes section. You can optionally add:<br>**DisplayName**: Name to be used in logging.<br>**Colour**: The colour to use when charting this probe.<br>**HideFromViewerApp**: If True, ony log to the CSV file.  |
| **LoggingInterval** | Log temp probe readings every N minutes |
| LastReadingWithinMinutes | Only log readings that have been updated within this number of minutes. 0 to disable. |
| SavedStateFileMaxDays | Number of days to keep in the data in the system state file. Try to keep this as low as possible to reduce file size. 0 to disable. |
| HistoryDataFile | Leave blank to disable logging to a CSV file. |
| HistoryDataFileMaxDays | Maximum number of days to keep in the history data file.  0 to disable. |
| **Charting** | Optionally use this section to configure how the PowerControllerViewer web app charts temperature reading history. The requires the following sub-keys:<br>**Enable**: Set to true to enable charting.<br>**Charts**: A list of chart configurations - see below. | 


The Charting: Charts section is a list of entries, each one defining a specifc chart to be displayed by the PowerControllerViewer app. Each entry requires the following 

| Key | Description |
|:--|:--|
| **Name** | The name of this chart. This will be used for the chart title. |
| **Probes**:  |  A list of the temperature probe(s) to include in this chart.  |
| **DaysToShow**  | How many days of data to show in this chart. This must be equal to or less than the **HistoryDataFileMaxDays** figure.   |

Here's an example:

```yaml
    ...
    Charting:
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
```