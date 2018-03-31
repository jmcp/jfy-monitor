#! /usr/bin/python3.4

#
# Copyright (c) 2013, 2018 James C. McPherson.  All Rights Reserved
#
#

#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

#  ACKNOWLEDGEMENTS:
#
#  This utility builds upon the work known as Solarmonj,
#  <https://code.google.com/p/solarmonj/> by John Croucher
#  (<http://jcroucher.com>)
#
#  This utility depends on the JFY serial protocol document
#  found at http://www.fergo.net/JFY-REVISED.pdf, as noted
#  in http://forums.whirlpool.net.au/forum-replies.cfm?t=1899721.
#  An alternate location for this file is
#  https://github.com/johnf/jfy/blob/master/doc/JFY-REVISED.pdf
#

"""
This utility monitors JFY SunTwins inverters. While it is unlikely
that you would have more than one of these attached to your system,
this utility is written to enable multiple-instance monitoring.

Data is stored locally, and uploaded to either or both
pvoutput.org and a Solaris Analytics stats store instance.

If running on Solaris, then configuration details are stored in SMF
and the start method script (running as user "jfy") extracts those
SMF properties to a config file in /system/volatile.

If running on other OSes, then configuration details are stored in
/etc/jfy/config using standard Python ConfigParser syntax.


The required sections and fields are as follows (note that $N should
be incremented for each inverter that you want to monitor with this
utility):

[global]
usesstore= True / False

[inverter-$N]
devname= device path to access the inverter (eg /dev/term/a)
pvout_sysid= PVoutput.org system id for this inverter
pvout_apikey= PVoutput.org api key for this inverter


Note that you may specify a per-inverter logfile path if desired,
by adding a

logpath=

field to an [inverter-$N] section.

----
External dependency: [pySerial][https://pypi.python.org/pypi/pyserial]
"""

import configparser
import datetime
import getopt
import os

import platform

import struct
import sys
import threading
import time
import urllib.parse
import urllib.request

# This is in what appears to be the wrong spot from pylint's point
# of view - but only because pyserial is installed in $HOME rather
# than system-delivered.
import serial
from serial import serialposix

from jfyDefinitions import (CtrlCodes, UnsupportedOpCodes, RegisterCodes,
                            ReadCodes, jfyHeader, jfyEnder, jfyAck, APid,
                            bcast, JFYData, JFYDivisors, JFYEmpty,
                            RESOURCE_SSID_PREFIX, STATS, SERVICEURL,
                            charset)


# This is a little bit ugly
OSNAME, HOST, BIGREL, DETREL = platform.uname()[0:4]
if OSNAME == "SunOS":
    if DETREL.startswith("11.4"):
        from libsstore import SStore, SSException


# Process-wide mapping of inverter serial number to id
_INVERTER_MAP = {1: "application"}

USAGE_STMT = """

$ jfymonitor -F /path/to/cfg/file -l /path/to/logfiles [-x code] [-od]

    -d provide debug output from various functions
    -F /path/to/config/file
    -o oneshot (do not daemonize)
    -l /path/to/logfile/hierarchy
    -x hex   run this specific Read Code and output to stdout **

    logpath may be inverter-specific, by serial number
    ** not implemented yet.
"""


# global functions
def usage(do_exit=False):
    """ Provides the usage statement for the utility """
    # -d debug output from various functions
    # -F /path/to/config/file
    # -o oneshot (do not daemonize)
    # -l /path/to/logfile/hierarchy
    # -x hex   run this specific Read Code and output to stdout
    # logpath may be inverter-specific, by serial number
    print(USAGE_STMT, file=sys.stderr)
    if do_exit:
        sys.exit(1)


def getline(stats=None):
    """
    Formats a result line (in CSV) for writing to a logfile. We return the
    line in data-natural order, unlike solarmonj. This function applies the
    divisors in JFYDivisors to return scaled data.
    """
    tstamp = datetime.date.strftime(datetime.datetime.now(),
                                    "%Y-%m-%dT%H:%M:%S")
    line = tstamp
    for idx, fname in enumerate(JFYData):
        line = line + "," + "{0}".format(stats[fname] / JFYDivisors[idx])
    line = line + "\n"
    return line


def checksum(packet=None, verify=False):
    """ Creates and verifies a packet checksum """
    rdict = {}
    if verify:
        # Use network byte order and just grab the last 2 bytes.
        pval = struct.unpack("!H", packet[-2:])[0]
        tval = 1 + (sum(packet[:-2]) ^ 0xffff)
        if tval == pval:
            rdict['ok'] = True
        else:
            rdict['ok'] = False
            rdict['expected'] = tval
    else:
        tval = 1 + (sum(packet) ^ 0xffff)
    rdict['value'] = [tval >> 8, tval & 0x00ff]
    return rdict


