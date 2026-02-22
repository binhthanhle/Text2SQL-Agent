import os
import time
import re
import pandas as pd
import sqlparse
from sqlalchemy.engine import Engine
from langchain.callbacks.base import BaseCallbackHandler
from langchain.callbacks.manager import CallbackManager
from sqlalchemy import create_engine
from langchain.callbacks.base import BaseCallbackHandler
from langchain.callbacks.manager import CallbackManager
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold
from dotenv import load_dotenv
load_dotenv()

from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate
)


class SQLQueryLogger(BaseCallbackHandler):
    def __init__(self):
        super().__init__()
        self.intermediate_steps = []
        self.total_tokens = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def on_agent_action(self, action, **kwargs):
        # Record each agent action
        self.intermediate_steps.append(("action", action))

    def on_tool_start(self, serialized, input_str, **kwargs):
        pass

    def on_agent_finish(self, finish, **kwargs):
        self.intermediate_steps.append(("finish", finish))

    def on_llm_end(self, response, **kwargs):
        """Extract token usage from the LLM response metadata if available."""
        try:
            if response.generations and response.generations[0]:
                msg = response.generations[0][0].message
                
                print("DEBUG DIR MSG:", dir(msg))
                print("DEBUG MSG DICT:", getattr(msg, '__dict__', msg))
                print("DEBUG RESPONSE_METADATA:", getattr(msg, 'response_metadata', 'Not Found'))
                
                # Gemini Langchain Provider
                if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                    usage = msg.usage_metadata
                    self.total_tokens += usage.get('total_tokens', 0)
                    self.input_tokens += usage.get('input_tokens', 0)
                    self.output_tokens += usage.get('output_tokens', 0)
                    return

                # Standard Langchain Providers
                if hasattr(msg, 'response_metadata') and 'token_usage' in msg.response_metadata:
                    usage = msg.response_metadata['token_usage']
                    # Some versions use an object, others a dict
                    if hasattr(usage, 'total_tokens'):
                        self.total_tokens += usage.total_tokens
                        self.input_tokens += getattr(usage, 'prompt_tokens', 0)
                        self.output_tokens += getattr(usage, 'completion_tokens', 0)
                    elif 'total_tokens' in usage:
                        self.total_tokens += usage.get('total_tokens', 0)
                        self.input_tokens += usage.get('prompt_tokens', 0)
                        self.output_tokens += usage.get('completion_tokens', 0)
                # Try fallback for generic generation info
                elif hasattr(response.generations[0][0], 'generation_info') and response.generations[0][0].generation_info:
                    gen_info = response.generations[0][0].generation_info
                    if 'token_usage' in gen_info:
                         usage = gen_info['token_usage']
                         if hasattr(usage, 'total_tokens'):
                             self.total_tokens += usage.total_tokens
                             self.input_tokens += getattr(usage, 'prompt_tokens', 0)
                             self.output_tokens += getattr(usage, 'completion_tokens', 0)
        except Exception:
            pass


def setup_database(db_path: str = "data/company_data.db") -> Engine:
    """Connects to a SQLite database and returns the engine."""
    full_path = f"sqlite:///{os.path.abspath(db_path)}"
    engine = create_engine(full_path)
    return engine


def setup_agent(engine: Engine, api_key: str) -> tuple:
    """Sets up the SQL agent along with the callback logger. Returns the agent_executor and query_logger."""
    query_logger = SQLQueryLogger()
    callback_manager = CallbackManager([query_logger])
    # Initialize the SQL database interface
    db = SQLDatabase(engine=engine)    
    # Set up the language model
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro", 
        temperature=0, 
        google_api_key=api_key,
        safety_settings={
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        }
    )
    # llm = ChatOllama(model="sqlcoder", temperature=0)

    prefix = (
        "You are an agent designed to interact with a SQL database.\n"
        "Given an input question, create a syntactically correct SQLite query to run, then look at the results of the query and return the answer.\n"
        "Unless the user specifies otherwise, whenever you return data results, you MUST ALWAYS format them as a nicely formatted Markdown Table.\n"
        "Never use numbered lists or comma separated text for data results. Always default to a Markdown Table."
    )
    
    # Create the SQL agent
    agent_executor = create_sql_agent(
        llm, 
        db=db, 
        verbose=True, 
        prefix=prefix,
        callback_manager=callback_manager, 
        handle_parsing_errors=True,
        max_iterations=15,          # Allow agent to take more steps/thoughts for complex queries
        max_execution_time=120.0    # Allow up to 2 minutes of execution time
    )
    
    return agent_executor, query_logger


def get_result(query: str, agent_executor: object, query_logger: SQLQueryLogger, is_api=False) -> tuple:
    """
    Executes the agent with the given query, then extracts the SQL query generated from the logger. 
    Returns a tuple of (agent_output, sql_query, execution_time, total_tokens).
    """
    # Clear previous intermediate steps
    query_logger.intermediate_steps.clear()
    query_logger.total_tokens = 0
    query_logger.input_tokens = 0
    query_logger.output_tokens = 0

    start_time = time.time()
        
    # Invoke the agent with the provided query
    try:
        result = agent_executor.invoke({"input": query})
        answer = result.get('output', "Could not generate an answer.")
    except ValueError as e:
        error_msg = str(e)
        # Check if it's the specific output parsing error
        if "Could not parse LLM output:" in error_msg:
            # Extract the raw answer between backticks
            match = re.search(r"Could not parse LLM output: `(.*)`", error_msg, re.DOTALL)
            if match:
                answer = match.group(1).strip()
            else:
                answer = error_msg.replace("Could not parse LLM output: ", "").strip('`').strip()
        else:
            answer = f"Error generating answer: {error_msg}"
    except Exception as e:
        error_msg = str(e)
        if "No generation chunks were returned" in error_msg:
            answer = "Error: Gemini model blocked the response or returned empty output. Safety settings have been adjusted to unblock it, but if it persists, check your prompt or model availability."
        else:
            answer = f"An unexpected error occurred: {error_msg}"
        
    end_time = time.time()
    
    execution_time = round(end_time - start_time, 2)
    
    # Retrieve token usage tracked by the callback
    token_str = "N/A"
    if query_logger.total_tokens > 0:
        token_str = f"Tot: {query_logger.total_tokens} | In: {query_logger.input_tokens} | Out: {query_logger.output_tokens}"
    
    # Look through logged events to capture the SQL query
    captured_query = None
    for event_type, event in query_logger.intermediate_steps:
        if event_type == "action" and getattr(event, "tool", None) == 'sql_db_query':
            captured_query = getattr(event, "tool_input", None)
            
            # If the tool_input is a dictionary with a single 'query' key, extract its value.
            if isinstance(captured_query, dict) and 'query' in captured_query:
                captured_query = captured_query['query']
            elif isinstance(captured_query, str):
                pass
    return answer, captured_query, execution_time, token_str



