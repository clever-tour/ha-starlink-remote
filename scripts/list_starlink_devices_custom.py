import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add project root to sys.path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Ensure custom_components/starlink_ha is in path for imports inside starlink_client if needed
sys.path.insert(0, str(ROOT / "custom_components" / "starlink_ha"))

# The starlink_client might be inside the custom component or a dependency
# Looking at the tree, I don't see a 'starlink_client' folder in the root.
# Ah, the manifest.json says "requirements": ["httpx>=0.27.0", "protobuf>=6.32.0"].
# Wait, I saw 'spacex' folder in 'custom_components/starlink_ha/spacex'.

# Let's check where GrpcWebClient is.
# I'll search for it.
