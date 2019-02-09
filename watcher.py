#!/usr/bin/env python3
#
# I waive copyright and related rights in the this work worldwide
# through the CC0 1.0 Universal public domain dedication.
# https://creativecommons.org/publicdomain/zero/1.0/legalcode
#
# Author(s):
#   Tom Parker <tparker@usgs.gov>

""" Keep an eye on RS product generation."""

from datetime import timedelta, datetime
from string import Template
import signal
import logging
import os
import sys
import socket
import struct
import pathlib
from urllib.parse import urlparse
import errno
from multiprocessing import Process
import argparse
import smtplib
import http.client
import re

import ruamel.yaml
import tomputils.util as tutil
import pycurl
import humanize
import multiprocessing_logging
import requests


CONFIG_FILE_ENV = 'PRODUCT_WATCHER_CONFIG'
MODIS_DATE_RE = r"\.(\d{5}\.\d{4})\.modis"
MODIS_DATE_STR = "%y%j.%H%M"


def get_volcview_status():
    volcview_status = []
    for (server, server_url) in global_config['volcview_url'].items():
        server_status = {'server': server}
        sensors = {}
        url = server_url + global_config['volcview_status_path']
        resp = requests.get(url)
        server_status['response_code'] = resp.status_code
        if resp.status_code == requests.codes.ok:
            status = resp.json()
            for image in status:
                sensor = image['data_type_name']
                age = float(image['age_hours'])
                if sensor not in sensors or age < sensors[sensor]:
                    sensors[sensor] = age
        server_status['sensors'] = sensors
        volcview_status.append(server_status)

    return volcview_status


def send_email(recipient, message):
    if 'mailhost' not in global_config:
        logger.info("Skipping email, mailhost is undefined.")
        logger.info(message)
        return
    
    logger.info("Sending email to {}".format(recipient))
    server = smtplib.SMTP(global_config['mailhost'])
    server.sendmail(global_config['email_source'], recipient, message)
    server.quit()


def check_volcview(volcview_status):
    for server_status in volcview_status:
        response_code = server_status['response_code']
        server = server_status['server']
        if response_code != requests.codes.ok:
            url = global_config['volcview_url'][server] \
                  + global_config['volcview_status_path']
            message = "Subject: CRITICAL error on {}\n\n" \
                      + "Unable to pull status from {}." \
                      + " Received response code {} ({})."
            message = message.format(server, url, response_code,
                                     http.client.responses[response_code])
            send_email(global_config['volcview_watchers'], message)
        else:
            logger.info("%s status good, not panicing. (%d)", server,
                        response_code)
            age = min(server_status['sensors'].values())
            if age > global_config['volcview_max_age']:
                logger.info("{} age: {} hours. That's not good."
                            .format(server_status['server'], age))
                message = "Subject: CRITICAL error on {}\n\n".format(server) \
                          + "Images aren't making it to {}.".format(server) \
                          + " Most recent image is {} hours old.".format(age)
                send_email(global_config['volcview_watchers'], message)
            else:
                logger.info("{} age: {} hours. No reason to panic."
                            .format(server_status['server'], age))


def get_sensor_ages(volcview_status):
    sensor_ages = {}
    for server_status in volcview_status:
        for sensor, age in server_status['sensors'].items():
            if sensor not in sensor_ages or age < sensor_ages[sensor]:
                sensor_ages[sensor] = age

    return sensor_ages


def get_gina_modis_age():
    url = global_config['modis_url']
    resp = requests.get(url)
    if resp.status_code != requests.codes.ok:
        message = "Subject: CRITICAL error at GINA\n\n" \
                  + "Cannot retrieve file list from {}." \
                  + " Received response code {} ({})."
        message = message.format(url, resp.status_code,
                                 http.client.responses[resp.status_code])
        send_email(global_config['modis_watchers'], message)

    pattern = re.compile(MODIS_DATE_RE)
    most_recent = datetime(2000, 1, 1, 12)
    for date in re.findall(pattern, resp.text):
        most_recent = max(most_recent, datetime.strptime(date, MODIS_DATE_STR))

    age = (datetime.utcnow() - most_recent).total_seconds() / (60 * 60)

    logger.info("Most recent MODIS image at GINA: %s (%f hours old)",
                most_recent, age)

    return age


def check_modis(age):
    if age < global_config['modis_limit']:
        logger.info("MODIS is healthy. (%f hrs)", age)
        return

    gina_modis_age = get_gina_modis_age()
    logger.info("MODIS is unhealthy. volcview: %f hours; GINA: %f hours",
                age, gina_modis_age)

    if gina_modis_age > global_config['modis_limit']:
        logger.info("MODIS data processing problem on avors2")
        message = "Subject: MODIS data processing problem\n\n" \
                  "Most recent MODIS image in volcview is {} hours old, " \
                  "while GINA has more recent data ({} hrs). " \
                  "Check terascan processing on avors2"
        message = message.format(age, gina_modis_age)
    else:
        logger.info("MODIS data processing problem at GINA")
        message = "Subject: MODIS outage at GINA\n\n" \
                  "The most recent MODIS image at GINA is {} hours old." \
                  " Something wrong up north?\n\nGINA URL: {}"
        message = message.format(gina_modis_age,
                                 global_config['modis_url'])

    send_email(global_config['modis_watchers'], message)


def check_sensors(sensor_ages):
    check_modis(sensor_ages['MODIS'])


def parse_config():
    config_file = pathlib.Path(tutil.get_env_var(CONFIG_FILE_ENV))
    yaml = ruamel.yaml.YAML()
    try:
        global_config = yaml.load(config_file)
    except ruamel.yaml.parser.ParserError as e1:
        logger.error("Cannot parse config file")
        tutil.exit_with_error(e1)
    except OSError as e:
        if e.errno == errno.EEXIST:
            logger.error("Cannot read config file %s", config_file)
            tutil.exit_with_error(e)
        else:
            raise
    return global_config


def main():
    # let ctrl-c work as it should.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    global logger
    logger = tutil.setup_logging("filefetcher errors")
    multiprocessing_logging.install_mp_handler()

    global global_config
    global_config = tutil.parse_config(tutil.get_env_var(CONFIG_FILE_ENV))

    volcview_status = get_volcview_status()
    check_volcview(volcview_status)

    sensor_ages = get_sensor_ages(volcview_status)
    check_sensors(sensor_ages)

    logger.debug("That's all for now, bye.")
    logging.shutdown()


if __name__ == '__main__':
    main()