def decode_pkt(bytestream):
    """
    Breaks packet down into components, returns a dict of the
    inverter address, ctrl code, function code, data length and
    data.
    """
    # Use network byte order
    try:
        predata = struct.unpack('!H5B', bytestream[0:7])
    except struct.error as _err:
        # We need to handle this up the call stack
        return None

    datalen = predata[5]
    rval = {}
    rval['src'] = predata[1]
    rval['dest'] = predata[2]
    rval['ctrl'] = predata[3]
    jumper = {}
    if predata[3] == 0x30:
        jumper = RegisterCodes
    elif predata[3] == 0x31:
        jumper = ReadCodes
    else:
        jumper = UnsupportedOpCodes
    # if we're seeing Write or Execute, this gives us None, which is ok.
    rval['func'] = jumper.get(predata[4])
    rval['dlen'] = datalen
    data = list(struct.unpack_from("!{0}B".format(datalen), bytestream, 7))
    rval['pktdata'] = data
    rval['chksum'] = checksum(bytestream[:-2], verify=True)
    if not rval['chksum']['ok']:
        print("checksum invalid ({0} {1}, expected {2})".format(
            hex(rval['chksum']['value'][0]), hex(rval['chksum']['value'][1]),
            hex(rval['chksum']['expected'])))
    return rval


def create_pkt(src, dest, ctrl, func, data):
    """
    Returns binary packet. The examples provided in the spec describe
    the functions that we need to use.
    """
    prepkt = []
    prepkt.extend(jfyHeader)
    prepkt.extend([src])
    prepkt.extend([dest])
    prepkt.extend([ctrl])
    prepkt.extend([func])
    if data:
        prepkt.extend([len(data)])
        prepkt.extend(data)
    else:
        prepkt.extend([0])
    csum = checksum(prepkt, False)
    prepkt.extend(csum['value'])
    prepkt.extend(jfyEnder)
    pkt = struct.pack("{0}B".format(len(prepkt)), *prepkt)
    return pkt



