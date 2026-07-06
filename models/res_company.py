# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    """Company-wide defaults for the Live Attendance Counter.

    These act only as DEFAULTS. Each employee can override both values
    on their own record (see hr_employee.py) - this satisfies the
    "Required Working Hours (Configurable)" requirement at both levels.
    """
    _inherit = 'res.company'

    attendance_target_hours = fields.Float(
        string='Default Required Working Hours',
        default=9.0,
        help='Default daily target working hours used by the Live '
             'Attendance Counter dashboard, unless overridden on the '
             'employee record.',
    )
    attendance_office_start_time = fields.Float(
        string='Default Office Start Time',
        default=9.5,
        help='Official office start time, expressed as a float hour '
             '(e.g. 9.5 = 09:30 AM). Used to detect late arrivals.',
    )
    attendance_allow_manual_checkin = fields.Boolean(
        string='Allow Manual Check In/Out',
        default=True,
        help='When disabled, employees can no longer Check In/Check Out '
             'themselves from the Live Attendance dashboard - only punches '
             'from the biometric device (or manual entry by an Attendance '
             'Officer/Manager) are accepted. Use this once biometric sync is '
             'reliable, to prevent self-service misuse.',
    )
