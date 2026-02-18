# Configuration file - HeartbeatMonitor section

Integration with a [Better Uptime](https://betterstack.com/uptime) heartbeat monitor to monitor uptime of the application.

| Key | Description | 
|:--|:--|
| Enable | Set to True to enable integration with the Heartbeat monitoring service. | 
| WebsiteURL | Each time the app runs successfully, you can have it hit this URL to record a heartbeat. This is optional. If the app exist with a fatal error, it will append /fail to this URL. | 
| HeartbeatTimeout | How long to wait for a response from the website before considering it down in seconds. | 
| Frequency | How often to post the state to the heartbeat monitor (in seconds). | 