
This utility monitors [JFY][JFY home] SunTwins inverters, specifically
the JFY-5000. While it is unlikely that you would have more than one of
these attached to your system, this utility is written to enable
multiple-instance monitoring. 

Data is stored locally, and uploaded to either or both
[pvoutput.org][pvoutput.org] and a
[Solaris Analytics][Solaris Analytics] stats store instance.

If running on **Solaris**, then configuration details are stored in SMF
and the start method script (running as user "jfy") extracts those
SMF properties to a config file in `/system/volatile`.

If running on other OSes, then configuration details are stored in
`/etc/jfy/config` using standard Python ConfigParser syntax.


The required sections and fields are as follows (note that $N should
be incremented for each inverter that you want to monitor with this
utility):

    [global]
    usesstore= True / False

    [inverter-$N]
    devname= device path to access the inverter (eg /dev/term/a)
    pvout_sysid= PVoutput.org system id for this inverter
    pvout_apikey= PVoutput.org api key for this inverter
    logpath= path to logfiles for this inverter, if different to the default.


There is one external dependency: [pySerial][pySerial]

This project is offered under the terms of the GPLv3. Please review
[LICENSE][LICENSE] for details.

Please review [Acknowledgements][Acks].

----

  [JFY home]: http://jfytech.com.au
  [pvoutput.org]: https://pvoutput.org
  [Solaris Analytics]: https://blogs.oracle.com/jmcp/solaris-analytics%3a-an-overview
  [pySerial]: https://pypi.python.org/pypi/pyserial
  [LICENSE]: LICENSE.md
  [Acks]: Acknowledgements.md
