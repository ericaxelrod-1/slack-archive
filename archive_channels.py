import os
import sys
from archive_utils import (
    get_complete_workspace_topology, archive_conversation_flow
)

def main():
    print("Starting Channels archiving shard...")
    contexts = get_complete_workspace_topology(types="public_channel,private_channel")
    print(f"Found {len(contexts)} Channel contexts to process.")
    for context in contexts:
        label = f"channel_{context.get('name', 'channel')}"
        archive_conversation_flow(context["id"], label)
    print("Channels archiving shard completed.")

if __name__ == "__main__":
    main()
