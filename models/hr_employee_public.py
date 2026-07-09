# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployeePublic(models.Model):
    """hr.employee.public is a read-only SQL VIEW (see hr/models/
    hr_employee_public.py's init() method) that Odoo dynamically builds
    from whatever fields are declared on this model - used for avatar
    hover-cards, Manager field previews, and other privacy-restricted
    "public profile" contexts. A field existing on hr.employee alone is
    NOT enough for it to show up there; it has to be re-declared here too,
    or reading it through the public-profile model raises
    "not available for employee public profiles".
    """
    _inherit = 'hr.employee.public'

    attendance_target_hours = fields.Float(readonly=True)
    attendance_office_start_time = fields.Float(readonly=True)
    attendance_device_id = fields.Char(readonly=True)