class Inverter(threading.Thread):
    """ It's a collection of tubes """

    def __init__(self, inv, oneshot, debug):
        #
        # definitions we need
        self.devname = inv['devname']
        self.usesstore = inv['usesstore']
        self.apikey = inv['apikey']
        self.sysid = inv['sysid']
        self.logpath = inv['logpath']
        self.oneshot = oneshot
        self.starttime = datetime.datetime.now()
        # for rotating the logfile
        self.day = datetime.date.strftime(self.starttime, "%d")
        self.debug = debug

        # properties filled in via setup()
        self.dev = None         # file handle for the monitoring device
        self.logfile = None     # full OS path to logfile
        self.sst = None         # handle to sstored
        self.isreg = None       # are we registered with the inverter?
        self.serial = None      # inverter serial number
        self.hr_serial = None   # human-readable form of serial number
        self.idx = None          # inverter ID in the map
        self.stats = None       # stat names
        self.stats_array = None # array of stats for updating sstored
        threading.Thread.__init__(self)

    def xfer_pkt(self, bytestream):
        """
        Sends the packet out through the device and receives the
        response (if any)
        """
        for _tries in range(0, 10):
            rval = self.dev.write(bytestream)
            if rval != len(bytestream):
                print("Unable to write all of bytestream. {0} of {1} "
                      "transferred.".format(rval, len(bytestream)),
                      file=sys.stderr)
            # Inspection of the captured data files we have implies that
            # the largest packet received is 64 bytes *following* the
            # 7 bytes of header content.
            time.sleep(1)
            rpkt = self.dev.read_all()
            if len(rpkt) > 0:
                if self.debug:
                    print("response {0}".format(rpkt))
                return rpkt
        return None

    def logrotate(self):
        """
        Checks whether the logfile needs rotating (per-day), and
        rotates it if necessary
        """

        curday = datetime.date.strftime(self.starttime, "%d")

        if self.logfile is not None:
            if curday == self.day:
                if self.debug:
                    print("not rotating logfile {0}".format(self.logfile))
                    return
            else:
                self.logfile.close()
                self.day = curday

        # Can we open the logfile for writing?

        logdir = os.path.join(os.path.join(self.logpath, self.hr_serial),
                              datetime.date.strftime(self.starttime,
                                                     "%Y/%m"))
        try:
            _statbuf = os.stat(logdir)
        except FileNotFoundError as _exc:
            if self.debug:
                print("Creating toplevel logdir {0}".format(logdir))
            os.makedirs(logdir)

        logname = os.path.join(logdir, curday)
        self.logfile = open(logname, "a", buffering=1)
        if not self.logfile:
            print("Unable to open logfile {0}".format(logname))
            self.dev.close()
            self.dev = None
            return

    def query_normal_info(self):
        """ Queries the inverter for instantaneous data. """

        # We assume that the inverter is online;
        pkt = create_pkt(APid, self.idx, CtrlCodes['Read'],
                         ReadCodes['QueryNormalInfo'], data=None)

        inpkt = self.xfer_pkt(pkt)

        # Sometimes we won't get a response in after 10 tries, so
        # don't worry about it
        if not inpkt:
            return
        response = decode_pkt(inpkt)
        # Boo - didn't get a valid packet
        if not response or not response['chksum']['ok']:
            return dict(zip(JFYData, JFYEmpty))

        rvals = []
        normalinfo = response['pktdata']
        # See comment atop definition of JFYData. We return the un-scaled
        # data; our output functions handle scaling for us.
        for idx in range(0, 16, 2):
            if idx == 8 or idx == 12:
                # these are the 'ignore' fields
                continue
            rvals.append((normalinfo[idx] << 8) | normalinfo[idx+1])

        if self.debug:
            alldata = []
            for idx in range(0, len(normalinfo), 2):
                alldata.append((normalinfo[idx] << 8) | normalinfo[idx+1])
            print("alldata from pkt: {0}".format(alldata))

        return dict(zip(JFYData, rvals))

    def print_warnings(self):
        """ print SStore warnings to stderr """
        for warn in self.sst.warnings():
            print("{0}".format(warn), file=sys.stderr)

    def sstore_update(self, vals):
        """
        Updates the stats in sstored after stripping out the ignore[12]
        fields in JFYData. We're using the shared memory region method
        provided by data_attach(), so this is a very simple function.
        """
        values = {}
        for idx, fname in enumerate(JFYData):
            values[self.stats[idx]] = vals[fname] / JFYDivisors[idx]

        if self.debug:
            print("sstore updated with values {0}".format(values))
        self.sst.data_update(values)

    def pvoutput_update(self, vals):
        """
        Updates the pvoutput.org service, if the current minute is
        divisible by 5 (complies with pvoutput.org rules). Refer to
        API documentation at https://www.pvoutput.org/help.html#api-addstatus
        """
        curtime = datetime.datetime.now()
        if curtime.minute % 5 != 0:
            return
        valdata = {
            'd': curtime.strftime("%Y%m%d"),                 # date
            't': curtime.strftime("%H:%M"),                  # time
            'v1': vals['energyGenerated'] / JFYDivisors[5],  # energy
            'v2': vals['powerGenerated'] / JFYDivisors[1],   # power
            'v5': vals['temperature'] / JFYDivisors[0],      # temperature
            'v6': vals['voltageDC'] / JFYDivisors[2]         # Vdc
        }
        data = urllib.parse.urlencode(valdata)
        data = data.encode("ascii")
        req = urllib.request.Request(url=SERVICEURL, data=data)
        req.add_header("X-Pvoutput-Apikey", self.apikey)
        req.add_header("X-Pvoutput-SystemId", self.sysid)
        try:
            urllib.request.urlopen(req, data)
        except urllib.error.URLError as exc:
            print("Failed: reason {0}".format(exc.reason), file=sys.stderr)

        if self.debug:
            print("Updated pvoutput.org with valdata: {0}".format(valdata))

    def register(self):
        """ Register this utility with the inverter """
        # Per the spec:
        #
        # OfflineQuery
        # We send a broadcast packet and wait for a response:
        #     src=1, dest=0, ctrl=0x31, func=0x40, datalen=0, data=None
        #
        # RegisterRequest
        # Newly attached inverter responds with serial number as ASCII data
        #     src=0, dest=1, ctrl=0x31, func=0xbf, datalen=0xa, data=serial
        #
        # SendRegisterAddress
        # We allocate a destination ID from our map (excl 0, 0xff) and send
        # registration packet
        #     src=1, dest=0, ctrl=0x31, func=0x41, datalen=0xb, data=serial+ID
        #
        # AddressConfirm
        # Inverter sends ACK:
        #     src=N, dest=1, ctrl=0x31, func=0xbe, datalen=1, data=jfyAck
        next_inv = max(_INVERTER_MAP.keys()) + 1
        if next_inv > 253:
            print("Too many ({0} > 253) inverters attached.".format(next_inv),
                  file=sys.stderr)
            return
        pkt = create_pkt(APid, bcast, CtrlCodes['Register'],
                         RegisterCodes['ReRegister'],
                         data=None)

        inpkt = self.xfer_pkt(pkt)
        pkt = create_pkt(APid, bcast, CtrlCodes['Register'],
                         RegisterCodes['OfflineQuery'],
                         data=None)
        inpkt = self.xfer_pkt(pkt)
        response = decode_pkt(inpkt)
        if not response:
            print("Empty response from decode_pkt (1)")
            return
        # Sanity-check the packet values
        if response['src'] != 0 or \
           response['dest'] != 0 or \
           response['ctrl'] != CtrlCodes['Register'] or \
           not response['chksum']['ok']:
            # Garbage from this inverter, fail out
            print("Got garbage response (1)  {0}".format(response))
            return
        # Packet seems ok, let's build the next
        self.serial = response['pktdata']
        self.hr_serial = "".join([chr(s) for s in self.serial if s in charset])

        # remove any trailing whitespace
        self.hr_serial = self.hr_serial.strip()

        _INVERTER_MAP[next_inv] = self.hr_serial

        # We do this in two steps so that create_pkt generates things correctly
        serial_reg = self.serial
        serial_reg.append(next_inv)
        pkt = create_pkt(APid, bcast, CtrlCodes['Register'],
                         RegisterCodes['SendRegisterAddress'],
                         data=serial_reg)
        inpkt = self.xfer_pkt(pkt)
        response = decode_pkt(inpkt)
        # Sanity-check the packet values
        if not response:
            print("Empty response from decode_pkt (2)")
            return
        if response['src'] != next_inv or \
           response['dest'] != APid or \
           response['ctrl'] != CtrlCodes['Register'] or \
           not response['chksum']['ok'] or \
           response['pktdata'][0] != jfyAck:
            # Garbage from this inverter, fail out
            print("Got garbage response (2): {0}".format(response))
            return
        self.isreg = True
        self.idx = next_inv
        print("Registration succeeded for device with "
              "serial number {0} on {1}".format(self.hr_serial, self.devname))
        return

    def setup_sstore(self):
        """ Connects to sstored and performs a data_attach for the stats """
        # We need the serial number to be available before we start
        if not self.serial:
            self.usesstore = False
            return

        self.sst = SStore()
        # Unable to make a connection, operate without it
        if not self.sst:
            self.usesstore = False
            return

        hr_serial = "".join([chr(s) for s in self.serial if s in charset])
        # remove any trailing whitespace
        hr_serial = hr_serial.strip()
        # ... so we can add the resource name
        resname = RESOURCE_SSID_PREFIX + hr_serial
        try:
            self.sst.resource_add(resname)
            self.print_warnings()
        except SSException as exc:
            print("Unable to add resource {0} to sstored: {1}".format(
                resname, SSException.__str__))
            self.usesstore = False
            return

        stats = []
        for sname in STATS:
            stats.append("{0}{1}//:stat.{2}".format(
                RESOURCE_SSID_PREFIX, hr_serial, sname))
        self.stats = stats
        try:
            self.stats_array = self.sst.data_attach(stats)
            self.print_warnings()
        except SSException as exc:
            print("Unable to attach stats to sstored\n{0} / {1}".format(
                exc.message, exc.errno),
                  file=sys.stderr)
            self.usesstore = False
            self.sst.free()
            self.sst = None

    def setup(self):
        """ Performs the actual setup functions """
        #
        # Can we open the device, at 9600/8/n/1?
        try:
            self.dev = serialposix.PosixPollSerial(port=self.devname,
                                                   timeout=1, exclusive=True)
        except ValueError as valex:
            print("Unable to exclusively open {0} with default "
                  "9600/8/n/1 parameters: {1}".format(
                      self.devname, valex.args))
            return
        except serial.SerialException as serex:
            print("Received SerialException attempting to open {0}".
                  format(self.devname))
            print("{0} : {1}".format(serex.errno, serex.strerror))
            return

        # Register with the inverter
        self.register()
        if not self.isreg:
            self.logfile.close()
            self.dev.close()
            self.dev = None
            return

        # logfile checking:
        self.logrotate()

        # Using sstored?
        if self.usesstore:
            self.setup_sstore()


    def run(self):
        """ This is where we do all the work. """
        while True:
            # check whether we need to rotate the logfile
            self.logrotate()
            if not self.dev:
                return

            # query the inverter
            stats = self.query_normal_info()
            if not stats:
                continue
            if self.debug:
                print("stats {0}".format(stats))

            line = getline(stats)

            if self.logfile:
                self.logfile.write(line)

            # update sstored
            if self.usesstore:
                self.sstore_update(stats)

            # update pvoutput.org
            if self.apikey:
                self.pvoutput_update(stats)

            # shutdown if required
            if not self.oneshot:
                print("Not daemonizing")
                # flush and close the device
                self.dev.flush()
                self.dev.close()
                # break connection to sstored
                if self.sst:
                    self.sst.free()
                    self.sst = None
                # close the logfile
                if self.logfile:
                    self.logfile.close()
                    self.logfile = None
                return
            else:
                time.sleep(30)


