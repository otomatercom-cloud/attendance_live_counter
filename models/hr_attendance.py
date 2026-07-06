# -*- coding: utf-8 -*-
import pytz

from odoo import api, fields, models


class HrAttendance(models.Model):
    """Extends hr.attendance with the two "once-off" computations the
    live counter needs: how late the employee arrived, and (once
    checked out) whether they left before hitting their target hours.

    These are computed and STORED on write of check_in / check_out only -
    they are NOT recomputed every second. The second-by-second ticking
    display is handled entirely in the browser (see static/src/js), which
    keeps the database write-free while the employee is working.
    """
    _inherit = 'hr.attendance'

    is_late = fields.Boolean(
        string='Late Arrival',
        compute='_compute_late_arrival',
        store=True,
        help='True if check-in happened after the employee/company office start time.',
    )
    late_duration = fields.Float(
        string='Late By (Hours)',
        compute='_compute_late_arrival',
        store=True,
    )
    is_left_early = fields.Boolean(
        string='Left Early',
        compute='_compute_left_early',
        store=True,
        help='True if the employee checked out before reaching their target working hours.',
    )
    left_early_duration = fields.Float(
        string='Left Early By (Hours)',
        compute='_compute_left_early',
        store=True,
    )

    # --- Biometric device punch tracking ---------------------------------
    # Two separate fields because one hr.attendance record spans TWO raw
    # punches (the check-in and the check-out). Storing a single combined
    # "device_ref" would lose the check-in's fingerprint the moment the
    # check-out is written, defeating de-duplication for re-sent punches.
    # NULLs don't collide under a Postgres unique constraint, so manual /
    # kiosk-created records (which leave these blank) are unaffected.
    device_ref_in = fields.Char(
        string='Check-In Device Reference', copy=False, index=True,
        help='Unique fingerprint of the biometric check-in punch that created '
             'this record, used to prevent duplicate imports.',
    )
    device_ref_out = fields.Char(
        string='Check-Out Device Reference', copy=False, index=True,
        help='Unique fingerprint of the biometric check-out punch that closed '
             'this record, used to prevent duplicate imports.',
    )

    _sql_constraints = [
        ('device_ref_in_uniq', 'unique(device_ref_in)',
         'This check-in punch has already been synced (duplicate device reference).'),
        ('device_ref_out_uniq', 'unique(device_ref_out)',
         'This check-out punch has already been synced (duplicate device reference).'),
    ]

    @api.depends('check_in', 'employee_id')
    def _compute_late_arrival(self):
        for attendance in self:
            is_late = False
            late_duration = 0.0
            if attendance.check_in and attendance.employee_id:
                office_start = attendance.employee_id._attendance_office_start_time()
                tz_name = attendance.employee_id.tz or attendance.employee_id.user_id.tz or 'UTC'
                try:
                    tz = pytz.timezone(tz_name)
                except pytz.UnknownTimeZoneError:
                    tz = pytz.utc
                local_check_in = pytz.utc.localize(attendance.check_in).astimezone(tz)
                check_in_hour = local_check_in.hour + local_check_in.minute / 60.0 + local_check_in.second / 3600.0
                if check_in_hour > office_start:
                    is_late = True
                    late_duration = check_in_hour - office_start
            attendance.is_late = is_late
            attendance.late_duration = late_duration

    @api.depends('check_out', 'worked_hours', 'employee_id')
    def _compute_left_early(self):
        for attendance in self:
            left_early = False
            left_early_duration = 0.0
            if attendance.check_out and attendance.employee_id:
                target_hours = attendance.employee_id._attendance_target_hours()
                if attendance.worked_hours < target_hours:
                    left_early = True
                    left_early_duration = target_hours - attendance.worked_hours
            attendance.is_left_early = left_early
            attendance.left_early_duration = left_early_duration
