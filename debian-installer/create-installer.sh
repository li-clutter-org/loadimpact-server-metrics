#!/bin/sh

die() {
  echo $1
  exit 1
}

[ -d "src" ] || die "Cant find src/ directory. Please run this script from the debian-installer/ directory."

# Source files
CONTROL="src/DEBIAN/control"
AGENT_FILES="li_metrics_agent.py README LICENSE socket27.py httplib27.py"
AGENT_CONF_SAMPLE="li_metrics_agent.conf.sample"

VERSION=`grep ^Version: ${CONTROL} |awk {print $2}`

TARGET="li_metrics_agent-${VERSION}_all"
MD5SUMS="${TARGET}/DEBIAN/md5sums"

[ -d ${TARGET} ] && die "${TARGET} directory exists!  Update version number in ${CONTROL} maybe?"

# Make build directory
mkdir ${TARGET} || die "Failed to create ${TARGET} directory. Do you have permissions?"

# Copy /usr/lib files
mkdir -p ${TARGET}/usr/lib/li_metrics_agent || die "Failed to make directories under ${TARGET}/usr/lib"
cp ${AGENT_FILES} ${TARGET}/usr/lib/li_metrics_agent || die "Failed to copy files to ${TARGET}/usr/lib"

# Copy /etc files
cp -r src/etc ${TARGET}/etc || die "Failed to copy src/etc files to ${TARGET}/etc"
cp -r ${AGENT_CONF_SAMPLE} ${TARGET}/etc/li_metrics_agent/${AGENT_CONF_SAMPLE} || die "Failed to copy ${AGENT_CONF_SAMPLE} to ${TARGET}/etc/li_metrics_agent"

# Copy /DEBIAN files
cp -r src/DEBIAN ${TARGET}/DEBIAN || die "Failed to copy src/DEBIAN files to ${TARGET}/DEBIAN"

# Generate checksum file
md5sum `find ${TARGET} -type f | grep -v '^[.]/DEBIAN/'` |tee ${MD5SUMS}

# Generate Installed-Size value for control file
SIZE=`du ${TARGET} |tail -1 |awk '{print $1}'`
sed 's/^Installed-Size:.*/Installed-Size: '"${SIZE}/" src/DEBIAN/control >${CONTROL}

# Create package
dpkg-deb -b ${TARGET}


