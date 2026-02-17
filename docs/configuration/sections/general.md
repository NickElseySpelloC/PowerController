# Configuration file - General section

General settings for the Power Controller application.

| Key | Description | 
|:--|:--|
| Label | The label (name) that your installation. Used in the email subject and web viewer app |
| PollingInterval | Number of seconds to sleep between each check of the run plan and possible changes to outputs. Recommended 30 seconds or more. |
| ReportCriticalErrorsDelay | Some critical errors can trigger email notifications - for example the AmberAPI not responding. This is the time in minutes for an issue to persist before we send an email notification. Leave blank to disable. |
| PrintToConsole | Print some basic information to the console during startup and operation |
| DefaultPrice | A default price to use if the Amber API is not available and there is no schedule price defined |
