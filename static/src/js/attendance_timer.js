/** @odoo-module **/

import { Component, onWillUnmount, onWillUpdateProps, useState } from "@odoo/owl";

/**
 * Format a millisecond duration as HH:MM:SS.
 * Kept as a plain function (not a QWeb-visible global) - QWeb expressions
 * cannot call bare JS globals, only component properties/methods, so this
 * is only ever used from JS and exposed to the template via a getter.
 */
export function formatHms(ms) {
    const totalSeconds = Math.floor(Math.max(0, ms) / 1000);
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = totalSeconds % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

/**
 * AttendanceTimer
 * ================
 * Reusable, self-contained "biometric style" live timer.
 *
 * - Starts its own setInterval automatically as soon as it receives
 *   state="checked_in" + a check-in timestamp.
 * - Stops (and clears the interval) the instant state="checked_out".
 * - Destroys the interval on unmount - no leaks.
 * - NEVER writes to the database and NEVER polls the server: it only
 *   reads Date.now(), corrected by a server-time offset supplied once
 *   by the parent, so the displayed value stays accurate even if the
 *   employee's local clock is wrong.
 *
 * Designed to be reused as-is for future break/lunch timers: just feed
 * it a different pair of start/state values.
 */
export class AttendanceTimer extends Component {
    static template = "attendance_live_counter.AttendanceTimer";
    static props = {
        checkIn: { type: [String, Boolean] },
        checkOut: { type: [String, Boolean] },
        state: { type: String },
        serverOffsetMs: { type: Number, optional: true },
        size: { type: String, optional: true }, // "lg" | "md"
    };
    static defaultProps = {
        serverOffsetMs: 0,
        size: "lg",
    };

    setup() {
        this.timerState = useState({ elapsedMs: this._computeElapsed(this.props) });
        this.intervalId = null;
        this._syncInterval(this.props);

        onWillUpdateProps((nextProps) => {
            this.timerState.elapsedMs = this._computeElapsed(nextProps);
            this._syncInterval(nextProps);
        });

        onWillUnmount(() => this._clearInterval());
    }

    _computeElapsed(props) {
        if (!props.checkIn) {
            return 0;
        }
        const checkInMs = new Date(props.checkIn).getTime();
        let endMs;
        if (props.state === "checked_out" && props.checkOut) {
            endMs = new Date(props.checkOut).getTime();
        } else {
            endMs = Date.now() + (props.serverOffsetMs || 0);
        }
        return Math.max(0, endMs - checkInMs);
    }

    _syncInterval(props) {
        const shouldRun = props.state === "checked_in" && !!props.checkIn;
        if (shouldRun && !this.intervalId) {
            this.intervalId = setInterval(() => {
                this.timerState.elapsedMs = this._computeElapsed(this.props);
            }, 1000);
        } else if (!shouldRun && this.intervalId) {
            this._clearInterval();
        }
    }

    _clearInterval() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }

    get formatted() {
        return formatHms(this.timerState.elapsedMs);
    }
}
