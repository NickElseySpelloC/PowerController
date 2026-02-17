# Configuration 

The PowerController application is configured using the **config.yaml** file. An [example Configuration File](example_config.md) has been provided as part of the installation - you can copy this to config.yaml to get started. 

We recommend fully configuring the config file before attempting to run the application. When the app starts, it will do its best to validate the contents of the config file. That being said, some errors might not be reported until the app is fully running (see [log files](../running.md)).

You can edit config.yaml using nano:
```bash 
nano config.yaml
```
...or you can copy it to a desktop system and use your favorite editor that include yaml syntax validation (we recommend VSCode with the redhat.vscode-yaml extension).

The config file supports the following sections. Some of mandatory and some are optional. The same goes for the various keys in each section. The supported sections are outline below. A seperate help page has been provided for each one (click on the section name).

<div class="config-table" markdown>

| Section | Description | Required | 
|:--|:--|:--|
| [General](sections/general.md) | General settings for the Power Controller application | Yes |
| Files | Location of log and system state files | Yes |
| Email | use this section here if you want to be emailed when there's a critical error or excessive energy use | No |
| Website | Settings for the built-in web server that provides a web interface to view and control the outputs | No |
| AmberAPI | Integration with the Amber Electric API to download real time energy prices for your home | No |
| ShellyDevices | Describe the Shelly devices you want to control | Yes |
| Outputs | Configure the behaviour of each outputs and/or meters that will control and monitor your electrical devices | Yes |
| OperatingSchedules | Schedule used for switched outputs | Yes |
| OutputSequences | Define a sequence of actions to perform on outputs when turning On or off | No |
| ViewerWebsite | Integration with the [PowerControllerViewer app](https://github.com/NickElseySpelloC/PowerControllerViewer) | No |
| OutputMetering | Logging of output energy consumption data to CSV and the system state file, as well as viewing and charting in the PowerControllerView application (if enabled) | No |
| TempProbeLogging | Logging of temperature probes to CSV and the system state file, as well as viewing and charting in the PowerControllerView application (if enabled) | No |
| UPSIntegration | Define one or more UPS units that can modify the behaviour of an Output | No |
| Location | Specific the location of your home. Used to define dawn and dusk times in an operating schedule | No |
| TeslaMate | Configure integration with the TeslaMate database to import Tesla charging session data | No |
| HeartbeatMonitor | Integration with a [Better Uptime](https://betterstack.com/uptime) heartbeat monitor to monitor uptime of the application | No |

</div>

