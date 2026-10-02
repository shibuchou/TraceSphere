#!/usr/bin/env bash
set -u
LOG=/usr/local/zstack/apache-tomcat-8.5.99/logs/management-server.log
echo "== attach network service 任务流 =="
grep -a "e19cb27fc0ed466fa2719428410ad260" "$LOG" | grep -aE "FlowChain|flow\[|error|Error" | tail -25
echo
echo "== 近期 dhcp 应用相关 =="
grep -a -i "apply.*dhcp\|dhcp.*apply\|flatDhcp\|FlatDhcpBackend" "$LOG" | tail -15
