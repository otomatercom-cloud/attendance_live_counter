/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { AttendanceTimer, formatHms } from "./attendance_timer";

/** Format a millisecond duration as "6h 10m" (used by the progress bar label). */
function formatHm(ms) {
    const totalMinutes = Math.round(Math.max(0, ms) / 60000);
    const h = Math.floor(totalMinutes / 60);
    const m = totalMinutes % 60;
    return `${h}h ${m}m`;
}

const MS_PER_HOUR = 3600 * 1000;

/**
 * AttendanceDashboard
 * =====================
 * Client action ("ir.actions.client") registered under tag
 * "attendance_live_counter.dashboard".
 *
 * Loads the current user's attendance data with exactly ONE RPC call
 * on mount (and one more after every Check In / Check Out click).
 * Every second in between is pure client-side math (Date.now()), no
 * server round trip - see Rule 11 in the spec / ODOO19_RULES.md
 * performance guidance.
 */
export class AttendanceDashboard extends Component {
    static template = "attendance_live_counter.Dashboard";
    static components = { AttendanceTimer };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.busService = useService("bus_service");

        this.state = useState({
            loading: true,
            actionPending: false,
            error: null,
            data: null,
            clockNow: Date.now(),
        });
        this.serverOffsetMs = 0;
        this.clockIntervalId = null;

        onWillStart(() => this._loadData());

        this.clockIntervalId = setInterval(() => {
            this.state.clockNow = Date.now();
        }, 1000);

        // Every logged-in user's browser is automatically subscribed to
        // their own res.partner bus channel by Odoo's websocket layer
        // (ir_websocket._build_bus_channel_list) - no addChannel() call
        // needed here. sync_essl_punch() on the server sends to
        // employee.user_id, i.e. this exact channel, the instant a
        // biometric punch is synced. This is push, not polling: the
        // dashboard does nothing until the server tells it something
        // changed, then does exactly one RPC to refresh.
        this._onPunchNotification = this._onPunchNotification.bind(this);
        this.busService.subscribe("attendance_live_counter/punch", this._onPunchNotification);

        onWillUnmount(() => {
            if (this.clockIntervalId) {
                clearInterval(this.clockIntervalId);
                this.clockIntervalId = null;
            }
            this.busService.unsubscribe("attendance_live_counter/punch", this._onPunchNotification);
        });
    }

    async _onPunchNotification(payload) {
        if (this.state.data && payload && payload.employee_id !== this.state.data.employee_id) {
            return;
        }
        await this._loadData();
        if (this.state.data) {
            const message = this.state.data.state === "checked_in"
                ? "Punch received - checked in automatically."
                : "Punch received - checked out automatically.";
            this.notification.add(message, { type: "success" });
        }
    }

    async _loadData() {
        try {
            const data = await this.orm.call("hr.employee", "get_my_attendance_dashboard_data", []);
            this._applyData(data);
        } catch (error) {
            this.state.error = (error && error.data && error.data.message) || error.message || "Unable to load attendance data.";
        } finally {
            this.state.loading = false;
        }
    }

    _applyData(data) {
        this.state.data = data;
        this.state.error = null;
        this.serverOffsetMs = data.server_time ? new Date(data.server_time).getTime() - Date.now() : 0;
    }

    async onCheckIn() {
        await this._runAction("action_my_attendance_check_in");
    }

    async onCheckOut() {
        await this._runAction("action_my_attendance_check_out");
    }

    async _runAction(methodName) {
        if (this.state.actionPending) {
            return;
        }
        this.state.actionPending = true;
        try {
            const data = await this.orm.call("hr.employee", methodName, []);
            this._applyData(data);
        } catch (error) {
            const message = (error && error.data && error.data.message) || error.message || "Action failed.";
            this.notification.add(message, { type: "danger" });
        } finally {
            this.state.actionPending = false;
        }
    }

    // --- Live, purely client-side calculations -------------------------------

    get elapsedMs() {
        const data = this.state.data;
        if (!data || !data.check_in) {
            return 0;
        }
        const checkInMs = new Date(data.check_in).getTime();
        let endMs;
        if (data.state === "checked_out" && data.check_out) {
            endMs = new Date(data.check_out).getTime();
        } else {
            endMs = this.state.clockNow + this.serverOffsetMs;
        }
        return Math.max(0, endMs - checkInMs);
    }

    get targetMs() {
        const hours = (this.state.data && this.state.data.target_hours) || 9.0;
        return hours * MS_PER_HOUR;
    }

    get remainingMs() {
        return Math.max(0, this.targetMs - this.elapsedMs);
    }

    get overtimeMs() {
        return Math.max(0, this.elapsedMs - this.targetMs);
    }

    get progressPct() {
        if (!this.targetMs) {
            return 0;
        }
        return Math.min(100, (this.elapsedMs / this.targetMs) * 100);
    }

    get progressPctLabel() {
        return `${Math.round(this.progressPct)}%`;
    }

    get statusColor() {
        const data = this.state.data;
        if (!data || data.state === "checked_out") {
            return "grey";
        }
        const overtimeHours = this.overtimeMs / MS_PER_HOUR;
        if (overtimeHours > 2) {
            return "red";
        }
        if (overtimeHours > 0) {
            return "orange";
        }
        if (this.elapsedMs >= this.targetMs) {
            return "green";
        }
        return "blue";
    }

    get statusLabel() {
        const data = this.state.data;
        if (!data) {
            return "";
        }
        if (data.state === "checked_out") {
            return data.check_out ? "Checked Out" : "Not Checked In";
        }
        switch (this.statusColor) {
            case "red":
                return "High Overtime";
            case "orange":
                return "Overtime";
            case "green":
                return "Target Completed";
            default:
                return "Working";
        }
    }

    get isCheckedIn() {
        return !!(this.state.data && this.state.data.state === "checked_in");
    }

    get progressLabel() {
        return `${formatHm(this.elapsedMs)} / ${formatHm(this.targetMs)}`;
    }

    get remainingLabel() {
        return this.remainingMs > 0 ? formatHms(this.remainingMs) : "00:00:00";
    }

    get overtimeLabel() {
        return formatHms(this.overtimeMs);
    }

    get currentTimeLabel() {
        return new Date(this.state.clockNow).toLocaleTimeString();
    }

    get checkInLabel() {
        const data = this.state.data;
        return data && data.check_in ? new Date(data.check_in).toLocaleTimeString() : "--:--:--";
    }

    get checkOutLabel() {
        const data = this.state.data;
        return data && data.check_out ? new Date(data.check_out).toLocaleTimeString() : "--:--:--";
    }

    get lateLabel() {
        const data = this.state.data;
        if (!data || !data.is_late) {
            return null;
        }
        return formatHms(data.late_duration * MS_PER_HOUR);
    }

    get leftEarlyLabel() {
        const data = this.state.data;
        if (!data || !data.is_left_early || data.state !== "checked_out") {
            return null;
        }
        return formatHms(data.left_early_duration * MS_PER_HOUR);
    }

    get targetHoursLabel() {
        const data = this.state.data;
        return data ? `${data.target_hours}h` : "--";
    }
}

registry.category("actions").add("attendance_live_counter.dashboard", AttendanceDashboard);
