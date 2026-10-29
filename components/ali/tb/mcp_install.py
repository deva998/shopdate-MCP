"""Legacy installation entry: portable releases use the root installer."""
import sys

def main(argv, home=None):
    print('Use install.ps1 (Windows) or install.sh (macOS) at the release root. '
          'This release exports MCP configs; merge them in your client settings. '
          'No client settings were changed.', file=sys.stderr)
    return 2
