import pytest
import pandas as pd
import os
from src.template_engine import TemplateFiller

def test_template_auto_generation(tmpdir):
    # Use a temporary directory
    temp_dir = tmpdir.mkdir("templates")
    filler = TemplateFiller(str(temp_dir))
    
    df = pd.DataFrame({"Col1": [1, 2], "Col2": ["A", "B"]})
    template_path = os.path.join(str(temp_dir), "test_template.xlsx")
    
    # Ensure template doesn't exist
    if os.path.exists(template_path):
        os.remove(template_path)
        
    # This should generate the template and then fill it
    output = filler.fill_template(df, template_path)
    
    assert output is not None
    assert os.path.exists(template_path)
