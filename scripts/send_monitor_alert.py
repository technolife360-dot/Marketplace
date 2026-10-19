#!/usr/bin/env python3
"""Send a minimal operational alert to the explicitly authorized support mailbox."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import email_service

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workflow',required=True);parser.add_argument('--run-url',required=True);args=parser.parse_args()
    try:email_service.send_monitor_alert('sentryloot@gamestorehub.com',args.workflow,args.run_url)
    except Exception as exc:
        print('Monitor email was not delivered: '+type(exc).__name__,file=sys.stderr);return 1
    print('Operational alert accepted by the configured email provider.');return 0
if __name__=='__main__':raise SystemExit(main())
