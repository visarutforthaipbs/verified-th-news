import asyncio
import os
import subprocess
import sys
from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.types import TemplatedSystemInstructions, CapabilitiesConfig

# Load env variables from local .env
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                parts = line.strip().split("=", 1)
                if len(parts) == 2:
                    os.environ[parts[0]] = parts[1].strip('"\'')

# Set GEMINI_API_KEY from environment or fall back to factcheck key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_FACTCHECK_API_KEY") or ""

def run_remote_command(command: str) -> str:
    """Runs a shell command on popmacmini via SSH.

    Args:
        command: The shell command to run on popmacmini.
    """
    res = subprocess.run(
        ["ssh", "popmacmini", command],
        capture_output=True,
        text=True
    )
    if res.returncode != 0:
        return f"Error: Command failed with exit code {res.returncode}.\nStderr: {res.stderr}\nStdout: {res.stdout}"
    return res.stdout

# Agent tools
def sync_database_on_popmacmini() -> str:
    """Triggers the daily ingestion and synchronization pipeline of all fact-check sources on popmacmini."""
    return run_remote_command("cd ~/th-verify && .venv/bin/python -m th_verify.cli sync all --mode delta")

def rebuild_dataset_exports_on_popmacmini() -> str:
    """Rebuilds the dataset exports (classification splits and RAG corpus) and generates the build report on popmacmini."""
    return run_remote_command("cd ~/th-verify && .venv/bin/python scripts/build_dataset.py")

def rebuild_search_index_on_popmacmini() -> str:
    """Rebuilds the multilingual-e5-small semantic search index from the exports on popmacmini."""
    return run_remote_command("cd ~/th-verify && .venv/bin/python -m th_verify.cli index")

def run_invariants_tests_on_popmacmini() -> str:
    """Runs all quality assurance invariant tests on popmacmini to ensure no data leaks or bad normalizations exist."""
    return run_remote_command("cd ~/th-verify && .venv/bin/python -m pytest -q")

def check_claim_similarity_on_popmacmini(text: str) -> str:
    """Searches past fact-checks on popmacmini for a claim to see if it has been checked before.

    Args:
        text: The claim text or news title to check.
    """
    return run_remote_command(f"cd ~/th-verify && .venv/bin/python -m th_verify.cli check {repr(text)}")

def build_monthly_brief_on_popmacmini(month_str: str) -> str:
    """Generates the monthly brief draft on popmacmini for the specified month.

    Args:
        month_str: The month to build, e.g., '2026-06'.
    """
    return run_remote_command(f"cd ~/th-verify && .venv/bin/python scripts/build_brief.py --month {repr(month_str)}")

def build_issue_focus_report_on_popmacmini(topic: str) -> str:
    """Builds the topic-specific deep-dive focus report on popmacmini.

    Args:
        topic: The topic name, e.g. 'migrant' or 'callcenter_scam'.
    """
    return run_remote_command(f"cd ~/th-verify && .venv/bin/python scripts/build_issue_report.py --topic {repr(topic)}")

def get_review_queue_status_on_popmacmini() -> str:
    """Gets the current progress and count of unlabeled records in the human labeling queue on popmacmini."""
    cmd = """sqlite3 ~/th-verify/data/th_verify.db 'SELECT COUNT(*), SUM(verdict_origin LIKE "human%") FROM fact_checks WHERE source="sure_share" AND title LIKE "%จริงหรือ%"'"""
    return run_remote_command(cmd)

def get_actual_new_records_added_in_last_24_hours_on_popmacmini() -> str:
    """Gets the count of actual new fact-check records inserted into the database in the last 24 hours (since the last sync) on popmacmini."""
    cmd = 'sqlite3 ~/th-verify/data/th_verify.db \'SELECT source, COUNT(*) FROM fact_checks WHERE first_seen_at >= datetime("now", "-24 hours") GROUP BY source\''
    return run_remote_command(cmd)

# Define coordinator agent persona
COORDINATOR_PERSONA = """You are the TH Verify AI Coordinator. Your role is to manage and orchestrate the team of specialized agents:
- DbCaretaker: Keeps the raw database synced, tests invariants, and rebuilds dataset search indexes. Always respects human labeling.
- VerifyDeskAgent: Checks inbound claims against the index, runs similarity analysis, and evaluates risk.
- MonthlyBriefAgent: Extracts monthly trends and compiles briefs.
- IssueFocusAgent: Produces issue-specific focus reports.

You can delegate tasks to these subagents using start_subagent capability, or perform checks yourself using the exposed tools.
Always emphasize that the human labeling UI at http://popmacmini.local:8942/review is the source of truth for labeling sure_share claims.
"""

async def run_coordinator():
    if not GEMINI_API_KEY:
        print("WARNING: GEMINI_API_KEY is not set. Please set GEMINI_API_KEY environment variable or define it in your .env file.")
    
    config = LocalAgentConfig(
        api_key=GEMINI_API_KEY,
        system_instructions=TemplatedSystemInstructions(
            identity=COORDINATOR_PERSONA
        ),
        tools=[
            sync_database_on_popmacmini,
            rebuild_dataset_exports_on_popmacmini,
            rebuild_search_index_on_popmacmini,
            run_invariants_tests_on_popmacmini,
            check_claim_similarity_on_popmacmini,
            build_monthly_brief_on_popmacmini,
            build_issue_focus_report_on_popmacmini,
            get_review_queue_status_on_popmacmini,
            get_actual_new_records_added_in_last_24_hours_on_popmacmini
        ],
        capabilities=CapabilitiesConfig(
            enable_subagents=True
        )
    )
    
    async with Agent(config) as agent:
        print("=================================================================")
        print("TH Verify AI Agent Team Coordinator Active")
        print("You can chat with the coordinator and ask it to run syncs,")
        print("delegate to subagents, or evaluate claims.")
        print("=================================================================")
        await agent.run_interactive_loop()

if __name__ == "__main__":
    asyncio.run(run_coordinator())
