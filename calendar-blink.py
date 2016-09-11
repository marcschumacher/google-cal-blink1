#!/usr/local/bin/python3
import datetime
import os
import os.path
import signal
import subprocess
import sys
import time
from enum import Enum

import dateutil.parser
import httplib2
import oauth2client
import pytz
from apiclient import discovery
from oauth2client import client
from oauth2client import tools

try:
    import argparse

    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
    flags = None

# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/calendar-python-quickstart.json
SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
APPLICATION_NAME = 'blink1 notification for Google Calendar'
LOCAL_TIMEZONE = pytz.timezone('Europe/Berlin')
HOME_DIR = os.path.expanduser("~")
BLINK1_DIR = os.path.join(HOME_DIR, '.blink1')
CREDENTIAL_DIR = os.path.join(BLINK1_DIR, 'credentials')
CREDENTIAL_PATH = os.path.join(CREDENTIAL_DIR, 'blink1.json')
CLIENT_SECRET_FILE = os.path.join(CREDENTIAL_DIR, 'client_secret.json')
DND_FILE = os.path.join(BLINK1_DIR, 'dnd')
BIN_BLINK_TOOL = os.path.join(HOME_DIR, 'bin/blink1-tool')

PRE_ALERT_TIME_MINUTES = 5  # minutes of pre alerting
CHECK_INTERVAL = 5  # seconds at which status is checked


class LEDStatus1(Enum):
    noEvent = 0,
    eventNow = 1,
    eventSoon = 2


class LEDStatus2(Enum):
    free = 0,
    dnd = 1


def get_credentials():
    if not os.path.exists(CREDENTIAL_DIR):
        os.makedirs(CREDENTIAL_DIR)
    store = oauth2client.file.Storage(CREDENTIAL_PATH)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else:  # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + CREDENTIAL_PATH)
    return credentials


def is_busy_event(event):
    return not ('transparency' in event and event['transparency'] == 'transparent')


def get_next_shortly_upcoming_event(service, minutes_before):
    now_dt = datetime.datetime.utcnow()
    now = now_dt.isoformat() + 'Z'  # 'Z' indicates UTC time

    time_max_dt = now_dt + datetime.timedelta(minutes=minutes_before)
    time_max = time_max_dt.isoformat() + 'Z'  # 'Z' indicates UTC time

    now_dt = now_dt.replace(tzinfo=datetime.timezone.utc)

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
                if not start_dt.tzinfo:
                    start_dt = LOCAL_TIMEZONE.localize(start_dt)
                if start_dt > now_dt:
                    return event


def get_current_event(service):
    now_dt = datetime.datetime.utcnow()
    now = now_dt.isoformat() + 'Z'  # 'Z' indicates UTC time
    now_dt = now_dt.replace(tzinfo=datetime.timezone.utc)

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
                if not start_dt.tzinfo:
                    start_dt = LOCAL_TIMEZONE.localize(start_dt)
                if start_dt <= now_dt:
                    return event
        return None


def format_event(event):
    return "%s - %s: %s" % (event['start'].get('dateTime'), event['end'].get('dateTime'), event['summary'])


def get_system_status():
    led_status1 = LEDStatus1.noEvent

    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)
    current = get_current_event(service)
    if current:
        led_status1 = LEDStatus1.eventNow
        print("Running event:\n%s" % format_event(current))
    else:
        upcoming = get_next_shortly_upcoming_event(service, PRE_ALERT_TIME_MINUTES)
        if upcoming:
            led_status1 = LEDStatus1.eventSoon
            print("Upcoming event:\n%s" % format_event(upcoming))

    led_status2 = LEDStatus2.free

    if is_dnd():
        print("DND file is set")
        led_status2 = LEDStatus2.dnd

    return led_status1, led_status2


def signal_handler(signal, frame):
    print("Shutting down blink")
    execute_blink_cli(["--off"])
    sys.exit(0)


def execute_blink_cli(param):
    callarray = [BIN_BLINK_TOOL, '-q']
    callarray.extend(param)
    subprocess.call(callarray)


def set_blink_status(led_status1, led_status2):
    if led_status2 == LEDStatus2.dnd:
        print("Blink status 2: DND")
        execute_blink_cli(["--red", "-l", "2"])
    elif led_status2 == LEDStatus2.free:
        print("Blink status 2: Free")
        execute_blink_cli(["--green", "-l", "2"])

    if led_status1 == LEDStatus1.eventNow:
        print("Blink status 1: Running event")
        execute_blink_cli(["--magenta", "--blink", "3", "-l", "1"])
        execute_blink_cli(["--magenta", "-l", "1"])
    elif led_status1 == LEDStatus1.eventSoon:
        print("Blink status 1: Upcoming event")
        execute_blink_cli(["--yellow", "--blink", "3", "-l", "1"])
        execute_blink_cli(["--yellow", "-l", "1"])
    elif led_status1 == LEDStatus1.noEvent:
        print("Blink status 1: No event")
        execute_blink_cli(["--white", "-l", "1"])


def is_dnd():
    return os.path.isfile(DND_FILE)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    while True:
        led_status1, led_status2 = get_system_status()
        set_blink_status(led_status1, led_status2)
        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()
