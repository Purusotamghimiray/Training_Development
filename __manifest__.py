{
    'name': 'Leave Excel Report',
    'version': '16.0.1.0.0',
    'category': 'Human Resources/Time Off',
    'summary': 'Generate detailed Excel reports for employee leaves',
    'description': """
        This module adds an Excel report generation feature for employee leaves.
        - Generates detailed leave reports in Excel format
        - Shows allocation, utilization, and balance for different leave types
        - Accessible from Time Off reporting menu
    """,
    'author': 'DrukSmart Private Limited',
    'website': 'https://druk-smart.com/',
    'depends': ['hr_holidays'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/leave_report_wizard_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}