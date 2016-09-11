#!/usr/local/bin/python3
from __future__ import print_function
import httplib2
import os

from apiclient import discovery
import oauth2client
from oauth2client import client
from oauth2client import tools

import datetime
import dateutil.parser
from datetime import timezone

from subprocess import call

import time
import signal
import sys

import os.path

try:
    import argparse

    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
    flags = None

# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/calendar-python-quickstart.json
SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'blink1 notification for Google Calendar'

PRE_ALERT_TIME_MINUTES = 5  # minutes of pre alerting
CHECK_INTERVAL = 5  # seconds at which status is checked
DND_FILE = "%s/.dnd" % os.path.expanduser("~")


def get_credentials():
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'blink1.json')

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else:  # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials


def is_busy_event(event):
    return not ('transparency' in event and event['transparency']=='transparent')


def get_next_shortly_upcoming_event(service, minutes_before):
    now_dt = datetime.datetime.utcnow()
    now = now_dt.isoformat() + 'Z'  # 'Z' indicates UTC time

    time_max_dt = now_dt + datetime.timedelta(minutes=minutes_before)
    time_max = time_max_dt.isoformat() + 'Z'  # 'Z' indicates UTC time

    now_dt = now_dt.replace(tzinfo=timezone.utc)

    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime').execute()
    events = events_result.get('items', [])

    if not events:
        return None
    else:
        for event in events:
            if is_busy_event(event):
                start = event['start'].get('dateTime', event['start'].get('date'))
                start_dt = dateutil.parser.parse(start)
                if start_dt > now_dt:
                    return event


def get_current_event(service):
    now_dt = datetime.datetime.utcnow()
    now = now_dt.isoformat() + 'Z'  # 'Z' indicates UTC time
    now_dt = now_dt.replace(tzinfo=timezone.utc)

    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        singleEvents=True,
        orderBy='startTime').execute()

    events = events_result.get('items', [])

    if not events:
        return None
    else:
        for event in events:
            if is_busy_event(event):
                start = event['start'].get('dateTime', event['start'].get('date'))
                start_dt = dateutil.parser.parse(start)
                if start_dt <= now_dt:
                    return event
        return None


def format_event(event):
    return "%s - %s: %s" % (event['start'].get('dateTime'), event['end'].get('dateTime'), event['summary'])


def get_calendar_status():
    ret = 0
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)
    current = get_current_event(service)
    if current:
        ret = 1
        print("Running event:\n%s" % format_event(current))
    else:
        upcoming = get_next_shortly_upcoming_event(service, PRE_ALERT_TIME_MINUTES)
        if upcoming:
            ret = 2
            print("Upcoming event:\n%s" % format_event(upcoming))
    return ret


def signal_handler(signal, frame):
    print("Shutting down blink")
    execute_blink_cli(["--off"])
    sys.exit(0)


def execute_blink_cli(param):
    callarray = ['/Users/marc/bin/blink1-tool']
    callarray.extend(param)
    call(callarray)


def set_blink_status(status):
    if status == 1:
        print("Blink status: Running event")
        execute_blink_cli(["--blue", "--blink", "3"])
        execute_blink_cli(["--blue"])
    elif status == 2:
        print("Blink status: Upcoming event")
        execute_blink_cli(["--yellow", "--blink", "3"])
        execute_blink_cli(["--yellow"])
    else:
        print("Blink status: Nothing")
        execute_blink_cli(["--green"])


def is_dnd():
    return os.path.isfile(DND_FILE)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    while True:
        if is_dnd():
            execute_blink_cli(["--red", "--blink", "3"])
            execute_blink_cli(["--red"])
        else:
            set_blink_status(get_calendar_status())
        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()
