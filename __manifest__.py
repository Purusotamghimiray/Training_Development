{
    'name': 'Payslip Excel Report',
    'version': '1.0',
    'category': 'Human Resources',
    'summary': 'Export Payslips to Excel Format',
    'author': 'DrukSmart Private Limited',
    'depends': ['base','om_hr_payroll'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/payslip_excel_wizard_view.xml',
        'data/hr_payslip_excel_actions.xml',
    ],
    'installable': True,
    'application': False,
}