def parseargs(arglist):
    """ Parse the provided args to instantiate our configuration """
    # Our arguments are as follows:
    # -F /path/to/config/file
    # -o oneshot (do not daemonize)
    # -l /path/to/logfile/hierarchy
    # -x hex   run this specific Read Code and output to stdout
    # logpath is inverter-specific, by serial number
    daemonize = True
    cfgfile = ""
    readcode = None
    debug = False
    lopts, extra = getopt.getopt(arglist, "dF:l:ox:")
    dopts = dict(lopts)

    if '-F' not in dopts:
        usage(True)
    else:
        cfgfile = dopts['-F']

    if '-l' not in dopts:
        usage(True)
    else:
        logpath = dopts['-l']
    if len(extra) > 0:
        usage(True)

    if '-o' in dopts:
        daemonize = False
    if '-x' in dopts:
        readcode = dopts['-x']
        daemonize = False

    if '-d' in dopts:
        debug = True

    return cfgfile, logpath, daemonize, readcode, debug


def parse_cfg(cfgfile, logpath):
    """ Parse the configuration file """
    cfg = configparser.ConfigParser()
    cfg.read(cfgfile)
    if len(cfg.sections()) < 2 or not cfg["global"]:
        # Not enough sections
        print("Supplied configuration file {0} is incorrectly formed:\n"
              "no [global] section found".format(cfgfile), file=sys.stderr)
    usesstore = cfg['global']['usesstore'] or False
    # Now to deal with the inverters
    cfg.remove_section("global")
    rlist = list()
    for invsect in cfg.sections():
        inv = {}
        inv['usesstore'] = usesstore
        inv['devname'] = cfg[invsect]['devname']
        if cfg.has_option(invsect, "pvoutput_apikey"):
            inv['apikey'] = cfg[invsect]['pvoutput_apikey']
        else:
            inv['apikey'] = None
        if cfg.has_option(invsect, "pvoutput_sysid"):
            inv['sysid'] = cfg[invsect]['pvoutput_sysid']
        else:
            inv['sysid'] = None
        if cfg.has_option(invsect, "logpath"):
            inv['logpath'] = cfg[invsect]['logpath']
        else:
            inv['logpath'] = logpath
        rlist.append(inv)
    return rlist


