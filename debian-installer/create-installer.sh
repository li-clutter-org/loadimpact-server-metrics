#!/bin/sh

die() {
  echo $1
  exit 1
}

[ -d "src" ] || die "Cant find src/ directory. Please run this script from the debian-installer/ directory."

# Source files
CONTROL="src/DEBIAN/control"
AGENT_FILES="../li_metrics_agent.py ../README ../LICENSE ../socket27.py ../httplib27.py"
AGENT_CONF_SAMPLE="../li_metrics_agent.conf.sample"
INIT_D_FILE="src/etc/init.d/li_metrics_agent"
INSTALLSCRIPTS="src/DEBIAN/preinst src/DEBIAN/postinst"

VERSION=`grep ^Version: ${CONTROL} |awk '{print $2}'`

TARGET="li_metrics_agent-${VERSION}_all"
MD5SUMS="${TARGET}/DEBIAN/md5sums"

[ -d ${TARGET} ] && die "${TARGET} directory exists!  Update version number in ${CONTROL} maybe?"

# Make build directory
mkdir ${TARGET} || die "Failed to create ${TARGET} directory. Do you have permissions?"

# Make subdirs
mkdir ${TARGET}/usr || die "Failed to create ${TARGET}/usr directory. Do you have permissions?"
mkdir ${TARGET}/usr/lib || die "Failed to create ${TARGET}/usr/lib directory. Do you have permissions?"
mkdir ${TARGET}/usr/lib/li_metrics_agent || die "Failed to create ${TARGET}/usr/lib/li_metrics_agent directory. Do you have permissions?"
mkdir ${TARGET}/etc || die "Failed to create ${TARGET}/etc directory. Do you have permissions?"
mkdir ${TARGET}/etc/init.d || die "Failed to create ${TARGET}/etc/init.d directory. Do you have permissions?"
mkdir ${TARGET}/etc/li_metrics_agent || die "Failed to create ${TARGET}/etc/li_metrics_agent directory. Do you have permissions?"
mkdir ${TARGET}/DEBIAN || die "Failed to create ${TARGET}/DEBIAN directory. Do you have permissions?"

# Copy /usr/lib files
cp ${AGENT_FILES} ${TARGET}/usr/lib/li_metrics_agent || die "Failed to copy files to ${TARGET}/usr/lib/li_metrics_agent"

# Copy /etc files
cp ${INIT_D_FILE} ${TARGET}/etc/init.d || die "Failed to copy ${INIT_D_FILE} file to ${TARGET}/etc/init.d"
cp ${AGENT_CONF_SAMPLE} ${TARGET}/etc/li_metrics_agent || die "Failed to copy ${AGENT_CONF_SAMPLE} to ${TARGET}/etc/li_metrics_agent"

# Copy /DEBIAN files (except control, generated below)
cp ${INSTALLSCRIPTS} ${TARGET}/DEBIAN || die "Failed to copy ${INSTALLSCRIPTS} files to ${TARGET}/DEBIAN"

# Generate checksum file
cd ${TARGET}
md5sum `find . -type f | grep -v '^[.]/DEBIAN/'` |tee DEBIAN/md5sums
cd ..

# Generate Installed-Size value for control file
SIZE=`du ${TARGET} |tail -1 |awk '{print $1}'`

# Generate control file
sed 's/^Installed-Size:.*/Installed-Size: '"${SIZE}/" src/DEBIAN/control >${TARGET}/DEBIAN/control

# Create package
dpkg-deb -b ${TARGET}


