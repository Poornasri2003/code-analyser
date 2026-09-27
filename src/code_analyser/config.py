"""Central configuration loaded from environment variables."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password")

WATSONX_API_KEY: str = os.getenv("WATSONX_API_KEY", "")
WATSONX_URL: str = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
WATSONX_PROJECT_ID: str = os.getenv("WATSONX_PROJECT_ID", "")
WATSONX_MODEL_ID: str = os.getenv("WATSONX_MODEL_ID", "ibm/granite-3-8b-instruct")

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "watsonx")  # "watsonx" | "bobshell" | "fake"

MAX_FILES: int = int(os.getenv("ANALYSER_MAX_FILES", "500"))
MAX_FILE_BYTES: int = int(os.getenv("ANALYSER_MAX_FILE_BYTES", str(512 * 1024)))
CHUNK_LINES: int = 1200
EMBED_DIM: int = 384
BATCH_SIZE: int = 500

PLANNER_MAX_LINES: int = 100
PLANNER_MAX_FILES: int = 15
