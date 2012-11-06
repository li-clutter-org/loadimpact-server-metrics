#!/bin/sh

VERSION="1.0-1"
TARGET="li_metrics_agent-${VERSION}_all"
CONTROL="${TARGET}/DEBIAN/control"
MD5SUMS="${TARGET}/DEBIAN/md5sums"

[ -d ${TARGET} ] || ( echo "No $TARGET directory" ; exit 1 )

md5sum `find ${TARGET} -type f | grep -v '^[.]/DEBIAN/'` |tee ${MD5SUMS}

SIZE=`du ${TARGET} |tail -1 |awk '{print $1}'`

TMP=/tmp/control.$$
sed 's/^Installed-Size:.*/Installed-Size: '"${SIZE}/" ${CONTROL} >${TMP}
sed 's/^Version:.*/Version: '"${VERSION}/" ${TMP} >${CONTROL}
rm $TMP

dpkg-deb -b ${TARGET}


