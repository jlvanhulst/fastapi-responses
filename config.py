"""
    This file contains all project configs read from env file.
"""

import os
import logging
from dotenv import load_dotenv


class Config():
    """
    Main configuration class. Contains all the configurations for the project.
    """

    DEBUG: bool = (os.getenv("DEBUG", "FALSE") == "TRUE")
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.DEBUG, filename='app.log', filemode='a', format='%(asctime)s - %(levelname)s - %(message)s')

    logger.info(f"DEBUG: {DEBUG}")
    env = ".env.development" if DEBUG else ".env.production"
    env_found = load_dotenv(env)
    if not env_found:
        env = ".env"
        env_found = load_dotenv(env)
    if not env_found:
        logger.warning('No environment settings file used/found')
    else:
        logger.info(f"Environment settings file used: {env} ")

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    GOOGLE_SEARCH_CX_ID: str = os.getenv("GOOGLE_SEARCH_CX_ID")
    GOOGLE_SEEARCH_DEVELOPER_KEY: str = os.getenv("GOOGLE_SEEARCH_DEVELOPER_KEY")

    PROMPTS_DIR: str = os.getenv("PROMPTS_DIR", "prompts")


config = Config()

if config.OPENAI_API_KEY is None and config.GEMINI_API_KEY is None:
    # the app needs at least one API key - so no point in continuing
    raise ValueError("Neither OPENAI_API_KEY nor GEMINI_API_KEY is set - cannot run without at least one! Set it either in your OS or in .env or config.py")
