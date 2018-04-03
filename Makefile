#
# Copyright (c) 2018, James C. McPherson. All rights reserved
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


# This Makefile drives the packaging and installation of the jfymonitor
# script on Solaris 11.4.

# A really useful tip from
# http://blog.jgc.org/2015/04/the-one-line-you-should-add-to-every.html

print-%: ; @echo $*=$($*)



# Installing the components on a live system requires root privileges

PROTO =		proto
SHEETDIR =	usr/lib/webui/analytics/sheets/site
STATDIR =	usr/lib/sstore/metadata/json/site
COLLDIR =	usr/lib/sstore/metadata/collections
JFYDIR =	var/.migrate/jfy
JFYLIBDIR =	usr/lib/jfy
MANIFESTDIR =	lib/svc/manifest/site
SVCDIR =	lib/svc/method

DIRS =		$(SHEETDIR:%=proto/%) \
		$(STATDIR:%=proto/%) \
		$(MANIFESTDIR:%=proto/%) \
		$(SVCDIR:%=proto/%) \
		$(JFYDIR:%=proto/%) \
		$(JFYLIBDIR:%=proto/%) \
		$(COLLDIR:%=proto/%) \
		repo


PKGFMT =	/usr/bin/pkgfmt
PKGLINT =	/usr/bin/pkglint
PKGREPO =	/usr/bin/pkgrepo
PKGSEND =	/usr/bin/pkgsend
PYLINT27 =	/usr/bin/pylint-2.7
PYLINT34 =	/usr/bin/pylint-3.4

INSTALL =	/usr/sbin/install
INS.file =	$(INSTALL) -f $(@D) -m $(FILEMODE) $<
MKDIR =		/usr/bin/mkdir
MV =		/usr/bin/mv
RM =		/usr/bin/rm
SOLJSONV =	/usr/bin/soljsonvalidate
SOLJVARGS =	/usr/lib/webui/analytics/sheets/analytics-import.schema.json
XMLLINT =	/usr/bin/xmllint

SRCS =		jfymonitor.py jfyDefinitions.py
STATS =		class.app.solar.jfy.json stat.app.solar.jfy.json
SHEET =		JFYInverter.json
COLLECTION =	solar.jfy.json
MANIFEST =	jfy.xml
SVC =		svc-jfy.py
PKGMF =		jfy.p5m
TEXTS =		LICENSE Acknowledgements.md README.md

JFYS =		$(SRCS:%=$(JFYLIBDIR)/%) $(TEXTS:%=$(JFYDIR)/%)
SMFS =		$(MANIFEST:%=$(MANIFESTDIR)/%) $(SVC:%=$(SVCDIR)/%)
BUI =		$(SHEET:%=$(SHEETDIR)/%)
SSTORE =	$(STATS:%=$(STATDIR)/%) $(COLLECTION:%=$(COLLDIR)/%)

PRODUCT_1 =	$(JFYS) $(SMFS) $(BUI) $(SSTORE)
PRODUCT =	$(PRODUCT_1:%=proto/%)

LINTS =		$(SRCS:%=%.lint) \
		$(STATS:%=%.lint) \
		$(SHEET:%=%.lint) \
		$(COLLECTION:%=%.lint) \
		$(SVC:%=%.lint) \
		$(MANIFEST:%=%.lint)

# FILEMODE target-assigned variable override
FILEMODE = 0444
proto/$(JFYDIR)/%.py \
proto/$(SVCDIR)/%	:= FILEMODE=0555



# Prior to installing the components, we need to validate them
# with the various lint utilities

install:	lint proto $(PRODUCT)
pkg:		install

lint:		$(LINTS) fmt


j%.py.lint:	j%.py
	-$(PYLINT34) $<

# If we had a Python3 SMF include, this rule would be unnecessary
# and we just have one pylint rule
svc%.lint:	$(SVC)
	-$(PYLINT27) $<

%.json.lint:	%.json
	$(SOLJSONV) $(SOLJVARGS) $<

fmt:	$(PKGMF)
	$(PKGFMT) -c $(PKGMF)

%.xml.lint:	%.xml
	$(XMLLINT) --noout $<


proto:	$(DIRS)

$(DIRS):
	$(MKDIR) -p $@


proto/$(SHEETDIR)/%:		%	; $(INS.file)
proto/$(STATDIR)/%:		%	; $(INS.file)
proto/$(COLLDIR)/%:		%	; $(INS.file)
proto/$(JFYDIR)/%:		%	; $(INS.file)
proto/$(JFYLIBDIR)/%:		%	; $(INS.file)
proto/$(MANIFESTDIR)/%:		%	; $(INS.file)

# Special handling, because we rename the service method script
proto/$(SVCDIR)/%:		%
	$(INS.file)
	$(MV) $@ $(@:%.py=%)


package:	pkg
	$(PKGREPO) create -s repo
	$(PKGREPO) add-publisher -s repo JMCP
	$(PKGSEND) publish -s repo -d proto $(PKGMF)

clean:
	-$(RM) -rf proto repo __pycache__
