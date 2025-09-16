"""Configuration schemas for use with the SCConfigManager class."""


class ConfigSchema:
    """Base class for configuration schemas."""

    def __init__(self):
        self.placeholders = {
            "DeviceType": {
                "WebsiteAccessKey": "<Your website API key here>",
            },
            "AmberAPI": {
                "APIKey": "<Your API Key Here>",
            },
            "Email": {
                "SMTPUsername": "<Your SMTP username here>",
                "SMTPPassword": "<Your SMTP password here>",
            }
        }

        self.validation = {
            "General": {
                "type": "dict",
                "schema": {
                    "Label": {"type": "string", "required": False, "nullable": True},
                    "ReportCriticalErrorsDelay": {"type": "number", "required": False, "nullable": True, "min": 1, "max": 3600},
                },
            },
            "AmberAPI": {
                "type": "dict",
                "schema": {
                    "Mode": {"type": "string", "required": False, "nullable": True, "allowed": ["Live", "Offline", "Disabled"]},
                    "APIURL": {"type": "string", "required": False, "nullable": True},
                    "APIKey": {"type": "string", "required": False, "nullable": True},
                    "Timeout": {"type": "number", "required": False, "nullable": True, "min": 5, "max": 60},
                    "MaxConcurrentErrors": {"type": "number", "required": False, "nullable": True, "min": 0},
                    "RefreshInterval": {"type": "number", "required": False, "nullable": True, "min": 5, "max": 30}
                },
            },
            "ShellyDevices": {
                "type": "dict",
                "schema": {
                    "AllowDebugLogging": {"type": "boolean", "required": False, "nullable": True},
                    "ResponseTimeout": {"type": "number", "required": False, "nullable": True, "min": 1, "max": 120},
                    "RetryCount": {"type": "number", "required": False, "nullable": True, "min": 0, "max": 10},
                    "RetryDelay": {"type": "number", "required": False, "nullable": True, "min": 1, "max": 10},
                    "PingAllowed": {"type": "boolean", "required": False, "nullable": True},
                    "WebhooksEnabled": {"type": "boolean", "required": False, "nullable": True},
                    "WebhookHost": {"type": "string", "required": False, "nullable": True},
                    "WebhookPort": {"type": "number", "required": False, "nullable": True},
                    "WebhookPath": {"type": "string", "required": False, "nullable": True},
                    "Devices": {
                        "type": "list",
                        "required": True,
                        "nullable": False,
                        "schema": {
                            "type": "dict",
                            "schema": {
                                "Name": {"type": "string", "required": False, "nullable": True},
                                "Model": {"type": "string", "required": True},
                                "Hostname": {"type": "string", "required": False, "nullable": True},
                                "Port": {"type": "number", "required": False, "nullable": True},
                                "ID": {"type": "number", "required": False, "nullable": True},
                                "Simulate": {"type": "boolean", "required": False, "nullable": True},
                                "Colour": {"type": "string", "required": False, "nullable": True},
                                "Inputs": {
                                    "type": "list",
                                    "required": False,
                                    "nullable": True,
                                    "schema": {
                                        "type": "dict",
                                        "schema": {
                                            "Name": {"type": "string", "required": False, "nullable": True},
                                            "ID": {"type": "number", "required": False, "nullable": True},
                                            "Webhooks": {"type": "boolean", "required": False, "nullable": True},
                                        },
                                    },
                                },
                                "Outputs": {
                                    "type": "list",
                                    "required": False,
                                    "nullable": True,
                                    "schema": {
                                        "type": "dict",
                                        "schema": {
                                            "Name": {"type": "string", "required": False, "nullable": True},
                                            "Group": {"type": "string", "required": False, "nullable": True},
                                            "ID": {"type": "number", "required": False, "nullable": True},
                                            "Webhooks": {"type": "boolean", "required": False, "nullable": True},
                                        },
                                    },
                                },
                                "Meters": {
                                    "type": "list",
                                    "required": False,
                                    "nullable": True,
                                    "schema": {
                                        "type": "dict",
                                        "schema": {
                                            "Name": {"type": "string", "required": False, "nullable": True},
                                            "ID": {"type": "number", "required": False, "nullable": True},
                                            "MockRate": {"type": "number", "required": False, "nullable": True},
                                        },
                                    },
                                },
                            },
                        },
                    },
                }
            },
            "Location": {
                "type": "dict",
                "required": False,
                "nullable": True,
                "schema": {
                    "UseShellyDevice": {"type": "string", "required": False, "nullable": True},
                    "GoogleMapsURL": {"type": "string", "required": False, "nullable": True},
                    "Timezone": {"type": "string", "required": False, "nullable": True},
                    "Latitude": {"type": "number", "required": False, "nullable": True},
                    "Longitude": {"type": "number", "required": False, "nullable": True},
                },
            },
            "OperatingSchedules": {
                "type": "list",
                "required": True,
                "nullable": False,
                "schema": {
                    "type": "dict",
                    "schema": {
                        "Name": {"type": "string", "required": True},
                        "Windows": {
                            "type": "list",
                            "required": True,
                            "schema": {
                                "type": "dict",
                                "schema": {
                                    "StartTime": {"type": "string", "required": True},
                                    "EndTime": {"type": "string", "required": True},
                                    "Price": {"type": "number", "required": False, "nullable": True},
                                    "DaysOfWeek": {"type": "string", "required": False, "nullable": True},
                                    "DatesOff": {
                                        "type": "list",
                                        "required": False,
                                        "nullable": True,
                                        "schema": {
                                            "type": "dict",
                                            "schema": {
                                                "StartDate": {"type": "date", "required": False, "nullable": True},
                                                "EndDate": {"type": "date", "required": False, "nullable": True},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "Outputs": {
                "type": "list",
                "required": True,
                "nullable": False,
                "schema": {
                    "type": "dict",
                    "schema": {
                        "Name": {"type": "string", "required": True},
                        "DeviceOutput": {"type": "string", "required": True},
                        "Mode": {"type": "string", "required": True, "allowed": ["Schedule", "BestPrice"]},
                        "Schedule": {"type": "string", "required": False, "nullable": True},
                        "AmberChannel": {"type": "string", "required": False, "nullable": True, "allowed": ["general", "controlledLoad"]},
                        "DaysOfHistory": {"type": "number", "required": False, "nullable": True, "min": 2, "max": 60},
                        "TargetHours": {"type": "number", "required": True, "min": -1, "max": 24},
                        "MonthlyTargetHours": {"type": "dict", "required": False, "nullable": True},
                        "MinHours": {"type": "number", "required": False, "nullable": True, "min": 0, "max": 20},
                        "MaxHours": {"type": "number", "required": False, "nullable": True, "min": 1, "max": 24},
                        "MaxShortfallHours": {"type": "number", "required": False, "nullable": True, "min": 1, "max": 48},
                        "MaxBestPrice": {"type": "number", "required": True, "min": 1, "max": 1000},
                        "MaxPriorityPrice": {"type": "number", "required": True, "min": 1, "max": 1000},
                        "DatesOff": {
                            "type": "list",
                            "required": False,
                            "nullable": True,
                            "schema": {
                                "type": "dict",
                                "schema": {
                                    "StartDate": {"type": "date", "required": False, "nullable": True},
                                    "EndDate": {"type": "date", "required": False, "nullable": True},
                                },
                            },
                        },
                        "DeviceMeter": {"type": "string", "required": False, "nullable": True},
                        "MaxDailyEnergyUse": {"type": "number", "required": False, "nullable": True, "min": 100, "max": 50000},
                        "DeviceInput": {"type": "string", "required": False, "nullable": True},
                        "DeviceInputMode": {"type": "string", "required": False, "nullable": True, "allowed": ["Ignore", "TurnOn", "TurnOff"]},
                        "ParentOutput": {"type": "string", "required": False, "nullable": True},
                        "StopOnExit": {"type": "boolean", "required": False, "nullable": True},
                    },
                },
            },
            "Files": {
                "type": "dict",
                "schema": {
                    "SavedStateFile": {"type": "string", "required": True},
                    "LogfileName": {"type": "string", "required": False, "nullable": True},
                    "LogfileMaxLines": {"type": "number", "required": False, "nullable": True, "min": 0, "max": 100000},
                    "LogfileVerbosity": {"type": "string", "required": True, "allowed": ["none", "error", "warning", "summary", "detailed", "debug", "all"]},
                    "ConsoleVerbosity": {"type": "string", "required": True, "allowed": ["error", "warning", "summary", "detailed", "debug"]},
                },
            },
            "Email": {
                "type": "dict",
                "schema": {
                    "EnableEmail": {"type": "boolean", "required": False, "nullable": True},
                    "DailyEnergyUseThreshold": {"type": "number", "required": False, "nullable": True, "min": 1000, "max": 25000},
                    "SendEmailsTo": {"type": "string", "required": False, "nullable": True},
                    "SMTPServer":  {"type": "string", "required": False, "nullable": True},
                    "SMTPPort": {"type": "number", "required": False, "nullable": True, "min": 25, "max": 10000},
                    "SMTPUsername": {"type": "string", "required": False, "nullable": True},
                    "SMTPPassword": {"type": "string", "required": False, "nullable": True},
                    "SubjectPrefix": {"type": "string", "required": False, "nullable": True},
                },
            },
            "HeartbeatMonitor": {
                "type": "dict",
                "schema": {
                    "Enable": {"type": "boolean", "required": False, "nullable": True},
                    "WebsiteURL": {"type": "string", "required": False, "nullable": True},
                    "HeartbeatTimeout": {"type": "number", "required": False, "nullable": True, "min": 1, "max": 60},
                    "Frequency": {"type": "number", "required": False, "nullable": True, "min": 1, "max": 3600},
                },
            },
            "ViewerWebsite": {
                "type": "dict",
                "schema": {
                    "Enable": {"type": "boolean", "required": False, "nullable": True},
                    "Label": {"type": "string", "required": False, "nullable": True},
                    "BaseURL": {"type": "string", "required": False, "nullable": True},
                    "AccessKey": {"type": "string", "required": False, "nullable": True},
                    "APITimeout": {"type": "number", "required": False, "nullable": True, "min": 1, "max": 60},
                    "Frequency": {"type": "number", "required": False, "nullable": True, "min": 1, "max": 3600},
                },
            },
        }
