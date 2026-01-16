# OGE Document Automation System

Automated system for requesting, downloading, and organizing documents from the U.S. Office of Government Ethics (OGE) website.

## Overview

This system automates the process of:
1. Requesting transaction documents from the OGE website via web form submission
2. Downloading directly available documents without form submission
3. Processing email responses from OGE and organizing attachments

The system operates on pages 36-39 of the OGE website, filtered by Transaction type and sorted alphabetically by name.

## Prerequisites

- Python 3.8 or higher
- Google Chrome browser
- Gmail account with app-specific password (for email processing)
- Active internet connection

## Installation

1. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install required packages:

```bash
pip install -r requirements.txt
```

## Configuration

Edit `config.py` to set your credentials and preferences:

```python
USER_NAME = "Your Name"
USER_EMAIL = "your.email@example.com"
USER_OCCUPATION = "Your Occupation"
START_PAGE = 37
END_PAGE = 39
MAX_FILES_PER_BATCH = 5
GMAIL_USERNAME = "your.gmail@gmail.com"
GMAIL_PASSWORD = "your-app-specific-password"
```

**Important**: For Gmail, you must use an app-specific password, not your regular password. Generate one at: https://myaccount.google.com/apppasswords

## System Architecture

The system consists of three main components:

### 1. oge_automation.py - Request Form Submission

Automates form submission for documents that require email delivery.

**What it does**:
- Navigates to OGE website and applies filters (Transaction type, A-Z sort)
- For each row, clicks "Request this Document" link
- Opens popup to find matching individuals
- Selects up to 5 documents per batch
- Fills form with user information (Name, Email, Occupation)
- Submits request (documents will be emailed later)
- Tracks requested documents to avoid duplicate submissions

**Key features**:
- Handles multiple individuals per document (e.g., same person listed twice)
- Batches requests (5 files per submission)
- Persistent tracking via `requested_documents.json` - safe to resume if interrupted
- Dismisses browser alerts automatically
- Logs all actions to `request_log.csv` and `progress.md`

**Usage**:

```bash
python oge_automation.py
```

Options:
- `--yes` or `-y`: Skip confirmation prompt

**Outputs**:
- `request_log.csv`: Detailed log of all submissions
- `progress.md`: Real-time progress log
- `requested_documents.json`: Tracking file for resuming
- Documents will arrive via email to the configured email address

### 2. oge_direct_downloader.py - Direct Download

Downloads files that are immediately available without form submission.

**What it does**:
- Navigates to OGE website and applies same filters
- Identifies documents with direct PDF links or "(click to download)" labels
- Opens request forms to find hidden downloadable files in popups
- Downloads files directly using urllib or Selenium
- Organizes files by Page/PersonName structure using `peopleToPage_actual.json` mapping
- Skips files that already exist

**Key features**:
- No form submission - only downloads immediately available files
- Uses person-to-page mapping for folder organization
- Downloads from both table links and popup windows
- Puts unmatched documents in `_Unmatched` folder
- Logs downloads to CSV

**Usage**:

```bash
python oge_direct_downloader.py
```

Options:
- `--yes` or `-y`: Skip confirmation prompt
- `--headless`: Run browser in headless mode

**Outputs**:
- `OGE_Documents/Page_XX/PersonName/*.pdf`: Downloaded files
- `OGE_Documents/_Unmatched/*.pdf`: Files without mapping match
- `direct_download_log.csv`: Download log
- `direct_download_progress.md`: Progress tracking

### 3. email_processor.py - Email Attachment Processing

Processes emails from OGE and organizes PDF attachments.

**What it does**:
- Connects to Gmail via IMAP
- Searches for emails from `No_Reply/USOGE.OGEX5@oge.gov`
- Downloads PDF attachments
- Parses filenames to extract person names (Format: FirstName-LastName-Date-Type.pdf)
- Matches names to `peopleToPage_all.json` using fuzzy matching
- Organizes files into `OGE_Documents/Page_XX/PersonName/` structure
- Tracks matched/unmatched files in CSV reports

**Key features**:
- Fuzzy name matching for robust filename parsing
- Can process unread or all emails
- Optional mark-as-read functionality
- Skips already downloaded files
- Generates CSV reports for matched and unmatched documents

**Usage**:

```bash
python email_processor.py
```

Options:
- `--all`: Process all emails (not just unread)
- `--mark-read`: Mark processed emails as read
- `--yes` or `-y`: Skip confirmation prompt

