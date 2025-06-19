# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import xlsxwriter
import base64
from io import BytesIO
from datetime import datetime
# Import utility for column conversion
from xlsxwriter.utility import xl_col_to_name
# Import Odoo's logger
import logging
_logger = logging.getLogger(__name__) # Get logger instance

class LeaveReportWizard(models.TransientModel):
    _name = 'leave.report.wizard'
    _description = 'Leave Report Wizard'

    date_from = fields.Date(string='Date From', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Date To', required=True, default=fields.Date.today)
    excel_file = fields.Binary('Excel Report', readonly=True)
    file_name = fields.Char('File Name', readonly=True)

    def _get_leave_data(self, employee, leave_type, date_from, date_to):
        """
        Calculates leave allocation, utilization, and balance for a specific
        employee and leave type within a given date range.
        NOTE: Returns 'utilized' key, header displays 'Leave Availed'.
        Improved utilized calculation using leave's number_of_days for full overlaps.
        """
        _logger.info(f"[Leave Report Debug] Getting data for Employee: {employee.name}, Type: {leave_type.name}, Period: {date_from} to {date_to}")

        # --- Allocation Calculation ---
        allocation_domain = [
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('state', '=', 'validate'),
        ]
        allocations = self.env['hr.leave.allocation'].search(allocation_domain)
        allocated = sum(allocations.mapped('number_of_days_display'))
        _logger.info(f"[Leave Report Debug] Allocated: {allocated}")

        # --- Utilized Calculation (Improved) ---
        leave_domain = [
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('state', '=', 'validate'),
            ('request_date_from', '<=', date_to), # Leave starts before or on period end
            ('request_date_to', '>=', date_from), # Leave ends after or on period start
        ]
        _logger.info(f"[Leave Report Debug] Leave Search Domain: {leave_domain}")
        leaves = self.env['hr.leave'].search(leave_domain)
        _logger.info(f"[Leave Report Debug] Found {len(leaves)} validated leave record(s) overlapping domain.")

        utilized = 0
        if not leaves:
             _logger.info("[Leave Report Debug] No overlapping validated leaves found.")
        else:
            for leave in leaves:
                _logger.info(f"[Leave Report Debug] Processing Leave ID: {leave.id}, Date From: {leave.request_date_from}, Date To: {leave.request_date_to}, State: {leave.state}, Original Duration: {leave.number_of_days_display}")

                # Check if the leave is fully contained within the report period
                is_fully_within = (leave.request_date_from >= date_from and leave.request_date_to <= date_to)

                if is_fully_within:
                    # If fully within, use the leave's own duration
                    duration = leave.number_of_days_display # Or leave.number_of_days
                    _logger.info(f"[Leave Report Debug] Leave fully within period. Using original duration: {duration}")
                    utilized += duration
                else:
                    # If partially overlapping, calculate duration within the period
                    _logger.info("[Leave Report Debug] Leave partially overlaps period. Calculating overlap duration.")
                    period_start = max(leave.request_date_from, date_from)
                    period_end = min(leave.request_date_to, date_to)
                    _logger.info(f"[Leave Report Debug] Calculated Overlap Period: {period_start} to {period_end}")

                    if period_start <= period_end:
                        try:
                            # Convert to datetime for get_work_days_data
                            dt_period_start = fields.Datetime.to_datetime(period_start)
                            dt_period_end = fields.Datetime.to_datetime(period_end)
                            calendar = employee.resource_calendar_id
                            _logger.info(f"[Leave Report Debug] Calculating work days with calendar: {calendar.name if calendar else 'None'}")

                            work_days_data = employee.get_work_days_data(
                                dt_period_start,
                                dt_period_end,
                                calendar=calendar
                            )
                            # Use the calculated duration for the partial overlap
                            duration = work_days_data.get('days', 0)
                            _logger.info(f"[Leave Report Debug] get_work_days_data result: {work_days_data}, Duration (days) for overlap: {duration}")
                            utilized += duration
                        except Exception as e:
                            _logger.error(f"[Leave Report Debug] Error calculating partial duration for leave ID {leave.id}: {e}", exc_info=True)
                    else:
                         # This case should ideally not happen with the initial domain search, but log just in case
                        _logger.warning("[Leave Report Debug] Overlap calculation resulted in period_start > period_end. Skipping.")


        balance = allocated - utilized
        _logger.info(f"[Leave Report Debug] Final Utilized: {utilized}, Balance: {balance}")

        return {
            'allocated': allocated,
            'utilized': utilized, # Key remains 'utilized'
            'balance': balance
        }

    # --- generate_excel_report function remains the same as the previous version ---
    # --- It includes the header writing logic and calls _get_leave_data ---
    def generate_excel_report(self):
        """
        Generates the Excel report using the third specified header format.
        - Row 3: Fixed headers (A-D) + Merged "Leave Type Allocation" (E+)
        - Row 4: Empty (A-D) + Merged Leave Type Names (E-G, H-J, ...)
        - Row 5: Empty (A-D) + Sub-headers (Allocated, Availed, Balance) (E,F,G, H,I,J, ...)
        - Row 6: Data starts
        """
        _logger.info("[Leave Report Debug] Starting generate_excel_report") # Log start of report generation
        # Fetch active leave types that require allocation
        leave_types = self.env['hr.leave.type'].search([
            ('active', '=', True),
            ('requires_allocation', '=', 'yes')
        ], order='name') # Or sequence

        if not leave_types:
            _logger.warning("[Leave Report Debug] No active leave types requiring allocation found.")
            raise UserError(_("No active leave types requiring allocation found."))
        _logger.info(f"[Leave Report Debug] Found {len(leave_types)} leave types.")

        # Fetch employees (using the specific list from the original code)
        employee_names = [
            'Anup Das', 'Anup Mothey', 'Ashok', 'Bivek Pradhan', 'Brijesh Sharma',
            'Chandra maya Pradhan', 'Chiranjit Das', 'Geeta Sharma', 'Hema Devi Dahal',
            'Indra Bdr Ghallay', 'Jagat Bdr Chhetri', 'Kiran Khariya', 'Laxmi Ghallay',
            'Mahesh Bahadur Pradhan', 'Pobi Pradhan', 'Radika Ghallay', 'Sang Tshering Lapcha',
            'Sanjay Shah', 'Sher Bdr Ghallay', 'Sidarth Sharma', 'Sonam Pelden',
            'Sujata Pradhan', 'Uday Sarkar'
        ]
        employees = self.env['hr.employee'].search([
            ('active', '=', True),
            ('name', 'in', employee_names)
        ], order='name')

        if not employees:
             _logger.warning("[Leave Report Debug] No employees found matching the specified names.")
             raise UserError(_("No employees found matching the specified names."))
        _logger.info(f"[Leave Report Debug] Found {len(employees)} employees.")


        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Leave Allocation Summary')

        # --- Define Formats (for Third Header Structure) ---
        title_format = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter'
        })
        date_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'num_format': 'yyyy-mm-dd'
        })
        # Format for Header Row 3 (Fixed + Merged)
        header_row3_fixed_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1,
            'bg_color': '#DDEBF7', 'text_wrap': True # Light Blue BG
        })
        header_row3_merged_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1,
            'bg_color': '#DDEBF7', 'text_wrap': True # Light Blue BG
        })
        # Format for Header Row 4 (Merged Leave Type Names)
        header_row4_merged_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1,
            'bg_color': '#E2EFDA', 'text_wrap': True # Light Green BG
        })
        # Format for Header Row 5 (Sub-headers: Allocated, Availed, Balance)
        header_row5_sub_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1,
            'bg_color': '#F2F2F2', 'font_size': 9, 'text_wrap': True # Light Grey, smaller font
        })
        # Default cell format
        cell_format = workbook.add_format({
            'border': 1, 'valign': 'vcenter', 'align': 'left'
        })
        cell_format_center = workbook.add_format({
            'border': 1, 'valign': 'vcenter', 'align': 'center'
        })
        number_format = workbook.add_format({
            'border': 1, 'num_format': '0.00', 'align': 'right', 'valign': 'vcenter'
        })
        # Format for empty header cells to maintain borders and match row bg
        empty_header_row4_format = workbook.add_format({'border': 1, 'bg_color': '#E2EFDA'}) # Match row 4 bg
        empty_header_row5_format = workbook.add_format({'border': 1, 'bg_color': '#F2F2F2'}) # Match row 5 bg


        # --- Calculate dynamic column range ---
        num_leave_types = len(leave_types)
        fixed_cols = 4 # Sl.No, Name, Department, Job Position
        data_cols_per_type = 3 # Allocated, Availed, Balance
        total_cols = fixed_cols + (num_leave_types * data_cols_per_type)
        last_col_letter = xl_col_to_name(total_cols - 1) if total_cols > 0 else 'D'

        # --- Set Column Widths ---
        worksheet.set_column(0, 0, 6)  # A: Sl.No
        worksheet.set_column(1, 1, 25) # B: Name
        worksheet.set_column(2, 2, 20) # C: Department
        worksheet.set_column(3, 3, 20) # D: Job Position
        if num_leave_types > 0:
             worksheet.set_column(fixed_cols, total_cols - 1, 12) # E onwards - Leave Data

        # --- Write Title and Date Range (Rows 1 and 2) ---
        worksheet.merge_range(f'A1:{last_col_letter}1', 'Employee Leave Allocation Summary', title_format)
        worksheet.merge_range(f'A2:{xl_col_to_name(fixed_cols-1)}2', f'Period: {self.date_from.strftime("%Y-%m-%d")} to {self.date_to.strftime("%Y-%m-%d")}', date_format)
        worksheet.set_row(0, 28) # Title row height
        worksheet.set_row(1, 18) # Date row height

        # --- Write NEW Dynamic Headers (Starting from Row 3) ---
        header_row_1_num = 3 # Excel row 3 (index 2)
        header_row_2_num = 4 # Excel row 4 (index 3)
        header_row_3_num = 5 # Excel row 5 (index 4)

        # Header Row 1 (Excel Row 3)
        worksheet.write(header_row_1_num - 1, 0, 'S.No', header_row3_fixed_format) # A3
        worksheet.write(header_row_1_num - 1, 1, 'Employee Name', header_row3_fixed_format) # B3
        worksheet.write(header_row_1_num - 1, 2, 'Department', header_row3_fixed_format) # C3
        worksheet.write(header_row_1_num - 1, 3, 'Job Position', header_row3_fixed_format) # D3
        # Merge and write "Leave Type Allocation" E3 onwards
        if num_leave_types > 0:
            worksheet.merge_range(
                header_row_1_num - 1, fixed_cols, # Start col E (index 4)
                header_row_1_num - 1, total_cols - 1, # End col
                'Leave Type Allocation', header_row3_merged_format
            )
        else: # Handle case where there are no leave types
             pass

        # Header Row 2 (Excel Row 4): Merged Leave Type Names
        # Write empty borders for fixed columns (A, B, C, D)
        for c in range(fixed_cols):
            worksheet.write(header_row_2_num - 1, c, '', empty_header_row4_format)
        # Loop through leave types
        current_col = fixed_cols
        for leave_type in leave_types:
            worksheet.merge_range(
                header_row_2_num - 1, current_col,
                header_row_2_num - 1, current_col + data_cols_per_type - 1,
                leave_type.name, # Dynamic Leave Type Name
                header_row4_merged_format
            )
            current_col += data_cols_per_type

        # Header Row 3 (Excel Row 5): Sub-headers
        # Write empty borders for fixed columns (A, B, C, D)
        for c in range(fixed_cols):
            worksheet.write(header_row_3_num - 1, c, '', empty_header_row5_format)
        # Loop through leave types
        current_col = fixed_cols
        for leave_type in leave_types:
            worksheet.write(header_row_3_num - 1, current_col, 'Leave allocated', header_row5_sub_format)
            worksheet.write(header_row_3_num - 1, current_col + 1, 'Leave Availed', header_row5_sub_format) # Changed text
            worksheet.write(header_row_3_num - 1, current_col + 2, 'Leave Balance', header_row5_sub_format)
            current_col += data_cols_per_type

        # Freeze top panes (headers) - Freeze below row 5, right of column D
        worksheet.freeze_panes(header_row_3_num, fixed_cols)

        # --- Write Employee Data (Starting Row 6) ---
        current_row_idx = header_row_3_num # Data starts at index 5 (Excel Row 6)
        _logger.info(f"[Leave Report Debug] Starting data write loop from row index {current_row_idx}")
        for idx, employee in enumerate(employees, start=1):
            _logger.info(f"[Leave Report Debug] Writing data for employee: {employee.name}")
            # Write fixed columns (S.No, Name, Department, Job Position)
            worksheet.write(current_row_idx, 0, idx, cell_format_center) # Sl.No
            worksheet.write(current_row_idx, 1, employee.name or '', cell_format) # Name
            worksheet.write(current_row_idx, 2, employee.department_id.name or '', cell_format) # Department
            worksheet.write(current_row_idx, 3, employee.job_title or (employee.job_id.name or ''), cell_format) # Job Position

            # Write leave data for each type dynamically
            current_col = fixed_cols
            for leave_type in leave_types:
                _logger.info(f"[Leave Report Debug] Getting leave data for type: {leave_type.name}")
                # Call the updated function _get_leave_data
                leave_data = self._get_leave_data(employee, leave_type, self.date_from, self.date_to)

                # Write the results to Excel
                worksheet.write(current_row_idx, current_col, leave_data['allocated'], number_format)
                worksheet.write(current_row_idx, current_col + 1, leave_data['utilized'], number_format) # Use 'utilized' key
                worksheet.write(current_row_idx, current_col + 2, leave_data['balance'], number_format)
                current_col += data_cols_per_type

            current_row_idx += 1

        # --- Finalize and Save ---
        _logger.info("[Leave Report Debug] Finalizing workbook.")
        workbook.close()
        output.seek(0)
        excel_data = output.getvalue()

        # Set file name and data in wizard fields
        file_name = f'Leave_Alloc_Summary_{self.date_from.strftime("%Y%m%d")}_to_{self.date_to.strftime("%Y%m%d")}.xlsx'
        self.write({
            'excel_file': base64.b64encode(excel_data),
            'file_name': file_name
        })
        _logger.info(f"[Leave Report Debug] Report generated and saved as {file_name}")

        # Return action to download the file
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'leave.report.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'new',
        }
