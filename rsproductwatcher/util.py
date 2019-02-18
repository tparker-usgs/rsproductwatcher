#!/usr/bin/env python3
#
# I waive copyright and related rights in the this work worldwide
# through the CC0 1.0 Universal public domain dedication.
# https://creativecommons.org/publicdomain/zero/1.0/legalcode
#
# Author(s):
#   Tom Parker <tparker@usgs.gov>

""" utilities """


import tomputils.util as tutil
from rsproductwatcher import logger
import smtplib


def send_email(recipient, message):
        mailhost = tutil.get_env_var('MAILHOST', default="unset")

        if mailhost == "unset":
            logger.info("Skipping email, mailhost is undefined.")
            logger.info(message)
        else:
            logger.info("Sending email to {}".format(recipient))
            server = smtplib.SMTP(mailhost)
            server.sendmail(tutil.get_env_var('LOG_SENDER'), recipient,
                            message)
            server.quit()
