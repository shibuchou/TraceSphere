#!/usr/bin/env bash
cd /var/lib/zstack/virtualenv/zstackctl
. bin/activate

PORTAL=$(python -c "from zstackctl import ctl; h,p,u,pw=ctl.get_live_mysql_portal(); print('%s|%s|%s|%s'%(h,p,u,pw))")
DBH="${PORTAL%%|*}"; REST="${PORTAL#*|}"
DBP="${REST%%|*}";   REST="${REST#*|}"
DBU="${REST%%|*}";   DBPW="${REST#*|}"
echo "dbhost=$DBH port=$DBP user=$DBU"
echo
echo "== tables like account =="
mysql -h"$DBH" -P"$DBP" -u"$DBU" -p"$DBPW" zstack -N -e "show tables like '%ccount%';" 2>&1 | head
echo
echo "== AccountVO rows (masked pw) =="
mysql -h"$DBH" -P"$DBP" -u"$DBU" -p"$DBPW" zstack -e "select uuid,name,type,left(password,16) as pw_head,length(password) as pw_len from AccountVO;" 2>&1 | head -20
echo
echo "== sha512 of ${ZS_PW:?export ZS_PW} (head) =="
printf '%s' '${ZS_PW:?export ZS_PW}' | sha512sum | cut -c1-16
