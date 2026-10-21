#!/usr/bin/env python3
"""Explicit schema/reference-data migration; never run in an HTTP request."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import app
    application = app.VercelWSGIApplication()
    application._validate_config()
    app.migrate()
    # Verify the same RLS/encryption guards used by production API cold starts.
    if app.MODE == 'production':
        application._startup()
    print('Database migration and startup checks completed.')


if __name__ == '__main__':
    main()
