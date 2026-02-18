# Configuration file - Files section

Location of log and system state files.

Note: Required keys are shown in **bold**.

| Key | Description | 
|:--|:--|
| **SavedStateFile** | JSON file name to store the Power Controller's device current state and history. | 
| LogfileName | A text log file that records progress messages and warnings. | 
| LogfileMaxLines| Maximum number of lines to keep in the log file. If zero, file will never be truncated. | 
| LogfileVerbosity | The level of detail captured in the log file. One of: none; error; warning; summary; detailed; debug; all. | 
| ConsoleVerbosity | Controls the amount of information written to the console. One of: error; warning; summary; detailed; debug; all. Errors are written to stderr all other messages are written to stdout. | 