**Outputs**:
- `OGE_Documents/Page_XX/PersonName/*.pdf`: Organized attachments
- `OGE_Documents/_Unmatched/*.pdf`: Unmatched attachments
- `matched_people.csv`: List of matched people with document counts
- `unmatched_documents.csv`: List of unmatched filenames

## Workflow

Recommended execution order:

1. **Run oge_automation.py**: Submit requests for documents requiring email delivery
   - Wait 2-3 business days for OGE to process requests

2. **Run oge_direct_downloader.py**: Download immediately available files
   - Can be run anytime, independent of step 1

3. **Run email_processor.py**: Process emails received from OGE
   - Run after receiving email notifications from OGE
   - Can be run multiple times as new emails arrive

## File Structure

```
OGE_downloadingForms/
├── oge_automation.py          # Request form submission script
├── oge_direct_downloader.py   # Direct download script
├── email_processor.py         # Email processing script
├── config.py                  # Configuration file
├── audit.py                   # Utility for checking missing files
├── requirements.txt           # Python dependencies
├── peopleToPage_actual.json   # Person-to-page mapping (direct downloader)
├── peopleToPage_all.json      # Person-to-page mapping (email processor)
├── requested_documents.json   # Tracking file for requested docs
├── request_log.csv            # Log of form submissions
├── progress.md                # Progress tracking
├── matched_people.csv         # Matched email attachments report
├── unmatched_documents.csv    # Unmatched email attachments report
└── OGE_Documents/             # Downloaded files organized by page/person
    ├── Page_36/
    ├── Page_37/
    ├── Page_38/
    ├── Page_39/
    └── _Unmatched/
```

## Important Files

### config.py

Central configuration file containing:
- User credentials for form submission
- Gmail credentials for email processing
- Page range configuration
- Batch size settings
- Timeout configurations
- File paths for logs and tracking

**Security Note**: This file contains sensitive credentials. Never commit it to public repositories.

### peopleToPage_actual.json / peopleToPage_all.json

JSON mappings from person names to page numbers:

```json
{
  "LastName, FirstName": 37,
  "Smith, John": 38
}
```

Used by downloaders to organize files into correct page folders.

### requested_documents.json

Persistent tracking file that stores which documents have been requested per individual:

```json
{
  "aber, jessica d department of justice...": [
    "ethics agreement",
    "278 transaction report"
  ]
}
```

Allows the system to resume without duplicate requests if interrupted.

## Troubleshooting

**Browser crashes or hangs**:
- The automation restarts the browser every 10 requests to prevent memory issues
- Check your Chrome version matches chromedriver (webdriver-manager handles this automatically)

**Alert dialogs blocking execution**:
- Scripts include alert dismissal logic
- If alerts persist, check for unexpected popup content on the website

**Files not downloading**:
- Verify Chrome download settings allow automatic downloads
- Check that `downloads/` folder has write permissions
- Ensure stable internet connection

**Email connection fails**:
- Verify Gmail credentials in config.py
- Ensure you're using an app-specific password, not your regular Gmail password
- Check that IMAP is enabled in Gmail settings

**Name matching issues**:
- Check that `peopleToPage_*.json` files are up to date
- Unmatched files will be placed in `_Unmatched` folder for manual review
- Install thefuzz library for better fuzzy matching: `pip install thefuzz python-Levenshtein`

## Logging and Monitoring

All scripts provide real-time console output and generate detailed logs:

- **request_log.csv**: Every form submission with timestamp, person name, files requested, status
- **progress.md**: Human-readable progress log with timestamps
- **direct_download_log.csv**: All download attempts and outcomes
- **matched_people.csv**: Summary of successfully matched documents from emails
- **unmatched_documents.csv**: Documents that couldn't be matched to known people

## Audit Utility

`audit.py` compares requested documents (from `requested_documents.json`) with actual downloaded files:

```bash
python audit.py
```

Outputs:
- Unknown names: Files in directory not tracked in JSON (shouldn't exist)
- Missing files: Files requested but not yet received from OGE
- Missing names: Names in JSON but not in directory

## Notes

- The OGE website may update its structure; XPath selectors may need adjustment
- Processing pages 36-39 typically takes 2-4 hours depending on document count
- OGE requests are typically fulfilled within 2 business days
- The system is designed to be resumable - safe to stop and restart
- All scripts include retry logic and error handling for robustness

## Support

For issues or questions, refer to:
- Script logs in `*.csv` and `*.md` files
- Console output for real-time status
- `requested_documents.json` to check request history
