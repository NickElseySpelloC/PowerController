# Setup your Shelly devices

PowerController requires at least one [Shelly](https://www.shelly.com) device to operate. You can run the application in simulation mode for testing, but to actually control and/or meter an electrical device, you'll need at least one Shelly device installed and configured. Shelly make a wide range of home automation products. PowerController supports the majority of Shelly's smart switches and energy meters that support WiFi or Ethernet connectivity.

1. Install your device(s) according to Shelly's installation instructions. 
    - Get help from a licensed electrician if you're uncomfortable doing this work yourself. 
    - You must connect the device to your network via WiFi or Ethernet (PowerController doesn't support Bluetooth, Z-Wave or Zigbee only devices at this time)
2. Use the Shelly app to make sure the device is working as intended. 
3. Please _do not_ create any Actions for the device (these might conflict with the app's control of the device).
4. In the app, go to Settings > Device Information and make a note of the following:
    - Device IP address (e.g. 192.168.86.21)
    - Device Type (e.g. Shelly Plus 2 PM)
5. Lookup the device type in [models library](https://nickelseyspelloc.github.io/sc_utility/guide/shelly_models_list/) and make a note of the model identifier (e.g. ShellyPlus2PM). Here's the entry for our example:
```json
    {
      "model": "ShellyPlus2PM",
      "name": "Shelly Plus 2PM",
      "url": "https://shelly-api-docs.shelly.cloud/gen2/Devices/Gen2/ShellyPlus2PM",
      "generation": 2,
      "protocol": "RPC",
      "inputs": 2,
      "outputs": 2,
      "meters": 2,
      "meters_seperate": false,
      "temperature_monitoring": true
    },
```

## Unsupported device

If you've bought a Shelly smart switch or energy meter and are having problems getting it to work, you can try modifying the [shelly_models.json](https://nickelseyspelloc.github.io/sc_utility/guide/shelly_models_list/) file included with the sc_utility library to add or update your devie. Alternatively, please contact [Nick Elsey](https://www.spelloconsulting.com/contact-nick-elsey) for support.


# Next Step >> [Install PowerController](install_app.md)