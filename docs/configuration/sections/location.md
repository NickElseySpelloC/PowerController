# Configuration file - Location section

Specify the geographic location and timezone of your installation. This is used to determine the dawn and dusk times for schedules that use this feature. 

You can specify your location in one of three ways - device location (IP goecoding); Google Maps URL or manual. All three options also require your timezone (see [this page](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for a list ). 

## Shelly Device Location

Use a Shelly device's location (using IP lookup) by specifing the device name in the UseShellyDevice field.

```yaml
Location:
    Timezone: Europe/London
    UseShellyDevice: Shelly Pool 1
```

## Google Maps URL

Use a Google Maps URL to extract the location - specify the GoogleMapsURL field and the Timezone field.

```yaml
Location:
    Timezone: Europe/London
    GoogleMapsURL: https://www.google.com/maps/place/Buckingham+Palace/@51.4993124,-0.1353157,14.92z
```

## Manual 

Manually specify the latitude and longitude - specify the Timezone, Latitude and Longitude fields.

```yaml
Location:
    Timezone: Europe/London
    Latitude: 51.4993124
    Longitude: -0.1353157
```