def main():
    """ The utility proper starts here """

    cfgfile, logpath, oneshot, readcode, debug = parseargs(sys.argv[1:])

    if readcode:
        print("The -x option is not supported yet")
        sys.exit(1)

    attached = parse_cfg(cfgfile, logpath)
    thrlist = []
    for inv in attached:
        thrlist.append(Inverter(inv, oneshot, debug))

    if len(thrlist) > 0:
        for thr in thrlist:
            thr.setup()
            if not thr.isreg:
                # didn't get registration
                print("Registration failed, removing thr {0}".format(thr))
                thrlist.remove(thr)
                continue
            thr.setName("inverter-" + thr.hr_serial)

    if debug:
        print("Inverter map:")
        for index in _INVERTER_MAP:
            print("id {0:3}: {1}".format(index, _INVERTER_MAP[index]))

    if len(thrlist) > 0:
        try:
            _pid = os.fork()
        except OSError as err:
            print("Error encountered when forking jfymonitor process: "
                  "{0}".format(err))
        if _pid == 0:
            # Child process (run threads)
            for _thr in thrlist:
                _thr.run()
    else:
        print("No inverters passed registration for monitoring",
              file=sys.stderr)
        # SMF_ERR_EXIT_CONFIG
        sys.exit(96)

    sys.exit(0)

if __name__ == "__main__":
    main()
