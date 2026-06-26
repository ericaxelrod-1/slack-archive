import os
import sys
from archive_utils import (
    get_complete_workspace_topology, archive_conversation_flow
)

def main():
    print("Starting DM and MPIM archiving shard...")
    contexts = get_complete_workspace_topology(types="im,mpim")
    print(f"Found {len(contexts)} DM/MPIM contexts to process.")
    for context in contexts:
        if context.get("is_im"):
            label = f"dm_{context.get('user')}"
        elif context.get("is_mpim"):
            label = context.get("name", "mpim_group")
        else:
            label = "dm_context"
        
        archive_conversation_flow(context["id"], label)
    print("DM and MPIM archiving shard completed.")

if __name__ == "__main__":
    main()
