# Configuration file - PowerTariff section

Optionally, a PowerTariff can be defined that sets out the electricty rates charges by your energy provider. You would use this when Amber Electric isn't in use. Here's an example:

```yaml
PowerTariff:
  - Name: Peak
    Price: 0.266
    StartTime: "08:00"
    EndTime: "19:00"
    DaysOfWeek: Mon, Tue, Wed, Thu, Fri

  - Name: Shoulder
    StartTime: "07:00"
    EndTime: "08:00"
    DaysOfWeek: Mon, Tue, Wed, Thu, Fri
    Price: 0.279

  - Name: Shoulder
    StartTime: "19:00"
    EndTime: "23:00"
    DaysOfWeek: Mon, Tue, Wed, Thu, Fri
    Price: 0.279

  - Name: Shoulder
    StartTime: "07:00"
    EndTime: "23:00"
    DaysOfWeek: Sat
    Price: 0.279

  - Name: Off-Peak
    StartTime: "23:00"
    EndTime: "07:00"
    DaysOfWeek: All
    Price: 0.260

  - Name: Off-Peak
    StartTime: "00:00"
    EndTime: "00:00"
    DaysOfWeek: Sun
    Price: 0.260
```

You must also set **UsePowerTariff** to True for the relevant operating schedule to tell it to use this tariff.

This PowerTariff section provides the following features:

- Multiple day & time slots can be defined for a given tarrif band (for example, there are three distinct time slots for the Shoulder tarrif)
- If the end time is earlier or equal to the start time, then the end time is taken to be the next day.
- When determining whether DaysOfWeek applies to the current day, treat the day as applicable to the start time. For example, if StartTime = 22:00, EndTime = 07:00, DaysOfWeek = Sat and it's currently 23:10 on Sat night, then this entry would be a match.
- If two PowerTariff slots overlap for a given day and time, the first one in the list wins.
- The PowerTariff will be used by an OperatingSchedule if the UsePowerTariff key is set to True in the schedule
- If there are times during the week that have no PowerTariff price defined, a warning will be logged in the log file. For these "gap" times, the system will fall back to using the Price defined in the relwvant schedule window.
