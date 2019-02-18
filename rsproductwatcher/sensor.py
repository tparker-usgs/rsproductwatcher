#!/usr/bin/env python3
#
# I waive copyright and related rights in the this work worldwide
# through the CC0 1.0 Universal public domain dedication.
# https://creativecommons.org/publicdomain/zero/1.0/legalcode
#
# Author(s):
#   Tom Parker <tparker@usgs.gov>

""" encapsulate sensor details. """

import http.client
from datetime import datetime
import re

import requests
from rsproductwatcher.util import send_email
from rsproductwatcher import logger

MODIS_DATE_RE = r"\.(\d{5}\.\d{4})\.modis"
MODIS_DATE_STR = "%y%j.%H%M"

AVHRR_DATE_RE = r"\.(\d{5}\.\d{4})/n"
AVHRR_DATE_STR = "%y%j.%H%M"

VIIRS_DATE_RE = r"(_d\d{8}_t\d{6})\d_e"
VIIRS_DATE_STR = "_d%Y%m%d_t%H%M%S"


class Sensor(object):
    """ A single type of sensor """

    def __init__(self, date_re, date_str, config):
        self.config = config
        self.date_re = date_re
        self.date_str = date_str

    def get_upstream_age(self):
        file_list = get_gina_list(self.config['url'], self.config['watchers'])

        if file_list is None:
            return

        pattern = re.compile(self.date_re)
        most_recent = datetime(2000, 1, 1, 12)
        for date in re.findall(pattern, file_list):
            most_recent = max(most_recent,
                              datetime.strptime(date, self.date_str))

        age = (datetime.utcnow() - most_recent).total_seconds() / (60 * 60)

        logger.info("Most recent %s image at GINA: %s (%f hours old)",
                    self.config['name'], most_recent, age)

        return age


class AvhrrSensor(Sensor):
    """ AVHRR """

    def __init__(self, *args, **kwargs):
        super().__init__(AVHRR_DATE_RE, AVHRR_DATE_STR, *args, **kwargs)


class ModisSensor(Sensor):
    """ MODIS """

    def __init__(self, *args, **kwargs):
        super().__init__(MODIS_DATE_RE, MODIS_DATE_STR, *args, **kwargs)


class ViirsSensor(Sensor):
    """ VIIRS """

    def __init__(self, *args, **kwargs):
        super().__init__(VIIRS_DATE_RE, VIIRS_DATE_STR, *args, **kwargs)


def get_gina_list(url, watchers):
    resp = requests.get(url)
    if resp.status_code != requests.codes.ok:
        message = "Subject: CRITICAL error at GINA\n\n" \
                  + "Cannot retrieve file list from {}." \
                  + " Received response code {} ({})."
        message = message.format(url, resp.status_code,
                                 http.client.responses[resp.status_code])
        send_email(watchers, message)

    return resp.text


def sensor_factory(sensor):
    if sensor['name'] == 'VIIRS':
        return ViirsSensor(sensor)
    elif sensor['name'] == 'AVHRR':
        return AvhrrSensor(sensor)
    elif sensor['name'] == 'MODIS':
        return ModisSensor(sensor)
