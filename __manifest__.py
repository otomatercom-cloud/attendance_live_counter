{
    'name': 'Live Attendance Counter',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Biometric-style live working-time counter for employee attendance',
    'description': """
Live Attendance Counter
========================
Adds a real-time, per-second working-time counter on top of Odoo's standard
Attendance app.

Features
--------
* Live "Worked Today" timer that ticks every second, entirely in the browser
  (no per-second database writes, no polling).
* Modern OWL 2 dashboard card: employee, status, check-in / check-out,
  live worked time, target hours, remaining time, overtime.
* Daily progress bar toward the configurable target working hours.
* Automatic status colors: Working / Target Completed / Overtime /
  High Overtime / Checked Out.
* Late-arrival and early-checkout detection against a configurable
  office start time and target hours (per company, overridable per employee).
* Reusable Attendance Timer OWL component, ready to be reused for future
  break/lunch tracking.
    """,
    'author': 'Otomater',
    'license': 'LGPL-3',
    'depends': ['hr_attendance', 'hr'],
    'data': [
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'views/attendance_dashboard_views.xml',
        'views/hr_attendance_backend_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'attendance_live_counter/static/src/css/attendance_dashboard.css',
            'attendance_live_counter/static/src/js/attendance_timer.js',
            'attendance_live_counter/static/src/xml/attendance_timer.xml',
            'attendance_live_counter/static/src/js/attendance_dashboard.js',
            'attendance_live_counter/static/src/xml/attendance_dashboard.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
