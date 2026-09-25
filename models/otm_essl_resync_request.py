# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class OtmEsslResyncRequest(models.Model):
    """A request to resync one employee's eSSL punches for a date range -
    created here in Odoo, picked up and processed by essl_bridge.py on
    its next normal poll cycle (the bridge already talks to Odoo every
    15 seconds; this just gives it something extra to check each time).

    Odoo itself has no direct access to the eTimeTrackLite SQL Server
    database (different machine/network), so this can't be done from
    Odoo alone - the bridge script is the only thing that can actually
    read the device's raw data. This model is the hand-off point between
    the two, in the SAME direction communication already flows (bridge
    reaches out to Odoo), so no inbound network access to your local
    machine is ever needed.
    """
    _name = 'otm.essl.resync.request'
    _description = 'ESSL Resync Request'

    _inherit = ['mail.thread', 'mail.activity.mixin']

    _order = 'create_date desc'

    name = fields.Char(compute='_compute_name', store=True)
    employee_id = fields.Many2one('hr.employee', required=True, tracking=True)
    device_id = fields.Char(related='employee_id.attendance_device_id', store=True, readonly=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)

    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], default='pending', required=True, tracking=True, copy=False)
    result_message = fields.Text(readonly=True, copy=False)

    requested_by = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    requested_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    processed_date = fields.Datetime(readonly=True, copy=False)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for request in self:
            if request.date_to < request.date_from:
                raise ValidationError(_('"To" date cannot be before "From" date.'))

    @api.constrains('employee_id')
    def _check_device_id(self):
        for request in self:
            if not request.employee_id.attendance_device_id:
                raise UserError(_(
                    '%s has no Biometric Device ID set - there is nothing for the bridge '
                    'script to resync for them.'
                ) % request.employee_id.name)

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_name(self):
        for request in self:
            if request.employee_id and request.date_from:
                request.name = '%s (%s - %s)' % (request.employee_id.name, request.date_from, request.date_to)
            else:
                request.name = _('New Resync Request')

    # --- Called by essl_bridge.py, not from the UI ---------------------------
    @api.model
    def get_pending_essl_resync_requests(self):
        """Polled by the bridge script every cycle. Returns just enough to
        act on - the bridge does the actual SQL Server query itself,
        Odoo only knows WHAT to ask for, not the raw punch data.
        """
        requests = self.sudo().search([('state', '=', 'pending')])
        return [{
            'id': request.id,
            'device_id': request.device_id,
            'date_from': fields.Date.to_string(request.date_from),
            'date_to': fields.Date.to_string(request.date_to),
        } for request in requests if request.device_id]

    @api.model
    def mark_essl_resync_request_done(self, request_id, state, message):
        request = self.sudo().browse(request_id)
        if request.exists():
            request.write({
                'state': state,
                'result_message': message,
                'processed_date': fields.Datetime.now(),
            })
        return True
