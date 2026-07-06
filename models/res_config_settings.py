# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    attendance_target_hours = fields.Float(
        related='company_id.attendance_target_hours',
        readonly=False,
        string='Default Required Working Hours',
    )
    attendance_office_start_time = fields.Float(
        related='company_id.attendance_office_start_time',
        readonly=False,
        string='Default Office Start Time',
    )
    essl_sync_secret = fields.Char(
        string='eSSL Sync Secret',
        config_parameter='attendance_live_counter.essl_sync_secret',
        help='Shared secret the eSSL/eTimeTrackLite bridge script must send '
             'with every punch. Set a long random value here and put the '
             'exact same value in the bridge script config.',
    )
