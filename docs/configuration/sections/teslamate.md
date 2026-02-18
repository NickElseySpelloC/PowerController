# Configuration file - TeslaMate section

This can be used to import Tesla charging data from a local network instance of [TeslaMate ](https://docs.teslamate.org/docs/installation/docker).  

If you want to limit data imports to home charging, first set a geofence name in the TeslaMaste dashboard (Home > Dashboards > TeslaMate > Charges) and then set this geofence name in the GeofenceName config parameter.

| Key | Description | 
|:--|:--|
| Enable | Set to True to enable integration with the TeslaMate database. | 
| RefreshInterval| How often to refresh the TeslaMate data (in minutes). | 
| Host| The host address of the TeslaMate database (or use the TESLAMATE_DB_HOST environment variable).| 
| Port| The port number of the TeslaMate database (or use the TESLAMATE_DB_PORT environment variable). | 
| DatabaseName | The name of the TeslaMate database (or use the TESLAMATE_DB_NAME environment variable). | 
| DBUsername | The username to connect to the TeslaMate database (or use the TESLAMATE_DB_USER environment variable). | 
| DBPassword |  The password to connect to the TeslaMate database (or use the TESLAMATE_DB_PASSWORD environment variable). | 
