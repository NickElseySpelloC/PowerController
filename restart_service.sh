sudo systemctl stop LightingControl

#!/usr/bin/env bash

SERVICE="PowerController"

usage() {
	echo "Usage: $0 {start|stop|restart}"
	exit 1
}

if [ $# -ne 1 ]; then
	usage
fi

case "$1" in
	start)
		sudo systemctl start "$SERVICE"
		;;
	stop)
		sudo systemctl stop "$SERVICE"
		;;
	restart)
		sudo systemctl stop "$SERVICE"
		sudo systemctl start "$SERVICE"
		;;
	*)
		usage
		;;
esac
