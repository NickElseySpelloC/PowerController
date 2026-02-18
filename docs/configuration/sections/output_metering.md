# Configuration file - OutputMetering section

Enable logging of output energy consumption data to a CSV file and the system state file. You can list any output here that has an energy meter.

If the [web viewer app](viewer_website.md) is enabled then usage summaries are shown for each output for a variety of usage periods including custom.

Note: The section is optionaly, but if you use it, the required keys below are shown in **bold**.

| Key | Description | 
|:--|:--|
| Enable | Set to False to disable all output meter logging. |
| **DataFile** | The CSV file to log to. |
| DataFileMaxDays | Maximum number of days to keep in the CSV data file. Set to -1 for unlimited. |
| **OutputsToLog** | A list of outputs to include in the logs. Each entry can include:<br>**Output**: The name of the output. Must match a Outputs: [item]: Name entry.<br>**DisplayName**: Optionally use this alternative name in the CSV file and in the web view app.<br>**HideFromViewerApp**: If True, log this output int he CSV file but don't show it in the viewer app.  |