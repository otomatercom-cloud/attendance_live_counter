# -*- coding: utf-8 -*-
import hmac
import logging
from datetime import datetime, time as dt_time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


def _to_iso_utc(value):
    """Format a naive UTC datetime (as stored by Odoo) as an ISO-8601
    string with an explicit 'Z' suffix, so the browser's Date() parser
    always interprets it as UTC regardless of the browser's own locale.
    """
    if not value:
        return False
    return fields.Datetime.to_string(value).replace(' ', 'T') + 'Z'


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # --- Configurable targets -------------------------------------------------
    # Each employee can override the company default. Falls back to the
    # company value (and finally a hard default) when left at 0.
    attendance_target_hours = fields.Float(
        string='Required Working Hours',
        help='Daily target working hours for this employee. Leave at 0 to '
             'use the company default.',
    )
    attendance_office_start_time = fields.Float(
        string='Office Start Time',
        help='Official start time for this employee, as a float hour '
             '(e.g. 9.5 = 09:30 AM). Leave at 0 to use the company default.',
    )
    attendance_device_id = fields.Char(
        string='Biometric Device ID',
        copy=False,
        help='The enrollment / user ID configured for this employee on the '
             'eSSL / ZKTeco biometric machine. Used to match incoming punches '
             'from the eTimeTrackLite bridge to this employee. Must be unique.',
    )

    _sql_constraints = [
        ('attendance_device_id_uniq', 'unique(attendance_device_id)',
         'This Biometric Device ID is already assigned to another employee.'),
    ]

    # --- Helpers ---------------------------------------------------------------
    def _attendance_target_hours(self):
        self.ensure_one()
        return self.attendance_target_hours or self.company_id.attendance_target_hours or 9.0

    def _attendance_office_start_time(self):
        self.ensure_one()
        return self.attendance_office_start_time or self.company_id.attendance_office_start_time or 9.5

    def _today_utc_range(self):
        """Return (start_utc, end_utc) naive datetimes bounding 'today'
        in the employee's own timezone, so attendance lookups line up
        with what the employee actually experiences as 'today'.
        """
        self.ensure_one()
        tz_name = self.tz or self.user_id.tz or 'UTC'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.utc
        now_local = pytz.utc.localize(datetime.utcnow()).astimezone(tz)
        start_local = tz.localize(datetime.combine(now_local.date(), dt_time.min))
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(pytz.utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.utc).replace(tzinfo=None)
        return start_utc, end_utc

    def _today_attendance(self):
        """Most relevant hr.attendance record for 'today': the currently
        open one if checked in, otherwise the most recently closed one.

        hr.attendance itself is readable by a plain employee for their own
        records (hr_attendance.group_hr_attendance_own_reader, implied for
        every internal user), so this search does not need sudo().
        """
        self.ensure_one()
        start_utc, end_utc = self._today_utc_range()
        return self.env['hr.attendance'].search([
            ('employee_id', '=', self.id),
            ('check_in', '>=', start_utc),
            ('check_in', '<', end_utc),
        ], order='check_in desc', limit=1)

    # --- Dashboard data (single RPC call, loaded once by the OWL widget) ------
    def get_attendance_dashboard_data(self):
        """Return everything the live counter widget needs to render and
        run its client-side timer. Called ONCE on load / after check-in
        / after check-out - never polled every second (see JS side).

        NOTE on sudo(): core fields such as ``attendance_state`` carry a
        field-level ``groups=`` restriction (officers / hr.group_hr_user
        only) in stock hr_attendance, so a plain employee cannot read even
        their OWN attendance_state without it. This method is only ever
        reached via get_my_attendance_dashboard_data(), which has already
        resolved `self` to exactly the calling user's own employee record -
        sudo() here cannot expose anyone else's data.
        """
        self.ensure_one()
        employee = self.sudo()
        attendance = self._today_attendance()
        return {
            'employee_id': self.id,
            'employee_name': employee.name,
            'state': employee.attendance_state or 'checked_out',
            'check_in': _to_iso_utc(attendance.check_in) if attendance else False,
            'check_out': _to_iso_utc(attendance.check_out) if attendance else False,
            'server_time': _to_iso_utc(fields.Datetime.now()),
            'target_hours': self._attendance_target_hours(),
            'office_start_time': self._attendance_office_start_time(),
            'is_late': bool(attendance.is_late) if attendance else False,
            'late_duration': attendance.late_duration if attendance else 0.0,
            'is_left_early': bool(attendance.is_left_early) if attendance else False,
            'left_early_duration': attendance.left_early_duration if attendance else 0.0,
            'worked_hours_today': attendance.worked_hours if attendance else 0.0,
        }

    def action_attendance_check_in(self):
        self.ensure_one()
        employee = self.sudo()
        if employee.attendance_state == 'checked_in':
            raise UserError(_('%s is already checked in.') % self.name)
        # Delegate to the core, already-tested check-in/check-out toggle
        # (hr_attendance.hr.employee._attendance_action_change) instead of
        # duplicating hr.attendance create/write logic here - this is the
        # exact same method the Attendance kiosk uses. sudo() is required
        # because a plain employee has read-only access to hr.attendance
        # (see hr_attendance_security.xml: group_hr_attendance_own_reader),
        # scoped tightly to this single, already-resolved employee record.
        employee._attendance_action_change()
        return self.get_attendance_dashboard_data()

    def action_attendance_check_out(self):
        self.ensure_one()
        employee = self.sudo()
        if employee.attendance_state != 'checked_in':
            raise UserError(_('%s is not currently checked in.') % self.name)
        employee._attendance_action_change()
        return self.get_attendance_dashboard_data()

    # --- "My attendance" convenience wrappers ----------------------------------
    # The dashboard widget calls these on the model (no active id needed):
    # it always resolves to the current logged-in user's own employee.
    # @api.model is REQUIRED here: the JS side calls these with an empty
    # args list (this.orm.call("hr.employee", "get_my_attendance_dashboard_data", [])).
    # Without @api.model, Odoo's call_kw does `ids, args = args[0], args[1:]`
    # to build the recordset `self` - with args=[] that raises exactly
    # "list index out of range". @api.model methods skip that ids-extraction
    # step entirely and just receive `self = env['hr.employee']`.
    @api.model
    def get_my_attendance_dashboard_data(self):
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(_('No employee record is linked to your user account.'))
        return employee.get_attendance_dashboard_data()

    @api.model
    def action_my_attendance_check_in(self):
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(_('No employee record is linked to your user account.'))
        return employee.action_attendance_check_in()

    @api.model
    def action_my_attendance_check_out(self):
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(_('No employee record is linked to your user account.'))
        return employee.action_attendance_check_out()

    # --- eSSL / biometric device sync -------------------------------------
    # Called remotely (XML-RPC) by the eTimeTrackLite bridge script running
    # on the machine next to the punching device - see essl_bridge.py.
    # This is the ONLY entry point that lets an external, non-interactive
    # script create attendance records, so it is deliberately guarded by a
    # shared secret (Settings > Attendances > Live Attendance Counter) on
    # top of the normal Odoo login the bridge already needs.
    def _check_essl_sync_secret(self, secret):
        configured = self.env['ir.config_parameter'].sudo().get_param(
            'attendance_live_counter.essl_sync_secret') or ''
        if not configured:
            raise AccessError(_(
                'The eSSL sync secret is not configured. Set one in '
                'Settings > Attendances > Live Attendance Counter before '
                'syncing punches.'
            ))
        if not secret or not hmac.compare_digest(str(secret), configured):
            raise AccessError(_('Invalid eSSL sync secret.'))

    @api.model
    def sync_essl_punch(self, secret, device_id, punch_datetime, device_ref=None):
        """Record one raw punch coming from the biometric machine.

        :param secret: shared secret, must match the configured
            ``attendance_live_counter.essl_sync_secret`` system parameter.
        :param device_id: the machine's enrollment/user ID for the
            employee (matched against hr.employee.attendance_device_id).
        :param punch_datetime: the punch's actual timestamp, as a UTC
            string 'YYYY-MM-DD HH:MM:SS' (the bridge script is responsible
            for converting the device's local time to UTC before calling).
        :param device_ref: optional unique fingerprint for this exact punch
            event (e.g. "<device_id>|<raw checktime>"), used to make
            re-sending the same punch a safe no-op.
        :return: dict with at least a 'status' key
            ('ok' / 'duplicate' / 'error').
        """
        self._check_essl_sync_secret(secret)

        employee = self.sudo().search([('attendance_device_id', '=', device_id)], limit=1)
        if not employee:
            _logger.warning(
                'attendance_live_counter: punch received for unknown device_id %r', device_id)
            return {'status': 'error', 'message': 'No employee mapped to device_id %r' % device_id}

        try:
            punch_dt = fields.Datetime.from_string(punch_datetime)
        except Exception:
            return {'status': 'error', 'message': 'Invalid datetime: %r' % punch_datetime}
        if not punch_dt:
            return {'status': 'error', 'message': 'Invalid datetime: %r' % punch_datetime}

        return employee._record_device_punch(punch_dt, device_ref=device_ref)

    def _record_device_punch(self, punch_dt, device_ref=None):
        """Toggle check-in/check-out for a single raw punch at an exact
        timestamp. Kept separate from the interactive
        action_attendance_check_in/out (which always use "now") because a
        synced punch's timestamp is the actual punch time, possibly a few
        seconds or minutes in the past by the time the bridge relays it.
        """
        self.ensure_one()
        Attendance = self.env['hr.attendance'].sudo()

        if device_ref:
            existing = Attendance.search([
                '|', ('device_ref_in', '=', device_ref), ('device_ref_out', '=', device_ref),
            ], limit=1)
            if existing:
                return {'status': 'duplicate', 'attendance_id': existing.id}

        open_attendance = Attendance.search([
            ('employee_id', '=', self.id),
            ('check_out', '=', False),
        ], order='check_in desc', limit=1)

        if open_attendance and punch_dt > open_attendance.check_in:
            open_attendance.write({'check_out': punch_dt, 'device_ref_out': device_ref})
            attendance, state = open_attendance, 'checked_out'
        else:
            attendance = Attendance.create({
                'employee_id': self.id,
                'check_in': punch_dt,
                'device_ref_in': device_ref,
            })
            state = 'checked_in'

        # Push a live notification to the employee's own browser tab(s) so
        # the dashboard reloads and the counter starts automatically -
        # no polling, no manual refresh, no Check In click needed.
        if self.user_id:
            self.user_id._bus_send('attendance_live_counter/punch', {
                'employee_id': self.id,
                'state': state,
            })

        return {'status': 'ok', 'attendance_id': attendance.id, 'state': state}
