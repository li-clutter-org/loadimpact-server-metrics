#!/bin/bash

# Packages version and iteration
version=1.1
iteration=1
package_name=li-metrics-agent

lib_dir=/usr/lib/li_metrics_agent
bin_dir=/usr/bin
conf_dir=/etc/li_metrics_agent


serv_dir=/etc/init.d
upstart_dir=/etc/init
systemd_dir=/lib/systemd/system

# modify package_name for development branch
if [[ $CIRCLE_BRANCH = "develop" ]]; then
  echo $(date)
  package_name+="-dev"
  iteration+=".$(date +%Y%m%d.%H%M)"
fi

# Create and deploy .deb package
deb_file_name="${package_name}_${version}-${iteration}_all.deb"
rpm_file_name="${package_name}-${version}-${iteration}.noarch.rpm"


# Upstart (Ubuntu 12-04, Ubuntu 14-04, Centos 6)
for package_type in deb rpm; do

  fpm -s dir -t ${package_type} \
  --name ${package_name} \
  --version ${version} --iteration ${iteration} --architecture all \
  --before-install preinst \
  ../li_metrics_agent.py=${lib_dir}/li_metrics_agent.py \
  ../httplib27.py=${lib_dir}/httplib27.py  \
  ../socket27.py=${lib_dir}/socket27.py \
  ../README.md=${lib_dir}/README.md \
  ../LICENSE=${lib_dir}/LICENSE \
  ../li_metrics_agent.conf.sample=${conf_dir}/li_metrics_agent.conf.sample \
  li-metrics-agent-config=${bin_dir}/li-metrics-agent-config \
  li-metrics-agent-run=${bin_dir}/li-metrics-agent-run \
  upstart/li_metrics_agent.conf=${upstart_dir}/li_metrics_agent.conf \
  upstart/li-metrics-agent-reload=${bin_dir}/li-metrics-agent-reload

done

package_cloud push loadimpact/server-metrics-agent/ubuntu/precise ${deb_file_name}
package_cloud push loadimpact/server-metrics-agent/ubuntu/trusty ${deb_file_name}
package_cloud push loadimpact/server-metrics-agent/el/6 ${rpm_file_name}

rm deb_file_name
rm rpm_file_name

# SYSTEMD (Ubuntu 16-04, Centos 7)
for package_type in deb rpm; do

  fpm -s dir -t ${package_type} \
  --name ${package_name} \
  --version ${version} --iteration ${iteration} --architecture all \
  --before-install preinst \
  ../li_metrics_agent.py=${lib_dir}/li_metrics_agent.py \
  ../httplib27.py=${lib_dir}/httplib27.py  \
  ../socket27.py=${lib_dir}/socket27.py \
  ../README.md=${lib_dir}/README.md \
  ../LICENSE=${lib_dir}/LICENSE \
  ../li_metrics_agent.conf.sample=${conf_dir}/li_metrics_agent.conf.sample \
  li-metrics-agent-config=${bin_dir}/li-metrics-agent-config \
  li-metrics-agent-run=${bin_dir}/li-metrics-agent-run \
  systemd/li_metrics_agent.service=${systemd_dir}/li_metrics_agent.service \
  systemd/li-metrics-agent-reload=${bin_dir}/li-metrics-agent-reload

done

package_cloud push loadimpact/server-metrics-agent/ubuntu/xenial ${deb_file_name}
package_cloud push loadimpact/server-metrics-agent/el/7 ${rpm_file_name}

