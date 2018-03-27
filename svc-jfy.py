#!/usr/bin/python2.7

#
# Copyright (c) 2018, James C. McPherson. All rights reserved
#

#
# start and stop methods for the JFY inverter monitoring daemon
#

# We're forced to use Python 2.7 at present, due to a lack of
# Python3 bindings for SMF. Grrrr.
from __future__ import print_function

import os
import re
import smf_include
import subprocess
import sys


SVCPROP = "/usr/bin/svcprop"
CFGFNAME = "/var/share/jfy/cfg"
LOGPATH = "/var/share/jfy/log"

GLOBAL_SECT = """
[global]
usesstore={0}

"""

# IF we find the apikey, sysid or logpath properties, then
# we add them
INVERTER_SECT = """
[inverter-{0}]
devname={1}
"""

APISYSID = """pvoutput_apikey={0}
pvoutput_sysid={1}
"""


def start():
    """ SMF start method """

    # Set up configuration options
    (cfgfile, debug) = get_options()
    cfgf = open(CFGFNAME, "w", buffering=True)
    cfgf.write(cfgfile)
    cfgf.close()

    args = ["/var/share/jfy/jfymonitor.py", "-F", CFGFNAME]
    args.append("-l")
    args.append(LOGPATH)
    if debug:
        args.append("-d")

    print("args: {0}".format(args), file=sys.stderr)
    try:
        subprocess.check_call(args, stdout=sys.stdout, stderr=sys.stderr)
    except subprocess.CalledProcessError as err:
        if err.returncode == 1:
            # No valid instances to monitor
            smf_include.smf_method_exit(
                smf_include.SMF_EXIT_TEMP_DISABLE,
                "nothing_to_monitor",
                "Configuration provided for monitoring is invalid")
        else:
            print("Internal Error while executing {0}: {1}".format(args, err),
                  file=sys.stderr)
            return smf_include.SMF_EXIT_ERR_FATAL

    return smf_include.SMF_EXIT_OK


def get_options():
    """ Retrieve SMF global options """
    fmri = os.getenv("SMF_FMRI")
    if fmri is None:
        # should not be possible
        print("SMF_FMRI is None: script must be invoked as SMF method",
              file=sys.stderr)
        return smf_include.SMF_EXIT_ERR_CONFIG

    # For now we are only getting the FMRI list from the properties
    try:
        instances = subprocess.check_output(
            ["/usr/bin/svcprop", "-g", "inverter", fmri]).splitlines()
        usesstore = subprocess.check_output(
            ["/usr/bin/svcprop", "-p", "config/usesstore",
             fmri]).splitlines()[0]
    except subprocess.CalledProcessError as err:
        print("Error occurred w/ svcprop: '{0}': '{1}'".format(
            fmri, err), file=sys.stderr)
        return smf_include.SMF_EXIT_ERR_FATAL

    try:
        debug = subprocess.check_output(
            ["/usr/bin/svcprop", "-p", "config/debug", fmri]).splitlines()[0]
    except subprocess.CalledProcessError as err:
        debug = False

    inst_re = re.compile(r"([-\w]+)/([-\w]+) ([\w]+) ([\.-:/\w]+)")
    inverters = {}
    for line in instances:
        (inst, varname, _vtype, value) = inst_re.match(line.decode()).groups()
        if not inverters.get(inst):
            inverters[inst] = {}
        inverters[inst][varname] = value

    # Construct the config file
    cfgfile = GLOBAL_SECT.format(usesstore) + "\n"
    print(inverters)
    for inum, iname in enumerate(inverters):
        cfgfile = cfgfile + INVERTER_SECT.format(
            inum, inverters[iname]['devname'])
        apik = inverters[iname].get('pvoutput_apikey')
        sysid = inverters[iname].get('pvoutput_sysid')
        logp = inverters[iname].get('logpath')

        if apik and sysid:
            cfgfile = cfgfile + APISYSID.format(apik, sysid)
        if logp:
            cfgfile = cfgfile + "logpath={0}".format(logp)
        cfgfile = cfgfile + "\n"

    return (cfgfile, debug)


smf_include.smf_main()
