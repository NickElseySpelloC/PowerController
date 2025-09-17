"""RunPlanner module. Calculates a run plan for either Amber pricing or a defined schedule.

    Sample format:
    run_plan = {
        "Source": "Amber",
        "Channel": "general",
        "Status": None,
        "RequiredHours": 8.0,
        "PriorityHours": 2.0,
        "PlannedHours": 8.0,
        "NextStartTime": datetime(10, 30),
        "StartNow": True,
        "ForecastAveragePrice": 15.3,
        "ForecastEnergyUsage": 123.4,
        "EstimatedCost": 0.0188802,
        "RunPlan": [
            {
                "Date": "2024-06-01",
                "StartTime": "14:00",
                "EndTime": "15:00",
                "Minutes": 60,
                "AveragePrice": 21.03
            },
            ...
        }
"""  # noqa: D208
import datetime as dt
import operator

from sc_utility import DateHelper, SCLogger

from enumerations import AmberChannel, RunPlanMode, RunPlanStatus


class RunPlanner:
    def __init__(self, logger: SCLogger, plan_type: RunPlanMode, channel: AmberChannel | None = None):
        """Initializes the RunPlanner.

        Args:
            logger (SCLogger): The logger for the run planner.
            plan_type (RunPlanMode): The type of the run plan. Must be one of the RunPlanMode enums.
            channel (AmberChannel | None): The channel of the run plan (one of the AmberChannel enums), or None if plan_type is Schedule.

        Raises:
            RuntimeError: If the plan_type is invalid.
        """
        if plan_type not in RunPlanMode:
            error_msg = f"Invalid plan type: {plan_type}. Must be one of {', '.join([m.value for m in RunPlanMode])}"
            raise RuntimeError(error_msg)
        self.plan_type = plan_type
        self.channel = channel if plan_type == RunPlanMode.BEST_PRICE else None
        self.logger = logger

    def _create_run_plan_object(self) -> dict:
        """Return a new empty run plan object."""
        new_run_plan = {
            "Source": self.plan_type,
            "Channel": self.channel,
            "LastUpdate": DateHelper.now(),
            "Status": None,
            "RequiredHours": 0.0,
            "PriorityHours": 0.0,
            "PlannedHours": 0.0,
            "NextStartTime": None,
            "StartNow": False,
            "ForecastAveragePrice": 0.0,
            "ForecastEnergyUsage": 0.0,
            "EstimatedCost": 0.0,

            "RunPlan": []
        }
        return new_run_plan

    def calculate_run_plan(self, sorted_slot_data: list[dict], required_hours: float, priority_hours: float, max_price: float, max_priority_price: float, hourly_energy_usage: float = 0.0) -> dict:
        """Determines when to run based on the best pricing strategy.

        The time_slots[] list must contain the following keys:
            - StartTime: The start time of the slot (datetime.time)
            - EndTime: The end time of the slot (datetime.time)
            - Price: The price of the slot (float)
            - Minutes: The duration of the slot in minutes (int)

        The run_plan["Status"] key indicates the outcome of the planning process. Use the RunPlanStatus enum
            Nothing: The required_hours were zero. There's nothing to do sowe returned an empty run plan.
            Failed: The run plan could not be filled - could not allocate all required priority hours.
            Partial: The run plan was partially filled, but all the priority hours were allocated.
            Ready: The run plan was filled successfully and is ready to be executed.

        Args:
            sorted_slot_data (list[dict]): A list of dictionaries containing the price data sorted by best for the selected channel.
            required_hours (float): The number of hours required for the task. Set to -1 to get all remaining hours that can be filled by price.
            priority_hours (float): The number of hours that should be prioritized.
            max_price (float): The maximum price to consider for normal hours.
            max_priority_price (float): The maximum price to consider for the priority hours.
            hourly_energy_usage (float): The average hourly energy usage in Wh. Used to estimate cost of the run plan.

        Raises:
            RuntimeError: If the parameters are invalid.

        Returns:
            run_plan (dict): A dictionary containing the run plan. Check the Status key for success or failure.
        """
        # First check to see if an empty plan was requested
        run_plan = self._create_run_plan_object()
        remaining_required_mins = RunPlanner._calculate_required_minutes(required_hours)
        if remaining_required_mins == 0:
            run_plan["RequiredHours"] = run_plan["PriorityHours"] = run_plan["PlannedHours"] = 0.0
            run_plan["Status"] = RunPlanStatus.NOTHING
            return run_plan

        # Max sure the priority_hours is <= required_hours
        if required_hours != -1:
            priority_hours = min(priority_hours, required_hours)

        # Set the run plan hours
        run_plan["RequiredHours"] = required_hours
        run_plan["PriorityHours"] = priority_hours

        # If we were passed an empty slot list but requested hours, we can't fulfill the request
        if not sorted_slot_data:
            run_plan["Status"] = RunPlanStatus.FAILED
            run_plan["PlannedHours"] = 0.0
            return run_plan

        # Validate the parameters
        if max_price <= 0 or max_priority_price <= 0:
            error_msg = "Invalid price parameters for run plan."
            raise RuntimeError(error_msg)

        # Initialise our countdowns
        filled_mins = 0
        required_priority_mins = int(priority_hours * 60)
        required_priority_mins = min(required_priority_mins, remaining_required_mins)

        # Iterate through the sorted price data and add each slot indidually if it conforms to the price limits.
        for slot in sorted_slot_data:
            duration_mins = slot["Minutes"]

            # If slot is too expensive for priority hours, skip it
            if slot["Price"] > max_priority_price:
                continue
            if (slot["Price"] <= max_price and duration_mins <= remaining_required_mins) or (slot["Price"] <= max_priority_price and filled_mins < required_priority_mins):
                filled_mins += duration_mins
                remaining_required_mins -= duration_mins
            else:
                continue

            # If we get to get, we can add this price slot to our raw run plan
            end_time = slot["EndTime"]
            if remaining_required_mins < 0:
                # We have overrun, so reduce the end time
                end_dt = dt.datetime.combine(DateHelper.today(), end_time)
                end_dt -= dt.timedelta(minutes=abs(remaining_required_mins))
                end_time = end_dt.time()
            run_entry = {
                "Date": slot["Date"],
                "StartTime": slot["StartTime"],
                "EndTime": slot["EndTime"],
                "Minutes": duration_mins,
                "Price": slot["Price"],
                "ForecastEnergyUsage": (hourly_energy_usage / 60) * duration_mins if hourly_energy_usage > 0 else 0.0,
                "EstimatedCost": (hourly_energy_usage / (60 * 1000)) * duration_mins * (slot["Price"] / 100) if hourly_energy_usage > 0 else 0.0,
                "SlotCount": 1   # Used to count the number of slots merged together so that we can calculate the average price
            }
            run_plan["RunPlan"].append(run_entry)

            if remaining_required_mins <= 0:
                remaining_required_mins = 0
                break

        # We've completed the loop, let's finalise the run plan
        if not run_plan["RunPlan"] or filled_mins < required_priority_mins:
            run_plan["Status"] = RunPlanStatus.FAILED
        elif remaining_required_mins > 0:
            run_plan["Status"] = RunPlanStatus.PARTIAL
        else:
            run_plan["Status"] = RunPlanStatus.READY

        return RunPlanner._consolidate_run_plan(run_plan)

    @staticmethod
    def _consolidate_run_plan(run_plan) -> dict:
        """
        Consolidate the run plan by merging overlapping time slots and summarizing the total hours.

        Args:
            run_plan (dict): The run plan to consolidate.

        Returns:
            dict: The consolidated run plan.
        """
        # Sort the run plan by start time
        run_plan["RunPlan"].sort(key=operator.itemgetter("StartTime"))

        # Merge overlapping time slots
        merged_slots = []
        for slot in run_plan["RunPlan"]:
            if not merged_slots:
                merged_slots.append(slot)
            else:
                last_slot = merged_slots[-1]
                if slot["StartTime"] <= last_slot["EndTime"]:
                    # Overlapping slot found, merge them
                    last_slot["EndTime"] = max(last_slot["EndTime"], slot["EndTime"])
                    last_slot["Minutes"] += slot["Minutes"]
                    last_slot["SlotCount"] += 1
                    last_slot["Price"] += slot["Price"]
                    last_slot["ForecastEnergyUsage"] += slot["ForecastEnergyUsage"]
                    last_slot["EstimatedCost"] += slot["EstimatedCost"]
                else:
                    merged_slots.append(slot)

        # Fixup the averaged price per slot and the total average price
        price_total = 0
        slot_total = 0
        total_minutes = 0
        total_energy_used = 0.0
        total_cost = 0.0

        for slot in merged_slots:
            total_minutes += slot["Minutes"]
            price_total += slot["Price"]
            slot_total += slot["SlotCount"]
            if slot["SlotCount"] > 1:
                slot["Price"] /= slot["SlotCount"]
            slot["Price"] = round(slot["Price"], 2)
            total_energy_used += slot["ForecastEnergyUsage"]
            total_cost += slot["EstimatedCost"]
        run_plan["PlannedHours"] = total_minutes / 60.0
        run_plan["ForecastAveragePrice"] = round(price_total / slot_total, 2) if slot_total > 0 else 0.0
        run_plan["ForecastEnergyUsage"] = total_energy_used
        run_plan["EstimatedCost"] = total_cost

        run_plan["RunPlan"] = merged_slots

        # NextStartTime and StartNow
        run_plan["StartNow"] = False
        if run_plan["RunPlan"]:
            run_plan["NextStartTime"] = run_plan["RunPlan"][0]["StartTime"]
            time_now = DateHelper.now().replace(tzinfo=None).time()
            run_plan["StartNow"] = run_plan["NextStartTime"] <= time_now

        return run_plan

    @staticmethod
    def _calculate_required_minutes(required_hours: float) -> int:
        """
        Calculate the required minutes for the run plan.

        Args:
            required_hours (float): The number of hours required for the task. If -1, return all remaining minutes in the day

        Returns:
            int: The total required minutes.
        """
        # If required_hours is -1, we need to fill all remaining time today (hot water mode)
        if required_hours == -1:
            current_time = DateHelper.now().replace(tzinfo=None)
            remaining_required_mins = 24 * 60 - (current_time.hour * 60 + current_time.minute)
            # Round down to the nearest 5 minutes
            if remaining_required_mins % 5 != 0:
                remaining_required_mins -= 5 - (remaining_required_mins % 5)
        else:
            remaining_required_mins = required_hours * 60
        remaining_required_mins = max(0, remaining_required_mins)

        return int(remaining_required_mins)

    @staticmethod
    def print_info(run_plan: dict, title: str | None) -> str:
        """
        Print the run plan in a readable format.

        Args:
            run_plan (dict): The run plan to print.
            title (str): The title to display before the run plan.

        Returns:
            str: The formatted run plan string that can be printed or logged.
        """
        return_str = f"{title} run plan:\n" if title else "Run Plan:\n"

        return_str += f"  - Source: {run_plan['Source']}\n"
        return_str += f"  - Channel: {run_plan['Channel']}\n"
        return_str += f"  - Status: {run_plan['Status']}\n"
        return_str += f"  - RequiredHours: {run_plan['RequiredHours']}\n"
        return_str += f"  - PriorityHours: {run_plan['PriorityHours']}\n"
        return_str += f"  - PlannedHours: {run_plan['PlannedHours']}\n"
        return_str += f"  - NextStartTime: {run_plan['NextStartTime']}\n"
        return_str += f"  - StartNow: {run_plan['StartNow']}\n"
        return_str += f"  - ForecastAveragePrice: {run_plan['ForecastAveragePrice']}\n"
        return_str += "   - Run Plan Slots:\n"
        for slot in run_plan.get("RunPlan", []):
            return_str += f"     - Start: {slot['StartTime']}, End: {slot['EndTime']}, Duration: {slot['Minutes']}, Price: {slot['Price']}\n"

        return return_str
