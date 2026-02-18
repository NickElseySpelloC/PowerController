# Configuration file - OperatingSchedules section

Define the operating schedules for your devices. These are used to determine when a device is allowed to run when configured for Schedule mode. 

Note: Required keys are shown in **bold**.

| Key | Description | 
|:--|:--|
| **Name** | A name for this schedule - used in the Outputs section. | 
| **Windows** | A list of one or more StartTime / StopTime events for this schedule. Each window can have the following elements.... | 

| Window Paramater | Description | 
|:--|:--|
| **StartTime** | The start time in miliary format, for example "13:30". Must be enclosed in double quotes. |
| **EndTime** | The start time in miliary format, for example "17:30". Must be enclosed in double quotes. |
| DaysOfWeek | Days of the week this window applies to - Mon, Tue, Wed, Thu, Fri, Sat, Sun or All. Multiple days can be specified separated by commas. |
| Price | The average eletricity price in c/kWh for energy during this window. Used to forecast costs when running on a schedule rather than Amber prices. |