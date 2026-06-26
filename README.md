# Slack Archive

A lightweight, robust Python tool to archive Slack channels/conversations chronologically along with all threaded replies and binary file attachments.

## Features
- **Thread Replies:** Fetches all nested thread replies.
- **Media Archiver:** Automatically downloads attachments (images, PDFs, documents) using Slack OAuth credentials.
- **Targeted Output Layout:** Stored flat in the `slack_archive/` directory with a shared `attachments/` folder.
- **Robust Pagination:** Paginated using modern `next_cursor` logic.
- **Rate-limit Resilience:** Automatic exponential/literal backoff based on Slack's `Retry-After` header.

## Setup
1. Clone the repository and configure python environment:
   ```bash
   pip install -r requirements.txt
   ```
2. Create a `.env` file from the template:
   ```bash
   cp .env.example .env
   ```
3. Set your `SLACK_USER_TOKEN`, `SLACK_CHANNEL_ID`, and a friendly `SLACK_CHANNEL_LABEL` in the `.env` file.

## Usage
Run the archiver script:
```bash
python archive_workspace.py
```

## Directory Structure
```text
slack_archive/
├── attachments/
│   ├── F012A3DEF_spec_document.pdf
│   └── F567B8XYZ_architecture_diagram.png
├── general_C01234567.json
├── random_C76543210.json
└── dm_U99887766_D11223344.json
```

## Phase 4: Execution & Automation Runbook

### Running a Monolithic Manual Extract
To execute the task directly inside your terminal session, inject your key immediately into the run command:

#### Bash / macOS / Linux
```bash
export SLACK_USER_TOKEN="xoxp-your-token-string-here"
python archive_workspace.py
```

#### PowerShell / Windows
```powershell
$env:SLACK_USER_TOKEN="xoxp-your-token-string-here"
python archive_workspace.py
```