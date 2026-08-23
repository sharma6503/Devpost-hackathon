from dotenv import load_dotenv

# Eagerly load environment variables so they are resolved on CLI startups (e.g. adk web or api_server)
load_dotenv(override=True)

from . import agent as agent

__all__ = ["agent"]
