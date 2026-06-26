import os
import sys
import time
import subprocess
import threading
from archive_utils import initialize_filesystem, cleanup_empty_files, SLACK_TOKEN

def stream_output(process, prefix):
    """Streams stdout/stderr of a child process with a decorative prefix."""
    for line in iter(process.stdout.readline, ''):
        if line:
            print(f"[{prefix}] {line.strip()}", flush=True)

def run_shard(script_name, prefix, args=[]):
    """Launches a shard script in a subprocess and streams its output in a daemon thread."""
    cmd = [sys.executable, "-u", script_name] + args
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    thread = threading.Thread(target=stream_output, args=(process, prefix))
    thread.daemon = True
    thread.start()
    return process, thread

def main():
    start_time = time.time()
    
    if not SLACK_TOKEN or not SLACK_TOKEN.startswith("xoxp-"):
        print("Execution Blocked: A valid SLACK_USER_TOKEN environment variable starting with 'xoxp-' is required.")
        return

    initialize_filesystem()
    
    # 1. Preliminary cleanup of any empty files
    print("Performing initial clean up of empty JSON files...")
    initial_deleted = cleanup_empty_files()
    print(f"Removed {initial_deleted} empty files.")
    
    # 2. Configure Shards to Run
    shards_to_run = [
        ("archive_dms.py", "DMs", []),
        ("archive_channels.py", "Channels", [])
    ]
    
    # Check if we should also run search queries
    queries_file = "search_queries.txt"
    search_args = sys.argv[1:]
    if search_args or os.path.exists(queries_file):
        shards_to_run.append(("archive_search.py", "Search", search_args))
        
    print(f"Launching {len(shards_to_run)} archiving shards in parallel...")
    
    active_shards = []
    for script_name, prefix, args in shards_to_run:
        process, thread = run_shard(script_name, prefix, args)
        active_shards.append((process, prefix))
        
    # Wait for all processes to finish
    for process, prefix in active_shards:
        process.wait()
        print(f"Shard [{prefix}] finished with exit code {process.returncode}")
        
    # 3. Post-execution cleanup of any empty files
    print("Performing final clean up of any empty JSON files created during this run...")
    final_deleted = cleanup_empty_files()
    print(f"Removed {final_deleted} empty files.")
    
    duration = time.time() - start_time
    print(f"Workspace archiving complete. Total execution time: {duration:.2f} seconds.")

if __name__ == "__main__":
    main()
