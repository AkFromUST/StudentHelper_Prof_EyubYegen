"""
Configuration file for OGE Document Request Automation
"""

# User Information for form submission
USER_NAME = "Eyub Yegen"
USER_EMAIL = "eyubyegen3@gmail.com"
USER_OCCUPATION = "Professor"
USER_TYPE = "Private citizen"  # Options: Private citizen, Law firm, Other private organization, Government

# Page range to process (inclusive)
# For testing: just page 36
START_PAGE = 1
END_PAGE = 1

# Maximum files per request batch
MAX_FILES_PER_BATCH = 5

# Timeouts (in seconds)
PAGE_LOAD_TIMEOUT = 30
ELEMENT_WAIT_TIMEOUT = 15
BETWEEN_ACTIONS_DELAY = 1.5

# Logging
LOG_FILE = "request_log.csv"
PROGRESS_FILE = "progress.md"

# Downloads
DOWNLOADS_DIR = "downloads"

# Persistent tracking file for requested documents (allows resume if script stops)
REQUESTED_DOCS_FILE = "requested_documents.json"

# Website URLs
BASE_URL = "https://www.oge.gov/Web/OGE.nsf/Officials%20Individual%20Disclosures%20Search%20Collection?OpenForm"

GMAIL_PASSWORD = ""
GMAIL_USERNAME = "eyubyegen3@gmail.com"