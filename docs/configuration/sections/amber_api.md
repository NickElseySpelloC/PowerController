# Configuration file - AmberAPI section

Integration with the Amber Electric API to download real time energy prices for your home. To setup this section, you need to have an energy provider account with Amber Electric. Login to https://app.amber.com.au/developers/ and generate a new token to get your API key.

| Key | Description | 
|:--|:--|
| APIKey | Your Amber API key for used authentication (see above). Alternatively, you can set this via the set the AMBER_API_KEY environment variable. | 
| Mode | Operating mode for the Amber integration:<br>**Live**: Attempt to download prices<br>**Offline**: Pretend Amber API is offline, use cached prices. Useful for testing. <br>**Disabled**: Use the relevant operating schedule for prices. | 
| APIURL | Base URL for API requests. This the servers URL on the Amber developer's page, currently: https://api.amber.com.au/v1 |
| Timeout | Number of seconds to wait for Amber to respond to an API call. | 
| MaxConcurrentErrors | Send an email notification if we get this number of concurrent errors from Amber. |
| RefreshInterval | How often to refresh the pricing data from Amber (in minutes). |
| UsageDataFile | Set to the name of a CSV file to log hourly energy usage and costs as reported by Amber. |
| UsageMaxDays | Maximum number of days to keep in the usage data file. |
| PricesCacheFile | The name of the file to cache Amber pricing data. | 