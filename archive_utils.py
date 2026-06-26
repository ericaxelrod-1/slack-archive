import os
import json
import time
from datetime import datetime
import contextlib
import requests
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Load environment variables
load_dotenv()

SLACK_TOKEN = os.environ.get("SLACK_USER_TOKEN")
OUTPUT_DIR = "./slack_archive"
ATTACH_DIR = os.path.join(OUTPUT_DIR, "attachments")

# Initialize SDK Client
client = WebClient(token=SLACK_TOKEN)

def initialize_filesystem():
    """Guarantees output directories exist prior to pipeline execution."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(ATTACH_DIR, exist_ok=True)

@contextlib.contextmanager
def file_lock(lock_path, timeout=10):
    """Cross-platform, atomic file lock with timeout using os.open."""
    start_time = time.time()
    fd = None
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            # Check if lock has expired (timeout)
            try:
                mtime = os.path.getmtime(lock_path)
                if time.time() - mtime > timeout:
                    try:
                        os.remove(lock_path)
                    except OSError:
                        pass
            except OSError:
                pass
            
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Could not acquire lock on {lock_path} within {timeout} seconds.")
            time.sleep(0.05)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.remove(lock_path)
        except OSError:
            pass

def write_audit_log(conversation_id, file_label, status, status_code, status_message, records_count, bytes_written, error_detail=None):
    """Appends structured audit metrics to a central log file with atomic locking."""
    audit_filepath = os.path.join(OUTPUT_DIR, "archive_audit.json")
    lock_filepath = audit_filepath + ".lock"
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "input_parameters": {
            "conversation_id": conversation_id,
            "file_label": file_label
        },
        "response_metrics": {
            "status": status,
            "status_code": status_code,
            "status_message": status_message,
            "total_records": records_count,
            "total_bytes": bytes_written,
            "error_detail": error_detail
        }
    }
    
    # Ensure OUTPUT_DIR exists before logging
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    try:
        with file_lock(lock_filepath):
            with open(audit_filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # Fallback to stdout if lock fails, to ensure we don't crash but still report
        print(f"Logging error to stdout (could not write to audit file): {e}")
        print(json.dumps(log_entry, ensure_ascii=False))

def download_binary_file(url, filename, file_id, conversation_id):
    """
    Streams authenticated binary assets from Slack's CDN to disk.
    Organizes attachments by conversation_id: slack_archive/attachments/{conversation_id}/{file_id}_{filename}
    """
    local_filename = f"{file_id}_{filename}"
    conversation_dir = os.path.join(ATTACH_DIR, conversation_id)
    os.makedirs(conversation_dir, exist_ok=True)
    local_path = os.path.join(conversation_dir, local_filename)
    
    # Return relative path reference if already downloaded
    if os.path.exists(local_path):
        return f"./attachments/{conversation_id}/{local_filename}"

    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    try:
        with requests.get(url, headers=headers, stream=True) as response:
            response.raise_for_status()
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"    -> Downloaded attachment: {conversation_id}/{local_filename}")
        return f"./attachments/{conversation_id}/{local_filename}"
    except Exception as e:
        print(f"    -> Failed downloading attachment {filename} in {conversation_id}: {e}")
        return None

def parse_and_stage_attachments(message, conversation_id):
    """Scans message objects for file attachments and schedules download jobs."""
    if "files" in message:
        for file_info in message["files"]:
            url = file_info.get("url_private")
            name = file_info.get("name")
            file_id = file_info.get("id")
            if url and name and file_id:
                local_path_ref = download_binary_file(url, name, file_id, conversation_id)
                if local_path_ref:
                    # Injects local disk pointer directly into the archived metadata schema
                    file_info["local_archive_path"] = local_path_ref

def extract_thread_replies(channel_id, thread_ts):
    """Exhaustively consumes all nested replies within an out-of-band message thread."""
    replies = []
    cursor = None
    while True:
        try:
            response = client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                cursor=cursor,
                limit=200
            )
            replies.extend(response["messages"])
            cursor = response.get("response_metadata", {}).get("next_cursor")
            time.sleep(0.5)  # Proactive Tier 3 rate limiting delay
            if not cursor:
                break
        except SlackApiError as e:
            if e.response["error"] == "ratelimited":
                delay = int(e.response.headers.get("Retry-After", 15))
                print(f"  Rate limited inside thread. Waiting {delay}s...")
                time.sleep(delay)
                continue
            print(f"  Error reading thread {thread_ts}: {e.response['error']}")
            break
    return replies

def archive_conversation_flow(conversation_id, file_label):
    """Processes chronological conversation history, threads, and binary media pools."""
    print(f"Processing target context: {file_label} ({conversation_id})")
    
    initialize_filesystem()
    
    all_messages = []
    cursor = None
    status = "SUCCESS"
    status_code = 200
    status_message = "OK"
    error_detail = None
    
    while True:
        try:
            response = client.conversations_history(
                channel=conversation_id,
                cursor=cursor,
                limit=100
            )
            
            print(f"Fetched {len(response['messages'])} messages from history...")
            for msg in response["messages"]:
                # Process attachments for top-level messages
                parse_and_stage_attachments(msg, conversation_id)
                
                # Intercept parent threads and download child items
                if msg.get("reply_count", 0) > 0:
                    thread_ts = msg.get("thread_ts")
                    print(f"  -> Extracting {msg['reply_count']} nested replies from thread: {thread_ts}")
                    replies = extract_thread_replies(conversation_id, thread_ts)
                    nested_replies = []
                    for reply in replies:
                        # Skip parent message duplication (index 0 of conversation_replies is the parent)
                        if reply["ts"] == thread_ts:
                            continue
                        parse_and_stage_attachments(reply, conversation_id)
                        nested_replies.append(reply)
                    msg["replies"] = nested_replies
                
                all_messages.append(msg)
                
            # Check for next page
            cursor = response.get("response_metadata", {}).get("next_cursor")
            time.sleep(0.5)  # Proactive Tier 3 rate limiting delay
            if not cursor:
                break
            
        except SlackApiError as e:
            if e.response["error"] == "ratelimited":
                delay = int(e.response.headers.get("Retry-After", 15))
                print(f"  Rate limit hit. Resuming execution after a {delay}s backoff...")
                time.sleep(delay)
                continue
            else:
                error_msg = e.response['error']
                print(f"  Failed consuming history for context {file_label}: {error_msg}")
                status = "ERROR"
                status_code = e.response.status_code
                status_message = error_msg
                break
        except Exception as e:
            print(f"  Unexpected error fetching history for conversation {conversation_id}: {e}")
            status = "ERROR"
            status_code = 500
            status_message = "Unexpected Error"
            error_detail = str(e)
            break

    bytes_written = 0
    if status == "SUCCESS" and len(all_messages) > 0:
        output_filepath = os.path.join(OUTPUT_DIR, f"{file_label}_{conversation_id}.json")
        with open(output_filepath, "w", encoding="utf-8") as f:
            json.dump(all_messages, f, indent=4, ensure_ascii=False)
        bytes_written = os.path.getsize(output_filepath)
        print(f"Saved {len(all_messages)} entries -> {output_filepath}\n")
        write_audit_log(conversation_id, file_label, "SUCCESS", 200, "OK", len(all_messages), bytes_written)
    elif status == "SUCCESS":
        print(f"No messages found for context {file_label} ({conversation_id}). Logging to audit file.\n")
        write_audit_log(conversation_id, file_label, "EMPTY", 200, "No messages retrieved", 0, 0)
    else:
        print(f"Failed to archive context {file_label} ({conversation_id}). Logging to audit file.\n")
        write_audit_log(conversation_id, file_label, status, status_code, status_message, len(all_messages), 0, error_detail=error_detail)
        
    return all_messages

def get_complete_workspace_topology(types="public_channel,private_channel,im,mpim"):
    """Discovers every workspace context exposure available to the token profile."""
    conversations = []
    cursor = None
    while True:
        try:
            response = client.conversations_list(
                types=types,
                cursor=cursor,
                limit=100
            )
            conversations.extend(response["channels"])
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        except SlackApiError as e:
            print(f"Failed to query workspace topology: {e.response['error']}")
            break
    return conversations

def cleanup_empty_files():
    """Finds and deletes files in the output directory that are empty or contain only '[]' or whitespace."""
    if not os.path.exists(OUTPUT_DIR):
        return 0
    deleted_count = 0
    for filename in os.listdir(OUTPUT_DIR):
        filepath = os.path.join(OUTPUT_DIR, filename)
        if os.path.isfile(filepath) and filename.endswith(".json") and filename != "archive_audit.json":
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content or content == "[]" or content == "{}":
                    os.remove(filepath)
                    print(f"Deleted empty archive file: {filename}")
                    deleted_count += 1
            except Exception as e:
                print(f"Error checking/deleting file {filename}: {e}")
    return deleted_count
