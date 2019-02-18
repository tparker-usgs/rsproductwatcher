#!/usr/bin/env python3
#
# I waive copyright and related rights in the this work worldwide
# through the CC0 1.0 Universal public domain dedication.
# https://creativecommons.org/publicdomain/zero/1.0/legalcode
#
# Author(s):
#   Tom Parker <tparker@usgs.gov>

""" Keep an eye on RS product generation."""

from datetime import datetime
import signal
import logging
import pathlib
import errno
import smtplib
import http.client
import re

import ruamel.yaml
import tomputils.util as tutil
import requests
from rsproductwatcher.sensor import sensor_factory
from rsproductwatcher import logger
from rsproductwatcher.util import send_email

CONFIG_FILE_ENV = 'PRODUCT_WATCHER_CONFIG'


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


def check_sensor(sensor_config, volcview_age):
    if sensor_config['disabled']:
        logger.info("Sensor %s is disabled, skipping.", sensor_config['name'])
        return

    if volcview_age < sensor_config['limit']:
        logger.info("%s is healthy. (%f hrs)", sensor_config['name'],
                    volcview_age)
        return

    sensor = sensor_factory(sensor_config)
    upstream_age = sensor.get_upstream_age()
    if upstream_age > sensor_config['limit']:
        logger.info("%s upstream data processing problem",
                    sensor_config['name'])
        message = "Subject: {name} outage upstream\n\n" \
                  "The most recent {name} image upstream is {age} hours old." \
                  "\n\nupstream source: {source}"
        message = message.format(name=sensor_config['name'], age=upstream_age,
                                 source=sensor_config['source'])
    else:
        logger.info("%s data processing problem on avors2",
                    sensor_config['name'])
        message = "Subject: {name} data processing problem\n\n" \
                  "Most recent {name} image in volcview is {age} hours old, " \
                  "while there is more recent data upstream " \
                  "({upstream_age} hrs). "
        message = message.format(name=sensor_config['name'], age=volcview_age,
                                 upstream_age=upstream_age)

    send_email(sensor_config['watchers'], message)


def check_sensors(sensor_ages):
    for sensor in global_config['sensors']:
        check_sensor(sensor, sensor_ages[sensor['name']])


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
