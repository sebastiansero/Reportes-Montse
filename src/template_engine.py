from openpyxl import load_workbook, Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font, PatternFill
import io
import pandas as pd
from loguru import logger
import os

class TemplateFiller:
    def __init__(self, template_dir: str = "templates"):
        self.template_dir = template_dir
        os.makedirs(self.template_dir, exist_ok=True)

    def fill_template(self, df: pd.DataFrame, template_path: str) -> io.BytesIO:
        """
        Fills the Excel template with data. If template doesn't exist, generates a default one.
        """
        try:
            if not os.path.exists(template_path):
                logger.warning(f"Template {template_path} not found. Generating default.")
                self._generate_default_template(df, template_path)
            
            wb = load_workbook(template_path)
            ws = wb.active
            
            # Start writing from row 2
            start_row = 2
            
            for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=False), start=start_row):
                for c_idx, value in enumerate(row, start=1):
                    ws.cell(row=r_idx, column=c_idx, value=value)
            
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)
            logger.info(f"Successfully filled template: {template_path}")
            return output
            
        except Exception as e:
            logger.error(f"Error filling template {template_path}: {e}")
            raise e

    def _generate_default_template(self, df: pd.DataFrame, path: str):
        """Generates a professional-looking default template."""
        wb = Workbook()
        ws = wb.active
        ws.title = "Reporte"
        
        # Write Headers
        headers = df.columns.tolist()
        ws.append(headers)
        
        # Style Headers
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
        
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
        
        wb.save(path)
        logger.info(f"Generated default template at {path}")
