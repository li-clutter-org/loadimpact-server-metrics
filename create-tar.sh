#!/bin/sh

VERSION="1.1"

TMP="/tmp/li-metrics-agent"
TMP_FILE="/tmp/li-metrics-agent_${VERSION}.tar.gz"

mkdir ${TMP}

# Copy files from server metrics directory
cp -r `ls -A *.py | grep -v *service*` ${TMP}
cp README* ${TMP}
cp LICENSE ${TMP}
cp requirements.txt ${TMP}
cp li_metrics_agent.conf* ${TMP}
cp ${TMP}/li_metrics_agent.conf.sample ${TMP}/li_metrics_agent.conf

# Tar tmp dir
cd /tmp
tar -czf ${TMP_FILE} li-metrics-agent
cd -

cp ${TMP_FILE} .

rm -rf ${TMP} ${TMP_FILE}
