"""RunPlanner module. Calculates a run plan for either Amber pricing or a defined schedule."""
import datetime as dt
import operator

from org_enums import RunPlanMode, RunPlanStatus
from sc_utility import DateHelper, SCLogger

from local_enumerations import AmberChannel


class RunPlanner:
    """Class to calculate a run plan based on either Amber pricing or a defined schedule."""

    # Public Functions ============================================================================
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

    def calculate_run_plan(self,
                           sorted_slot_data: list[dict],
                           required_hours: float,
                           priority_hours: float,
                           max_price: float,
                           max_priority_price: float,
                           hourly_energy_usage: float = 0.0,
                           slot_min_minutes: int = 0,
                           slot_min_gap_minutes: int = 0,
                           constraint_slots: list[dict] | None = None) -> dict:
        """Determines when to run based on the best pricing strategy.

        Honours slot_min_minutes (minimum final slot length) and slot_gap_minutes
        (minimum gap between final slots - gaps smaller than this are eliminated by merging).

        Args:
            sorted_slot_data (list[dict]): A list of slot data dictionaries, each containing:
                - "Date" (datetime.date | None): The date of the slot, or None if today.
                - "StartDateTime" (datetime.datetime): The start time of the slot.
                - "EndDateTime" (datetime.datetime): The end time of the slot.
                - "Minutes" (int): The duration of the slot in minutes.
                - "Price" (float): The price of the slot in pence per kWh.
            required_hours (float): The number of hours required for the task. If -1, return all remaining minutes in the day.
            priority_hours (float): The number of hours that can be run at the priority price.
            max_price (float): The maximum price (in pence per kWh) for normal hours.
            max_priority_price (float): The maximum price (in pence per kWh) for priority hours.
            hourly_energy_usage (float): The estimated energy usage in Watts when the task is running. Default is 0.0 (unknown).
            slot_min_minutes (int): The minimum length of a final slot in minutes. Default is 0 (no minimum).
            slot_min_gap_minutes (int): The minimum gap between final slots in minutes. Gaps smaller than this are eliminated by merging. Default is 0 (no gap merging).
            constraint_slots (list[dict]): A list of constraint slots to consider when calculating the run plan. Each dictionary contains:
                - "StartDateTime" (datetime.datetime): The start time of the constraint slot.
                - "EndDateTime" (datetime.datetime): The end time of the constraint slot.

        Raises:
            RuntimeError: If the price parameters are invalid.

        Returns:
            dict: A run plan dictionary containing:
                - "Source": The source of the run plan (BestPrice or Schedule).
                - "Channel": The channel of the run plan (if applicable).
                - "LastUpdate": The timestamp of the last update.
        """
        run_plan = self._create_run_plan_object()
        run_plan["SlotMinMinutes"] = slot_min_minutes
        run_plan["SlotGapMinutes"] = slot_min_gap_minutes

        required_mins = RunPlanner._calculate_required_minutes(required_hours)
        if required_mins == 0:
            run_plan["RequiredHours"] = run_plan["PriorityHours"] = run_plan["PlannedHours"] = run_plan["RemainingHours"] = 0.0
            run_plan["Status"] = RunPlanStatus.NOTHING
            return run_plan

        if required_hours != -1:
            priority_hours = min(priority_hours, required_hours)

        run_plan["RequiredHours"] = required_hours
        run_plan["PriorityHours"] = priority_hours

        if not sorted_slot_data:
            if self.plan_type == RunPlanMode.SCHEDULE and required_hours == -1 and priority_hours == 0:
                run_plan["Status"] = RunPlanStatus.NOTHING  # Special case: we've asked for all hours and we've completed our schedule
            else:
                run_plan["Status"] = RunPlanStatus.FAILED
            run_plan["PlannedHours"] = 0.0
            run_plan["RemainingHours"] = 0.0
            return run_plan

        if max_price <= 0 or max_priority_price <= 0:
            error_msg = "Invalid price parameters for run plan."
            raise RuntimeError(error_msg)

        # Step 1: Select qualifying slots based on price criteria and optionally the constraint slots
        selected_slots = self._select_qualifying_slots(
                                    sorted_slot_data=sorted_slot_data,
                                    remaining_required_mins=required_mins,
                                    max_price=max_price,
                                    max_priority_price=max_priority_price,
                                    hourly_energy_usage=hourly_energy_usage,
                                    constraint_slots=constraint_slots
                                )

        if not selected_slots:
            run_plan["Status"] = RunPlanStatus.FAILED
            run_plan["PlannedHours"] = 0.0
            run_plan["RemainingHours"] = 0.0
            return run_plan

        # Step 2: Consolidate slots to honor min_minutes and gap constraints
        consolidated_slots = self._consolidate_slots(selected_slots, slot_min_minutes, slot_min_gap_minutes)

        # Step 3: Trim to exact required hours if needed
        final_slots = self._trim_to_required_hours(consolidated_slots, required_mins)

        # Step 4: Calculate final plan metrics
        return self._finalize_run_plan(run_plan, final_slots, required_mins, int(priority_hours * 60))

    @staticmethod
    def tick(run_plan: dict) -> dict:
        """Perform any periodic tasks needed by the RunPlanner.

        Args:
            run_plan (dict): The current run plan.

        Returns:
            dict: The updated run plan.
        """
        future_minutes = 0
        now = DateHelper.now()

        for slot in run_plan.get("RunPlan", []):
            # Add to future minutes for the portion of the slot that is in the future
            minutes = slot["Minutes"]
            if slot["EndDateTime"] > now:
                if slot["StartDateTime"] >= now:
                    future_minutes += minutes
                else:
                    future_minutes += int((slot["EndDateTime"] - now).total_seconds() / 60)

        run_plan["RemainingHours"] = future_minutes / 60.0

        return run_plan

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
        return_str += f"  - RemainingHours: {run_plan['RemainingHours']}\n"
        return_str += f"  - NextStartDateTime: {run_plan['NextStartDateTime']}\n"
        return_str += f"  - NextStopDateTime: {run_plan['NextStopDateTime']}\n"
        return_str += f"  - ForecastAveragePrice: {run_plan['ForecastAveragePrice']}\n"
        return_str += "   - Run Plan Slots:\n"
        for slot in run_plan.get("RunPlan", []):
            return_str += f"     - Start: {slot['StartDateTime']}, End: {slot['EndDateTime']}, Duration: {slot['Minutes']}, Price: {slot['Price']}\n"

        return return_str

    @staticmethod
    def get_current_slot(run_plan: dict) -> tuple[dict | None, bool]:
        """
        Get the current active slot from the run plan.

        Args:
            run_plan (dict): The run plan to check.

        Returns:
            tuple(dict | None, bool): The current active slot if found, otherwise None. Also returns a boolean indicating if a slot is currently active (i.e. should be running now).
        """
        current_time = DateHelper.now()
        for slot in run_plan.get("RunPlan", []):
            if slot["StartDateTime"] <= current_time <= slot["EndDateTime"]:
                return slot, True
        return None, False

    # Private Functions ============================================================================
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
            "RemainingHours": 0.0,
            "NextStartDateTime": None,
            "NextStopDateTime": None,
            "ForecastAveragePrice": 0.0,
            "ForecastEnergyUsage": 0.0,
            "EstimatedCost": 0.0,

            "RunPlan": []
        }
        return new_run_plan

    def _select_qualifying_slots(self, sorted_slot_data: list[dict], remaining_required_mins: int,  # noqa: PLR6301
                            max_price: float, max_priority_price: float,
                            hourly_energy_usage: float, constraint_slots: list[dict] | None = None) -> list[dict]:
        """Select slots that qualify based on price criteria.

        Args:
            sorted_slot_data (list[dict]): A list of slot data dictionaries (see calculate_run_plan):
            remaining_required_mins (int): The total remaining minutes required for the task.
            max_price (float): The maximum price (in pence per kWh) for normal hours.
            max_priority_price (float): The maximum price (in pence per kWh) for priority hours.
            hourly_energy_usage (float): The estimated energy usage in Watts when the task is running. Default is 0.0 (unknown).
            constraint_slots (list[dict]): A list of constraint slots to consider when calculating the run plan. Each dictionary contains:
                - "StartDateTime" (datetime.datetime): The start time of the constraint slot.
                - "EndDateTime" (datetime.datetime): The end time of the constraint slot.

        Returns:
            list[dict]: A list of selected slot dictionaries with added metadata:
        """
        selected_slots = []
        filled_mins = 0
        remaining_mins = remaining_required_mins

        if constraint_slots is None:
            constraint_slots = []

        for slot in sorted_slot_data:
            duration_mins = slot["Minutes"]
            price = slot["Price"]

            if price > max_priority_price:
                continue  # Too expensive even for priority hours

            # Check if slot qualifies under either normal or priority pricing
            qualifies_normal = price <= max_price
            qualifies_priority = price <= max_priority_price

            if not (qualifies_normal or qualifies_priority):
                continue

            # If constraint slots are provided, check if the current slot overlaps with any constraint slot
            if constraint_slots:
                slot_start = slot["StartDateTime"]
                slot_end = slot["EndDateTime"]
                overlaps_constraint = False

                for constraint in constraint_slots:
                    constraint_start = constraint["StartDateTime"]
                    constraint_end = constraint["EndDateTime"]

                    # Check for overlap
                    if slot_start < constraint_end and slot_end > constraint_start:
                        overlaps_constraint = True
                        break

                if not overlaps_constraint:
                    continue  # Slot does not overlap with any constraint slot

            # Create slot entry with metadata for consolidation
            slot_entry = {
                "Date": slot["Date"],
                "StartDateTime": slot["StartDateTime"],
                "EndDateTime": slot["EndDateTime"],
                "Minutes": duration_mins,
                "Price": price,
                "ForecastEnergyUsage": (hourly_energy_usage / 60) * duration_mins if hourly_energy_usage > 0 else 0.0,
                "EstimatedCost": (hourly_energy_usage / (60 * 1000)) * duration_mins * (price / 100) if hourly_energy_usage > 0 else 0.0,
                "SlotCount": 1,
                "_WeightedPriceMinutes": price * duration_mins
            }

            selected_slots.append(slot_entry)
            filled_mins += duration_mins
            remaining_mins -= duration_mins

            if remaining_mins <= 0:
                break

        return selected_slots

    def _consolidate_slots(self, slots: list[dict], slot_min_minutes: int, slot_gap_minutes: int) -> list[dict]:
        """Consolidate slots by merging based on gap and minimum slot constraints.

        Args:
            slots (list[dict]): A list of selected slot dictionaries.
            slot_min_minutes (int): The minimum duration for a slot to be considered valid.
            slot_gap_minutes (int): The maximum gap allowed between slots for merging.

        Returns:
            list[dict]: A list of consolidated slot dictionaries.
        """
        if not slots:
            return slots
        # Sort chronologically
        slots.sort(key=operator.itemgetter("Date", "StartDateTime"))

        # Step 1: Merge slots with gaps smaller than slot_gap_minutes
        merged_slots = self._merge_by_gap(slots, slot_gap_minutes)

        # Step 2: Handle slots shorter than slot_min_minutes
        final_slots = self._enforce_minimum_slot_length(merged_slots, slot_min_minutes)

        return final_slots

    def _merge_by_gap(self, slots: list[dict], slot_gap_minutes: int) -> list[dict]:  # noqa: PLR6301
        """Merge slots that have gaps smaller than slot_gap_minutes.

        Args:
            slots (list[dict]): A list of slot dictionaries.
            slot_gap_minutes (int): The maximum gap allowed between slots for merging.

        Returns:
            list[dict]: A list of merged slot dictionaries.
        """
        if not slots:
            return slots

        merged = []
        for slot in slots:
            if not merged:
                merged.append(slot)
                continue

            last_slot = merged[-1]
            last_end_dt = last_slot["EndDateTime"]
            curr_start_dt = slot["StartDateTime"]

            gap_minutes = (curr_start_dt - last_end_dt).total_seconds() / 60

            # Merge if:
            # 1. Slots are back-to-back (gap_minutes == 0), OR
            # 2. Gap is smaller than minimum required (when slot_gap_minutes > 0)
            should_merge = (gap_minutes == 0) or (slot_gap_minutes > 0 and 0 < gap_minutes < slot_gap_minutes)

            if should_merge:
                # Update last slot - extend to the end of current slot
                last_slot["EndDateTime"] = slot["EndDateTime"]

                # Calculate total duration using consistent date reference (last_slot's date)
                start_dt = last_slot["StartDateTime"]
                end_dt = slot["EndDateTime"]

                total_duration = int((end_dt - start_dt).total_seconds() / 60)
                last_slot["Minutes"] = total_duration

                # Aggregate metrics
                last_slot["_WeightedPriceMinutes"] += slot["_WeightedPriceMinutes"]
                last_slot["ForecastEnergyUsage"] += slot["ForecastEnergyUsage"]
                last_slot["EstimatedCost"] += slot["EstimatedCost"]
                last_slot["SlotCount"] += slot["SlotCount"]
            else:
                merged.append(slot)

        return merged

    def _enforce_minimum_slot_length(self, slots: list[dict], slot_min_minutes: int) -> list[dict]:
        """Handle slots that are shorter than minimum length.

        Args:
            slots (list[dict]): A list of slot dictionaries.
            slot_min_minutes (int): The minimum length of a final slot in minutes.

        Returns:
            list[dict]: A list of slot dictionaries with short slots merged or removed.
        """
        if not slots or slot_min_minutes <= 0:
            return slots

        result = []
        i = 0
        while i < len(slots):
            slot = slots[i]

            if slot["Minutes"] >= slot_min_minutes:
                result.append(slot)
                i += 1
                continue

            # Slot is too short - try to merge with next slot first
            if i + 1 < len(slots):
                next_slot = slots[i + 1]

                # Merge current slot with next slot
                start_dt = slot["StartDateTime"]
                end_dt = next_slot["EndDateTime"]

                merged_slot = {
                    "Date": slot["Date"],
                    "StartDateTime": start_dt,
                    "EndDateTime": end_dt,
                    "Minutes": int((end_dt - start_dt).total_seconds() / 60),
                    "_WeightedPriceMinutes": slot["_WeightedPriceMinutes"] + next_slot["_WeightedPriceMinutes"],
                    "ForecastEnergyUsage": slot["ForecastEnergyUsage"] + next_slot["ForecastEnergyUsage"],
                    "EstimatedCost": slot["EstimatedCost"] + next_slot["EstimatedCost"],
                    "SlotCount": slot["SlotCount"] + next_slot["SlotCount"]
                }

                result.append(merged_slot)
                i += 2  # Skip both slots

            # Try to merge with previous slot if no next slot available
            elif result:
                prev_slot = result[-1]
                end_dt = slot["EndDateTime"]

                # Extend previous slot
                prev_slot["EndDateTime"] = slot["EndDateTime"]
                prev_slot["Minutes"] = int((end_dt - prev_slot["StartDateTime"]).total_seconds() / 60)
                prev_slot["_WeightedPriceMinutes"] += slot["_WeightedPriceMinutes"]
                prev_slot["ForecastEnergyUsage"] += slot["ForecastEnergyUsage"]
                prev_slot["EstimatedCost"] += slot["EstimatedCost"]
                prev_slot["SlotCount"] += slot["SlotCount"]

                i += 1

            else:
                # Isolated short slot - remove it
                self.logger.log_message(f"Removing short slot ({slot['Minutes']} min) that cannot be merged", "debug")
                i += 1

        return result

    def _trim_to_required_hours(self, slots: list[dict], required_minutes: int) -> list[dict]:  # noqa: PLR6301
        """Trim slots to exactly meet required hours.

        Args:
            slots (list[dict]): A list of slot dictionaries.
            required_minutes (int): The exact number of minutes required.

        Returns:
            list[dict]: A list of slot dictionaries trimmed to the required minutes.
        """
        if not slots:
            return slots

        total_minutes = sum(slot["Minutes"] for slot in slots)

        if total_minutes <= required_minutes:
            return slots

        # Need to trim excess minutes from the last slot(s)
        excess_minutes = total_minutes - required_minutes

        # Work backwards through slots to trim excess
        for i in range(len(slots) - 1, -1, -1):
            slot = slots[i]

            if excess_minutes <= 0:
                break

            if slot["Minutes"] <= excess_minutes:
                # Remove entire slot
                excess_minutes -= slot["Minutes"]
                slots.pop(i)
            else:
                # Trim part of this slot
                start_dt = slot["StartDateTime"]
                new_end_dt = start_dt + dt.timedelta(minutes=slot["Minutes"] - excess_minutes)

                # Calculate the original price from weighted price minutes
                original_price = slot["_WeightedPriceMinutes"] / slot["Minutes"] if slot["Minutes"] > 0 else 0.0

                # Update slot
                slot["EndDateTime"] = new_end_dt
                slot["Minutes"] -= excess_minutes

                # Proportionally adjust energy and cost
                ratio = slot["Minutes"] / (slot["Minutes"] + excess_minutes)
                slot["ForecastEnergyUsage"] *= ratio
                slot["EstimatedCost"] *= ratio

                # Recalculate weighted price minutes with new duration
                slot["_WeightedPriceMinutes"] = original_price * slot["Minutes"]

                excess_minutes = 0

        return slots

    def _finalize_run_plan(self, run_plan: dict, slots: list[dict], required_mins: int, required_priority_mins: int) -> dict:  # noqa: PLR6301
        """Calculate final metrics and status for the run plan.

        Args:
            run_plan (dict): The run plan dictionary to finalize.
            slots (list[dict]): A list of slot dictionaries.
            required_mins (int): The total number of minutes to be included in the run plan.
            required_priority_mins (int): The minimum number of minutes that must be included in the run plan for it to be valid.

        Returns:
            dict: The finalized run plan dictionary.
        """
        if not slots:
            run_plan["Status"] = RunPlanStatus.FAILED
            run_plan["PlannedHours"] = 0.0
            run_plan["RemainingHours"] = 0.0
            return run_plan

        # Calculate final metrics
        total_minutes = 0
        future_minutes = 0
        total_weighted_price = 0.0
        total_energy_used = 0.0
        total_cost = 0.0

        now = DateHelper.now()
        for slot in slots:
            minutes = slot["Minutes"]
            total_minutes += minutes

            # Add to future minutes for the portion of the slot that is in the future
            if slot["EndDateTime"] > now:
                if slot["StartDateTime"] >= now:
                    future_minutes += minutes
                else:
                    future_minutes += int((slot["EndDateTime"] - now).total_seconds() / 60)

            total_energy_used += slot["ForecastEnergyUsage"]
            total_cost += slot["EstimatedCost"]
            total_weighted_price += slot["_WeightedPriceMinutes"]

            # Calculate weighted average price for this slot
            slot["Price"] = round(slot["_WeightedPriceMinutes"] / minutes if minutes > 0 else 0.0, 2)

            # Clean up internal fields
            del slot["_WeightedPriceMinutes"]

        run_plan["RunPlan"] = slots
        run_plan["PlannedHours"] = total_minutes / 60.0
        run_plan["RemainingHours"] = future_minutes / 60.0
        run_plan["ForecastAveragePrice"] = round(
            total_weighted_price / total_minutes if total_minutes > 0 else 0.0, 2
        )
        run_plan["ForecastEnergyUsage"] = total_energy_used
        run_plan["EstimatedCost"] = total_cost

        # Set status
        if total_minutes < required_priority_mins:
            run_plan["Status"] = RunPlanStatus.FAILED
        elif total_minutes >= required_mins:
            run_plan["Status"] = RunPlanStatus.READY
        else:
            run_plan["Status"] = RunPlanStatus.PARTIAL

        # Set timing fields
        if slots:
            run_plan["NextStartDateTime"] = slots[0]["StartDateTime"]
            run_plan["NextStopDateTime"] = slots[0]["EndDateTime"]

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
            current_time = DateHelper.now()
            remaining_required_mins = 24 * 60 - (current_time.hour * 60 + current_time.minute)
            # Round down to the nearest 5 minutes
            if remaining_required_mins % 5 != 0:
                remaining_required_mins -= 5 - (remaining_required_mins % 5)
        else:
            remaining_required_mins = required_hours * 60
        remaining_required_mins = max(0, remaining_required_mins)

        return int(remaining_required_mins)
