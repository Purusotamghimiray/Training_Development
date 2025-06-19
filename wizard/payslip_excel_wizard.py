import base64
import io
import xlwt
from odoo import models, fields
from odoo.exceptions import ValidationError
from datetime import datetime # Import datetime for formatting

class PayslipExcelWizard(models.TransientModel):
    _name = 'payslip.excel.wizard'
    # ... (fields definition remains the same) ...
    _description = 'Payslip Excel Export Wizard'

    date_start = fields.Date(string="Date From", required=True, default=fields.Date.context_today)
    date_end = fields.Date(string="Date To", required=True, default=fields.Date.context_today)
    payslip_ids = fields.Many2many('hr.payslip', string="Payslips (Optional)")
    excel_file = fields.Binary('Download Excel File', readonly=True)
    filename = fields.Char('File Name', readonly=True)


    def action_export_excel(self):
        # Search for payslips within the date range and in 'done' state if specific payslips are not selected
        if self.payslip_ids:
             payslips = self.payslip_ids.filtered(lambda p: p.state == 'done')
             if not payslips:
                  raise ValidationError("None of the selected payslips are in the 'Done' state.")
        else:
            payslips = self.env['hr.payslip'].search([
                ('date_from', '>=', self.date_start),
                ('date_to', '<=', self.date_end),
                ('state', '=', 'done')
            ])

        if not payslips:
            raise ValidationError("No validated payslips found for the selected period.")

        # Collect unique code, name, and category from all selected payslip lines
        code_name_map = {}
        for payslip in payslips:
            for line in payslip.line_ids:
                if line.code not in code_name_map:
                    # Ensure category has a code, default to 'OTH' if not
                    category_code = line.category_id.code or 'OTH'
                    code_name_map[line.code] = {
                        'name': line.name,
                        'category': category_code
                    }

        # Helper function to filter codes by category
        def filter_codes_by_category(cat_code):
            return sorted([code for code, val in code_name_map.items() if val.get('category') == cat_code])

        # Define standard category codes
        std_categories = ['BASIC', 'ALW', 'GROSS', 'DED', 'NET']

        # Get codes for standard categories
        basic_codes = filter_codes_by_category('BASIC')
        allowance_codes = filter_codes_by_category('ALW')
        gross_codes = filter_codes_by_category('GROSS')
        deduction_codes = filter_codes_by_category('DED')
        net_codes = filter_codes_by_category('NET')

        # Get any other codes not in the standard categories
        other_codes = sorted([
            code for code, val in code_name_map.items()
            if val.get('category') not in std_categories
        ])

        # Define the final order of codes for columns
        ordered_codes = basic_codes + allowance_codes + gross_codes + deduction_codes + net_codes + other_codes

        # Prepare workbook and sheet
        wb = xlwt.Workbook(encoding='utf-8') # Specify encoding for broader character support
        sheet = wb.add_sheet('Payslip Summary')

        # --- Style Definitions ---

        # General Styles
        title_style = xlwt.easyxf('font: bold on, height 240; align: horiz center')
        subtitle_style = xlwt.easyxf('font: bold on; align: horiz center')
        header_style = xlwt.easyxf(
            'font: bold on, height 200; pattern: pattern solid, fore_colour gray25; '
            'align: horiz center, vert center, wrap on; '
            'borders: left thin, right thin, top thin, bottom thin'
        )
        total_label_style = xlwt.easyxf(
            'font: bold on; align: horiz right, vert center; '
            'borders: left thin, right thin, top thin, bottom thin'
        )

        # Base styles for data cells (alternating rows)
        borders_str = 'borders: left thin, right thin, top thin, bottom thin;'
        align_left_str = 'align: horiz left, vert center;'
        align_right_str = 'align: horiz right, vert center;'
        pattern_alt_row_str = 'pattern: pattern solid, fore_colour gray25;' # Gray background for even data rows

        normal_style_odd = xlwt.easyxf(f'{borders_str} {align_left_str}')
        normal_style_even = xlwt.easyxf(f'{borders_str} {align_left_str} {pattern_alt_row_str}')
        normal_right_style_odd = xlwt.easyxf(f'{borders_str} {align_right_str}')
        normal_right_style_even = xlwt.easyxf(f'{borders_str} {align_right_str} {pattern_alt_row_str}')

        # Define Base Style STRINGS for Numeric Categories
        num_format = '#,##0.00' # Define number format once
        category_base_str = f'{borders_str} {align_right_str}' # Base for numeric cells

        # Specific patterns/fonts for each category string
        basic_style_str = f'pattern: pattern solid, fore_colour ice_blue; {category_base_str}'
        allowance_style_str = f'pattern: pattern solid, fore_colour light_turquoise; {category_base_str}'
        gross_style_str = f'pattern: pattern solid, fore_colour light_green; {category_base_str}'
        deduction_style_str = f'pattern: pattern solid, fore_colour light_yellow; {category_base_str}'
        net_style_regular_str = f'pattern: pattern solid, fore_colour coral; {category_base_str}; font: bold on' # Style for NET in data rows
        other_style_str = category_base_str # Style for uncategorized or 'OTH'

        # Create Actual XFStyle Objects using easyxf for CATEGORY cells in data rows
        style_basic = xlwt.easyxf(basic_style_str, num_format_str=num_format)
        style_allowance = xlwt.easyxf(allowance_style_str, num_format_str=num_format)
        style_gross = xlwt.easyxf(gross_style_str, num_format_str=num_format)
        style_deduction = xlwt.easyxf(deduction_style_str, num_format_str=num_format)
        style_net_regular = xlwt.easyxf(net_style_regular_str, num_format_str=num_format) # For data rows
        style_other = xlwt.easyxf(other_style_str, num_format_str=num_format)

        # Create Actual XFStyle Objects for TOTAL ROW cells
        # Style for the highlighted NET total cell(s)
        style_net_total_highlight = xlwt.easyxf(
            f'pattern: pattern solid, fore_colour lime; {category_base_str}; font: bold on;', # Lime background
            num_format_str=num_format
        )
        # Style for EMPTY cells in the total row (maintains borders and bold font)
        total_empty_style = xlwt.easyxf(f'{borders_str} font: bold on; align: horiz right, vert center;')


        # --- Map codes to styles ---
        # Map codes to styles for DATA rows
        code_style_map = {}
        for code in ordered_codes:
            category = code_name_map.get(code, {}).get('category', 'OTH')
            if category == 'BASIC':
                code_style_map[code] = style_basic
            elif category == 'ALW':
                code_style_map[code] = style_allowance
            elif category == 'GROSS':
                code_style_map[code] = style_gross
            elif category == 'DED':
                code_style_map[code] = style_deduction
            elif category == 'NET':
                code_style_map[code] = style_net_regular # Use regular NET style for data rows
            else: # OTH or uncategorized
                code_style_map[code] = style_other

        # --- Write Titles ---
        title_col_span = len(ordered_codes) + 2 # S.No, Name, Desig + all codes
        sheet.write_merge(0, 0, 0, title_col_span, 'Payslip Summary Report', title_style)
        # Format dates nicely for subtitle
        date_from_str = self.date_start.strftime('%d-%b-%Y') if self.date_start else 'N/A'
        date_to_str = self.date_end.strftime('%d-%b-%Y') if self.date_end else 'N/A'
        sheet.write_merge(1, 1, 0, title_col_span, f"Period: {date_from_str} to {date_to_str}", subtitle_style)

        # --- Freeze pane and set header ---
        sheet.set_panes_frozen(True)
        sheet.set_horz_split_pos(4) # Freeze rows above row index 4
        sheet.set_vert_split_pos(3) # Freeze columns left of col index 3

        # --- Set headers ---
        headers = ['S.No', 'Employee Name', 'Designation']
        col_widths = [1500, 6000, 5000]
        for code in ordered_codes:
            name = code_name_map.get(code, {}).get('name', code)
            label = f"{name}\n({code})"
            headers.append(label)
            col_widths.append(4000)

        header_row_index = 3
        sheet.row(header_row_index).height_mismatch = True
        sheet.row(header_row_index).height = 2 * 256
        for col, header in enumerate(headers):
            sheet.write(header_row_index, col, header, header_style)
            try:
                sheet.col(col).width = col_widths[col]
            except IndexError:
                 sheet.col(col).width = 4000

        # --- Initialize Totals (Only for NET codes) ---
        # Initialize all to 0, but will only accumulate for NET
        column_totals = {code: 0.0 for code in ordered_codes}

        # --- Populate data rows ---
        current_row_index = 4
        for idx, payslip in enumerate(payslips):
            emp = payslip.employee_id
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', emp.id),
                ('state', 'in', ['open', 'close']),
                ('date_start', '<=', payslip.date_to),
                '|', ('date_end', '=', False), ('date_end', '>=', payslip.date_from)
            ], order='date_start desc', limit=1)

            is_odd_row = (idx + 1) % 2 != 0
            current_normal_style = normal_style_odd if is_odd_row else normal_style_even
            current_normal_right_style = normal_right_style_odd if is_odd_row else normal_right_style_even

            col = 0
            sheet.write(current_row_index, col, idx + 1, current_normal_right_style)
            col += 1
            sheet.write(current_row_index, col, emp.name or '', current_normal_style)
            col += 1
            sheet.write(current_row_index, col, contract.job_id.name if contract and contract.job_id else '', current_normal_style)
            col += 1

            line_dict = {line.code: line.total for line in payslip.line_ids}
            for code in ordered_codes:
                value = line_dict.get(code, 0.0)
                category = code_name_map.get(code, {}).get('category', 'OTH')

                # --- Accumulate total ONLY if category is NET ---
                if category == 'NET':
                    column_totals[code] += value

                # Get style for data row cell
                style = code_style_map.get(code, style_other)

                # Write numeric value with appropriate style
                sheet.write(current_row_index, col, value, style)
                col += 1

            current_row_index += 1

        # --- Write Total Row ---
        total_row_index = current_row_index
        col = 0
        sheet.write_merge(total_row_index, total_row_index, 0, 2, 'Grand Total (NET)', total_label_style) # Adjusted label
        col = 3

        for code in ordered_codes:
            category = code_name_map.get(code, {}).get('category', 'OTH')

            # Write total ONLY if category is NET
            if category == 'NET':
                total_value = column_totals[code]
                # Use the special highlighted style for NET totals
                sheet.write(total_row_index, col, total_value, style_net_total_highlight)
            else:
                # Write an empty string with the basic total style for non-NET columns
                sheet.write(total_row_index, col, '', total_empty_style)

            col += 1

        # --- Save file ---
        fp = io.BytesIO()
        wb.save(fp)
        fp.seek(0)

        excel_b64 = base64.encodebytes(fp.read())
        fp.close()

        filename = f'Payslip_Summary_{self.date_start.strftime("%Y%m%d")}_{self.date_end.strftime("%Y%m%d")}.xls'
        self.write({
            'excel_file': excel_b64,
            'filename': filename
        })

        # Return action to download the file directly
        return {
            'name': 'Payslip Summary Export',
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=excel_file&filename_field=filename&download=true',
            'target': 'self',
        }