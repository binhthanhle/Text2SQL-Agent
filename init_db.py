import os
import pandas as pd
from sqlalchemy import create_engine
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_database(db_name: str, db_dir: str):
    """Reads Excel files from db_dir and creates a SQLite database with multiple tables."""
    db_path_obj = Path(db_dir)
    
    if not db_path_obj.exists():
        db_path_obj.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {db_dir}")
        
    db_file_path = f"sqlite:///{db_path_obj.resolve()}/{db_name}.db"
    logger.info(f"Creating database at {db_file_path}...")
    engine = create_engine(db_file_path)

    # Process all excel files in the directory
    for file_path in db_path_obj.glob('*.xlsx'):
        try:
            table_name = file_path.stem
            logger.info(f"Reading {file_path} into table '{table_name}'...")
            df = pd.read_excel(file_path)
            
            # Clean up column names to be more SQL friendly 
            df.columns = [
                str(c).strip().replace(' ', '_').replace('/', '_')
                .replace('(', '').replace(')', '').replace('%', 'pct')
                .replace('>', 'gt').replace('<', 'lt').replace('=', 'eq')
                .replace(',', '').replace('+', 'plus').replace('-', '_').replace('.', '') 
                for c in df.columns
            ]
            
            # Clean up string values that are actually numeric (like currency or percentages)
            for col in df.columns:
                if df[col].dtype == 'object':
                    try:
                        # Check if any value starts with $ or contains $ and numbers
                        if df[col].astype(str).str.contains(r'^\$?\s?-?[\d,]+(\.\d+)?$|^-?\$[\d,]+(\.\d+)?$').any():
                            # Remove $ and , and spaces
                            df[col] = df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False).str.strip()
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    except Exception as e:
                        logger.error(f"Error parsing column {col} in {table_name}: {e}")

            df.to_sql(table_name, engine, index=False, if_exists='replace')
            logger.info(f"Table '{table_name}' loaded successfully with {len(df)} rows.")
            
        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}")

    logger.info("Database initialization complete.")

if __name__ == "__main__":
    DB_NAME = "company_data"
    DB_DIR = "data"
    
    init_database(DB_NAME, DB_DIR)
