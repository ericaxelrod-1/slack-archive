import os
import sys
import json
import time
from slack_sdk.errors import SlackApiError
from archive_utils import (
    client, OUTPUT_DIR, write_audit_log, parse_and_stage_attachments, initialize_filesystem
)

def archive_search_query(query):
    print(f"Processing search query: '{query}'")
    initialize_filesystem()
    
    all_messages = []
    page = 1
    status = "SUCCESS"
    status_code = 200
    status_message = "OK"
    error_detail = None
    
    while True:
        try:
            response = client.search_messages(
                query=query,
                page=page,
                count=100
            )
            
            messages_payload = response.get("messages", {})
            matches = messages_payload.get("matches", [])
            print(f"Fetched page {page}: {len(matches)} matches...")
            
            if not matches:
                break
                
            for msg in matches:
                # Process attachments
                channel_id = msg.get("channel", {}).get("id")
                if channel_id:
                    parse_and_stage_attachments(msg, channel_id)
                all_messages.append(msg)
                
            pagination = messages_payload.get("pagination", {})
            page_count = pagination.get("page_count", 1)
            if page >= page_count:
                break
                
            page += 1
            time.sleep(1.0)  # Search API has stricter rate limits
            
        except SlackApiError as e:
            if e.response["error"] == "ratelimited":
                delay = int(e.response.headers.get("Retry-After", 15))
                print(f"  Rate limited in search. Waiting {delay}s...")
                time.sleep(delay)
                continue
            else:
                error_msg = e.response['error']
                print(f"  Failed running search for query '{query}': {error_msg}")
                status = "ERROR"
                status_code = e.response.status_code
                status_message = error_msg
                break
        except Exception as e:
            print(f"  Unexpected error running search: {e}")
            status = "ERROR"
            status_code = 500
            status_message = "Unexpected Error"
            error_detail = str(e)
            break
            
    # Save search results to a specific JSON file
    query_slug = "".join([c if c.isalnum() else "_" for c in query]).strip("_")
    file_label = f"search_{query_slug}"
    bytes_written = 0
    
    if status == "SUCCESS" and len(all_messages) > 0:
        output_filepath = os.path.join(OUTPUT_DIR, f"{file_label}.json")
        with open(output_filepath, "w", encoding="utf-8") as f:
            json.dump(all_messages, f, indent=4, ensure_ascii=False)
        bytes_written = os.path.getsize(output_filepath)
        print(f"Saved {len(all_messages)} entries -> {output_filepath}\n")
        write_audit_log("search_api", file_label, "SUCCESS", 200, "OK", len(all_messages), bytes_written)
    elif status == "SUCCESS":
        print(f"No search results found for query '{query}'. Logging to audit file.\n")
        write_audit_log("search_api", file_label, "EMPTY", 200, "No messages retrieved", 0, 0)
    else:
        print(f"Failed to archive search query '{query}'. Logging to audit file.\n")
        write_audit_log("search_api", file_label, status, status_code, status_message, len(all_messages), 0, error_detail=error_detail)

def main():
    queries = sys.argv[1:]
    if not queries:
        queries_file = "search_queries.txt"
        if os.path.exists(queries_file):
            with open(queries_file, "r", encoding="utf-8") as f:
                queries = [line.strip() for line in f if line.strip()]
        else:
            print("No search queries provided. Pass queries as command-line arguments or define them in search_queries.txt.")
            print("Example: python archive_search.py \"ai\" \"urgent\"")
            return
            
    print(f"Starting Search archiving shard with {len(queries)} queries...")
    for query in queries:
        archive_search_query(query)
    print("Search archiving shard completed.")

if __name__ == "__main__":
    main()
