import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
from contextlib import asynccontextmanager
from utils import setup_database, setup_agent, get_result
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define Lifespan for initializing the Database Engine
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Backend API...")
    # Initialize the engine once globally for the app
    engine = setup_database("data/company_data.db")
    app.state.engine = engine
    yield
    logger.info("Shutting down Backend API...")
    # Clean up engine if necessary
    app.state.engine.dispose()

app = FastAPI(title="Text-to-SQL API", lifespan=lifespan)

# Setup CORS to allow React Frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with frontend URL (e.g., http://localhost:5173)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_env = os.environ.get("GEMINI_API_KEY")

class ChatRequest(BaseModel):
    query: str
    api_key: str = None # Client can optionally pass API key if not in env

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Text-to-SQL API Backend is running"}

@app.get("/api/schema")
async def get_schema(request: Request):
    """Returns the database schema to render the ER diagram on the frontend."""
    try:
        engine: Engine = request.app.state.engine
        inspector = inspect(engine)
        schema = {}
        
        # Hardcode relationships since pandas to_sql removes them
        manual_fks = {
            "transactions_data": [
                {"constrained_columns": ["client_id"], "referred_table": "users_data", "referred_columns": ["id"]},
                {"constrained_columns": ["card_id"], "referred_table": "cards_data", "referred_columns": ["id"]},
                {"constrained_columns": ["mcc"], "referred_table": "mcc_codes", "referred_columns": ["mcc_id"]}
            ],
            "cards_data": [
                {"constrained_columns": ["client_id"], "referred_table": "users_data", "referred_columns": ["id"]}
            ]
        }
        
        for table_name in inspector.get_table_names():
            columns = []
            for column in inspector.get_columns(table_name):
                # Attempt to determine primary keys heuristically if not set
                is_pk = column.get('primary_key', 0) > 0
                if not is_pk and column['name'] in ['id', 'mcc_id']:
                    is_pk = True
                    
                columns.append({
                    "name": column['name'],
                    "type": str(column['type']),
                    "primary_key": is_pk
                })
            
            # Use manual FKs if defined, otherwise empty (since inspector fails on SQLite via Pandas)
            foreign_keys = manual_fks.get(table_name, [])
                
            schema[table_name] = {
                "columns": columns,
                "foreign_keys": foreign_keys
            }
        return {"schema": schema}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
def chat_with_agent(request_data: ChatRequest, request: Request):
    """Processes a natural language query using the Gemini SQL Agent."""
    use_api_key = request_data.api_key or api_key_env
    if not use_api_key:
        raise HTTPException(status_code=400, detail="Gemini API Key is required.")
        
    try:
        engine: Engine = request.app.state.engine
        # We re-initialize the agent to capture the exact logger output for this request
        agent, query_logger = setup_agent(engine, use_api_key)
        
        # Execute Query
        answer, sql_query, exec_time, tokens_str = get_result(request_data.query, agent, query_logger, is_api=True)
        
        # Format intermediate steps for the frontend
        thoughts = []
        for step_type, step in query_logger.intermediate_steps:
            if step_type == "action":
                thoughts.append({
                    "tool": step.tool,
                    "tool_input": step.tool_input,
                    "log": step.log
                })
        
        return {
            "answer": answer,
            "sql_query": sql_query,
            "execution_time": exec_time,
            "tokens": tokens_str,
            "thoughts": thoughts
        }
    except Exception as e:
        logger.error("Error processing chat request", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
